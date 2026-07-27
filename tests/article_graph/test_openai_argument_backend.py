from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import (
    DocumentSection,
    SourceDocumentSnapshot,
    SpanAnchor,
    stable_id,
)
from readwelt.extraction import (
    ARGUMENT_TAXONOMY_SCHEMA_VERSION,
    CORE_CANDIDATE_KINDS,
    CORE_RELATION_KINDS,
    BackendCapability,
    CapabilityStatus,
    ExtractionInput,
    OpenAIArgumentSemanticBackend,
    configured_argument_semantic_backend,
)


def test_article_graph_builder_runs_injected_argument_backend() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        outbound = json.loads(request.content)
        source = json.loads(outbound["messages"][1]["content"])
        return _response(_full_taxonomy_candidate(source["window_text"]))

    text = "Premise one."
    backend = _backend(respond)

    build = ArticleGraphBuilder(semantic_backends=(backend,)).build(
        _snapshot(text),
        text,
    )

    semantic = next(
        extraction
        for extraction in build.extractions
        if extraction.backend.backend_id == backend.descriptor.backend_id
    )
    assert semantic.candidate_nodes
    assert semantic.candidate_edges
    assert semantic.coverage.complete


def test_openai_argument_backend_emits_full_taxonomy_with_exact_unit_grounding() -> None:
    observed: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        outbound = json.loads(request.content)
        observed.append(outbound)
        source = json.loads(outbound["messages"][1]["content"])
        window_text = source["window_text"]
        return httpx.Response(
            200,
            json={
                "id": "argument-response",
                "choices": [
                    {"message": {"content": json.dumps(_full_taxonomy_candidate(window_text))}}
                ],
            },
        )

    backend = _backend(respond)
    inputs = (
        ExtractionInput("document", "snapshot", "unit-1", "Premise one."),
        ExtractionInput("document", "snapshot", "unit-2", "Premise two."),
    )

    extraction = backend.extract(inputs)

    assert len(observed) == 2
    assert all(payload["response_format"]["json_schema"]["strict"] is True for payload in observed)
    assert extraction.backend.taxonomy_schema_version == ARGUMENT_TAXONOMY_SCHEMA_VERSION
    assert extraction.backend.emitted_candidate_kinds == CORE_CANDIDATE_KINDS
    assert extraction.backend.emitted_relations == CORE_RELATION_KINDS
    assert len(extraction.candidate_nodes) == len(CORE_CANDIDATE_KINDS) * 2
    assert len(extraction.candidate_edges) == len(CORE_RELATION_KINDS) * 2
    assert all(
        candidate.grounding.exact
        and candidate.grounding.source_references[0].exact_text
        == inputs[0 if "unit-1" in candidate.source_unit_ids else 1].text
        for candidate in (
            *extraction.candidate_nodes,
            *extraction.candidate_edges,
        )
    )
    assert {
        outcome.capability
        for outcome in extraction.outcomes
        if outcome.status is CapabilityStatus.COMPLETE
    } == set(backend.descriptor.supported_capabilities)


def test_openai_argument_backend_fails_unit_on_invalid_offsets_and_reports_every_capability() -> (
    None
):
    def respond(_request: httpx.Request) -> httpx.Response:
        candidate = _full_taxonomy_candidate("Short.")
        candidate["nodes"][0]["end"] = 999
        return _response(candidate)

    backend = _backend(respond)

    extraction = backend.extract((ExtractionInput("document", "snapshot", "unit-1", "Short."),))

    assert extraction.candidate_nodes == ()
    assert extraction.candidate_edges == ()
    assert extraction.coverage.uncovered_unit_ids == ("unit-1",)
    assert len(extraction.outcomes) == len(backend.descriptor.supported_capabilities)
    assert all(outcome.status is CapabilityStatus.FAILED for outcome in extraction.outcomes)
    assert all(
        "offsets are outside the window" in (outcome.message or "")
        for outcome in extraction.outcomes
    )


def test_openai_argument_backend_fails_empty_on_unknown_taxonomy_kind() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        candidate = _full_taxonomy_candidate("Short.")
        candidate["nodes"][0]["kind"] = "interpretation"
        return _response(candidate)

    backend = _backend(respond)

    extraction = backend.extract((ExtractionInput("document", "snapshot", "unit-1", "Short."),))

    assert extraction.candidate_nodes == ()
    assert extraction.candidate_edges == ()
    assert extraction.coverage.covered_unit_ids == ()
    assert extraction.coverage.uncovered_unit_ids == ("unit-1",)
    assert all(outcome.status is CapabilityStatus.FAILED for outcome in extraction.outcomes)


def test_openai_argument_backend_reports_partial_coverage_after_one_unit_failure() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        outbound = json.loads(request.content)
        source = json.loads(outbound["messages"][1]["content"])
        candidate = _full_taxonomy_candidate(source["window_text"])
        if source["unit_id"] == "unit-2":
            candidate["nodes"][0]["end"] = 999
        return _response(candidate)

    backend = _backend(respond)

    extraction = backend.extract(
        (
            ExtractionInput("document", "snapshot", "unit-1", "Valid."),
            ExtractionInput("document", "snapshot", "unit-2", "Invalid."),
        )
    )

    assert extraction.coverage.covered_unit_ids == ("unit-1",)
    assert extraction.coverage.uncovered_unit_ids == ("unit-2",)
    assert all(outcome.status is CapabilityStatus.PARTIAL for outcome in extraction.outcomes)
    assert all(outcome.covered_unit_ids == ("unit-1",) for outcome in extraction.outcomes)


def test_argument_backend_configuration_supports_local_openai_compatible_endpoints() -> None:
    backend = configured_argument_semantic_backend(
        {
            "READWELT_ARGUMENT_MODEL": "qwen-argument",
            "READWELT_ARGUMENT_BASE_URL": "http://127.0.0.1:8000/v1",
            "READWELT_ARGUMENT_MAX_REQUEST_TOKENS": "24000",
        }
    )

    assert backend is not None
    assert backend.model == "qwen-argument"
    assert backend.api_key == "local"
    assert backend.base_url == "http://127.0.0.1:8000/v1"
    assert backend.max_request_tokens == 24_000
    assert BackendCapability.PREMISE in backend.descriptor.supported_capabilities
    assert configured_argument_semantic_backend({}) is None


def _full_taxonomy_candidate(text: str) -> dict[str, object]:
    nodes = [
        {
            "local_id": f"node-{kind}",
            "kind": kind,
            "label": kind,
            "text": text,
            "start": 0,
            "end": len(text),
            "confidence": 0.8,
            "confidence_method": "model_structured_output",
            "attributes": [],
        }
        for kind in CORE_CANDIDATE_KINDS
    ]
    edges = [
        {
            "local_id": f"edge-{relation}",
            "relation": relation,
            "source_local_id": "node-premise",
            "target_local_id": "node-claim",
            "start": 0,
            "end": len(text),
            "confidence": 0.7,
            "confidence_method": "model_structured_output",
            "attributes": [],
        }
        for relation in CORE_RELATION_KINDS
    ]
    return {"nodes": nodes, "edges": edges}


def _backend(
    respond: Callable[[httpx.Request], httpx.Response],
) -> OpenAIArgumentSemanticBackend:
    return OpenAIArgumentSemanticBackend(
        model="local-argument-model",
        api_key="local",
        client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_request_tokens=32_000,
    )


def _response(candidate: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(candidate)}}]},
    )


def _snapshot(text: str) -> SourceDocumentSnapshot:
    snapshot_id = stable_id("snapshot", text)
    section_id = stable_id("section", snapshot_id, "0")
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=stable_id("document", text),
        schema_version="1",
        source_kind="text/plain",
        source_locator="article.txt",
        content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        language="en",
        normalized_text_ref="objects/article/body",
        sections=(
            DocumentSection(
                section_id=section_id,
                title=None,
                start_offset=0,
                end_offset=len(text),
                anchor=SpanAnchor.create(
                    snapshot_id=snapshot_id,
                    section_id=section_id,
                    text=text,
                    start_offset=0,
                    end_offset=len(text),
                ),
            ),
        ),
    )

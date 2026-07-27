from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from readwelt.article_graph import ArticleGraphBuilder, Canonicalizer, MergeOutcome
from readwelt.domain import DocumentSection, SourceDocumentSnapshot, SpanAnchor
from readwelt.domain.reading import ReadingStage
from readwelt.extraction import (
    ARGUMENT_TAXONOMY_SCHEMA_VERSION,
    CORE_CANDIDATE_KINDS,
    CORE_RELATION_KINDS,
    BackendCapability,
    BackendDescriptor,
    DeterministicSemanticExtractionBackend,
    ExtractionInput,
)
from readwelt.stage_views import StageContext, StageViewProjector


def _extraction(
    nodes: tuple[dict[str, object], ...],
    edges: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    return {
        "extraction_id": "taxonomy-extraction",
        "snapshot_id": "snapshot-1",
        "nodes": nodes,
        "edges": edges,
        "available_capabilities": (),
        "missing_capabilities": (),
    }


def _candidate(
    candidate_id: str,
    kind: str,
    *,
    label: str | None = None,
    score: float = 0.9,
    method: str = "backend-a.v1",
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "label": label or candidate_id,
        "text": label or candidate_id,
        "confidence": {"score": score, "method": method},
        "source_unit_ids": ("unit-1",),
        "ambiguity": (),
        "epistemic_status": "explicit",
        "attributes": (),
    }


def _snapshot(text: str) -> SourceDocumentSnapshot:
    digest = hashlib.sha256(text.encode()).hexdigest()
    snapshot_id = f"snapshot_{digest[:24]}"
    document_id = f"document_{digest[:24]}"
    section_id = f"section_{digest[:24]}"
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=document_id,
        schema_version="1",
        source_kind="text/plain",
        source_locator="argument.txt",
        content_digest=f"sha256:{digest}",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        language="en",
        normalized_text_ref="objects/argument/body",
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


def test_closed_core_taxonomy_and_namespaced_extensions_are_admitted() -> None:
    nodes = tuple(_candidate(f"candidate-{kind}", kind) for kind in CORE_CANDIDATE_KINDS) + (
        _candidate("candidate-extension", "stanza:sentence"),
    )
    result = Canonicalizer().canonicalize((_extraction(nodes),))

    assert {node.kind for node in result.graph.nodes} == {
        *CORE_CANDIDATE_KINDS,
        "stanza:sentence",
    }
    assert result.graph.taxonomy_schema_version == ARGUMENT_TAXONOMY_SCHEMA_VERSION


def test_unknown_unnamespaced_kind_and_relation_fail_empty_with_diagnostics() -> None:
    nodes = (
        _candidate("claim-a", "claim"),
        _candidate("claim-b", "claim"),
        _candidate("unknown-a", "mystery"),
    )
    edges = tuple(
        {
            "candidate_id": f"edge-{relation}",
            "relation": relation,
            "source_candidate_id": "claim-a",
            "target_candidate_id": "claim-b",
            "confidence": {"score": 0.9, "method": "relation-model.v1"},
            "source_unit_ids": ("unit-1",),
            "ambiguity": (),
            "epistemic_status": "semantic_inference",
            "attributes": (),
        }
        for relation in ("supports", "vendor:supports")
    )
    result = Canonicalizer().canonicalize((_extraction(nodes, edges),))

    assert "mystery" not in {node.kind for node in result.graph.nodes}
    assert {edge.relation for edge in result.graph.edges} == {"vendor:supports"}
    rejected = {
        candidate_id
        for decision in result.merge_report.decisions
        if decision.outcome is MergeOutcome.REJECT
        for candidate_id in decision.candidate_ids
    }
    assert {"unknown-a", "edge-supports"}.issubset(rejected)


def test_canonical_confidence_aggregation_retains_both_assessments() -> None:
    result = Canonicalizer().canonicalize(
        (
            _extraction(
                (
                    _candidate(
                        "entity-a",
                        "entity",
                        label="same entity",
                        score=0.92,
                        method="model-a.v1",
                    ),
                    _candidate(
                        "entity-b",
                        "entity",
                        label="same entity",
                        score=0.88,
                        method="model-b.v2",
                    ),
                )
            ),
        )
    )

    node = result.graph.nodes[0]
    assert node.confidence == 0.88
    assert node.confidence_method == "minimum_candidate_score.v1"
    assert {
        (source.candidate_id, source.method, source.mention_id)
        for source in node.confidence_sources
    } == {
        (
            "entity-a",
            "model-a.v1",
            next(
                item.mention_id for item in result.graph.mentions if item.candidate_id == "entity-a"
            ),
        ),
        (
            "entity-b",
            "model-b.v2",
            next(
                item.mention_id for item in result.graph.mentions if item.candidate_id == "entity-b"
            ),
        ),
    }


def test_claim_only_fallback_reports_every_other_argument_capability_missing() -> None:
    backend = DeterministicSemanticExtractionBackend()
    extraction = backend.extract(
        (
            ExtractionInput(
                document_id="document-1",
                snapshot_id="snapshot-1",
                unit_id="unit-1",
                text="A claim.",
            ),
        )
    )

    assert backend.descriptor.emitted_candidate_kinds == ("claim",)
    assert backend.descriptor.emitted_relations == ()
    assert {
        BackendCapability.PREMISE,
        BackendCapability.CONCLUSION,
        BackendCapability.EVIDENCE,
        BackendCapability.EXAMPLE,
        BackendCapability.OBJECTION,
        BackendCapability.QUALIFICATION,
        BackendCapability.SUPPORT_RELATION,
        BackendCapability.REFUTATION_RELATION,
        BackendCapability.CAUSATION_RELATION,
        BackendCapability.CONTRAST_RELATION,
        BackendCapability.QUALIFICATION_RELATION,
        BackendCapability.EXEMPLIFICATION_RELATION,
        BackendCapability.PREMISE_TO_CLAIM_RELATION,
        BackendCapability.CONCLUSION_FLOW_RELATION,
    }.issubset(extraction.missing_capabilities)


def test_backend_taxonomy_declarations_reject_unnamespaced_extensions() -> None:
    with pytest.raises(ValueError, match="candidate extensions must be namespaced"):
        BackendDescriptor(
            backend_id="bad-backend",
            name="Bad backend",
            version="1",
            model_revision=None,
            supported_capabilities=(),
            taxonomy_schema_version=ARGUMENT_TAXONOMY_SCHEMA_VERSION,
            emitted_candidate_kinds=("sentence",),
        )


def test_stage_view_preserves_graph_claim_confidence_and_candidate_lineage() -> None:
    text = "A source-grounded claim."
    build = ArticleGraphBuilder().build(_snapshot(text), text)
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="locate the main line",
            token_budget=256,
        ),
    )

    canonical = build.graph.claims[0]
    projected = next(item for item in view.claim_candidates if item.claim_id == canonical.claim_id)
    assert projected.confidence == canonical.confidence
    assert projected.confidence_method == canonical.confidence_method
    assert projected.confidence_sources
    assert projected.candidate_ids == canonical.candidate_ids
    assert projected.mention_ids == canonical.mention_ids
    assert view.schema_version == "stage-view.v4"


@pytest.mark.parametrize("relation", CORE_RELATION_KINDS)
def test_all_core_relations_are_admitted(relation: str) -> None:
    nodes = (
        _candidate("claim-a", "claim"),
        _candidate("claim-b", "claim"),
    )
    edge = {
        "candidate_id": f"edge-{relation}",
        "relation": relation,
        "source_candidate_id": "claim-a",
        "target_candidate_id": "claim-b",
        "confidence": {"score": 0.9, "method": "relation-model.v1"},
        "source_unit_ids": ("unit-1",),
        "ambiguity": (),
        "epistemic_status": "semantic_inference",
        "attributes": (),
    }

    result = Canonicalizer().canonicalize((_extraction(nodes, (edge,)),))
    assert tuple(item.relation for item in result.graph.edges) == (relation,)

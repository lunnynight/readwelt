from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import DocumentSection, SourceDocumentSnapshot, SpanAnchor
from readwelt.provenance import (
    ProvenanceEventType,
    algorithm_lineage_for_build,
)

_EXPECTED_PATTERN_IDS = {
    "docling-core.reference-provenance-pattern",
    "docling-graph.provenance-merge-pattern",
    "graphrag.textunit-reverse-map",
    "kag.explicit-source-chunk-links",
    "prov.independent-lineage-model",
    "openlineage.versioned-event-envelope",
}


def _snapshot(text: str) -> SourceDocumentSnapshot:
    snapshot_id = "snapshot:algorithm-lineage"
    section_id = "section:algorithm-lineage"
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id="document:algorithm-lineage",
        schema_version="1",
        source_kind="text/plain",
        source_locator="source.txt",
        content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        language="en",
        normalized_text_ref="objects/source.txt",
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


def test_adapted_algorithm_records_are_pinned_and_scope_product_exclusions() -> None:
    records = algorithm_lineage_for_build(())

    assert {record.algorithm_id for record in records} == _EXPECTED_PATTERN_IDS
    assert all(len(record.source_revision) >= 40 for record in records)
    assert all(record.source_repository.startswith("https://github.com/") for record in records)
    assert all(record.license_name in {"MIT", "Apache-2.0"} for record in records)
    assert all(record.license_decision for record in records)
    assert all(record.local_adapter_version.startswith("readwelt.") for record in records)
    assert all(record.capability_scope for record in records)
    assert all(record.excluded_product_behavior for record in records)


def test_build_ledger_persists_every_contributing_algorithm_record() -> None:
    text = "Artifact lineage must preserve adopted algorithm decisions."
    build = ArticleGraphBuilder().build(_snapshot(text), text)
    events = tuple(
        event
        for event in build.provenance_ledger.events
        if event.event_type is ProvenanceEventType.ADOPTION
    )

    assert len(events) == len(_EXPECTED_PATTERN_IDS)
    payloads = tuple(dict(event.payload) for event in events)
    assert {str(payload["algorithm_id"]) for payload in payloads} == (_EXPECTED_PATTERN_IDS)
    for event, payload in zip(events, payloads, strict=True):
        assert event.source_refs == ()
        assert len(event.outputs) == 1
        assert event.outputs[0].startswith("sha256:")
        assert payload["schema_version"] == "algorithm-lineage.v1"
        assert payload["source_repository"]
        assert payload["source_revision"]
        assert payload["license_decision"]
        assert payload["local_adapter_version"]
        assert payload["capability_scope"]
        assert payload["excluded_product_behavior"]


def test_xberg_lineage_is_recorded_only_when_xberg_contributed() -> None:
    plain = algorithm_lineage_for_build(("ingested_by_plain_text_fallback",))
    xberg = algorithm_lineage_for_build(("ingested_by_xberg_1.0.0rc38",))

    assert all(record.algorithm_id != "xberg.primary-ingestion-adapter" for record in plain)
    xberg_record = next(
        record for record in xberg if record.algorithm_id == "xberg.primary-ingestion-adapter"
    )
    assert xberg_record.source_revision == "release:1.0.0rc38"
    assert xberg_record.license_name == "MIT"
    assert xberg_record.adoption_kind == "adopted_backend"


def test_docling_production_fallback_lineage_records_runtime_and_models() -> None:
    plain = algorithm_lineage_for_build(("docling_fallback_backend:injected_test_double",))
    production = algorithm_lineage_for_build(("docling_fallback_backend:production",))

    assert all(record.algorithm_id != "docling.pdf-ocr-structural-fallback" for record in plain)
    record = next(
        item for item in production if item.algorithm_id == "docling.pdf-ocr-structural-fallback"
    )
    assert record.source_revision == "release:2.114.0"
    assert record.license_name == "MIT"
    assert record.adoption_kind == "adopted_backend"
    assert record.model_artifact_digest == (
        "sha256:117ce0d7c9486c4bb9b53a11b5fe5f2035bf192997cf4915b5cb99f97389a202"
    )
    assert "rapidocr==3.9.2" in record.dependency_versions
    assert any(
        decision.startswith("docling-models:CDLA-Permissive-2.0")
        for decision in record.model_license_decisions
    )
    payload = record.to_payload()
    assert payload["local_adapter_version"] == ("readwelt.docling-structural-fallback.v1")
    assert payload["model_artifact_revisions"]
    assert payload["runtime_configuration"]


def test_docling_production_lineage_is_persisted_in_the_build_ledger() -> None:
    text = "A local Docling fallback contributed source structure."
    snapshot = replace(
        _snapshot(text),
        parse_findings=(
            "ingested_by_xberg_1.0.0rc38",
            "docling_fallback_backend:production",
        ),
    )

    build = ArticleGraphBuilder().build(snapshot, text)
    payload = next(
        dict(event.payload)
        for event in build.provenance_ledger.events
        if event.event_type is ProvenanceEventType.ADOPTION
        and dict(event.payload).get("algorithm_id") == "docling.pdf-ocr-structural-fallback"
    )

    assert payload["dependency_versions"]
    assert payload["model_artifact_digest"] == (
        "sha256:117ce0d7c9486c4bb9b53a11b5fe5f2035bf192997cf4915b5cb99f97389a202"
    )
    assert payload["model_license_decisions"]

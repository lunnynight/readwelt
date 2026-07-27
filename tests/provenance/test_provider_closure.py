from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import (
    DocumentSection,
    ReadingStage,
    SourceDocumentSnapshot,
    SpanAnchor,
    stable_id,
)
from readwelt.provenance import (
    ProvenanceEventType,
    ProvenanceLedger,
    ProviderMaterialDisposition,
    ProviderMaterialKind,
    ProviderVisibleMaterial,
    SourceRecordKind,
    final_provider_visible_material,
    provider_visible_material,
    validate_provider_material_closure,
)
from readwelt.stage_views import StageContext, StageViewProjector


def _build():
    text = "A cache needs a revision key.\n\nA stale key returns stale data."
    snapshot_id = stable_id("snapshot", text)
    document_id = stable_id("document", text)
    sections = []
    cursor = 0
    for ordinal, paragraph in enumerate(text.split("\n\n")):
        start = text.index(paragraph, cursor)
        end = start + len(paragraph)
        cursor = end
        section_id = stable_id("section", snapshot_id, str(ordinal))
        sections.append(
            DocumentSection(
                section_id=section_id,
                title=None,
                start_offset=start,
                end_offset=end,
                anchor=SpanAnchor.create(
                    snapshot_id=snapshot_id,
                    section_id=section_id,
                    text=text,
                    start_offset=start,
                    end_offset=end,
                ),
            )
        )
    snapshot = SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=document_id,
        schema_version="1",
        source_kind="text/plain",
        source_locator="article.txt",
        content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        language="en",
        normalized_text_ref="objects/article/body",
        sections=tuple(sections),
    )
    return ArticleGraphBuilder().build(snapshot, text)


def _view_and_report():
    build = _build()
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="locate the main line",
            token_budget=256,
        ),
    )
    material = provider_visible_material(
        nodes=(
            (item.node_id, item.source_unit_ids, item.source_element_ids) for item in view.nodes
        ),
        edges=(
            (item.edge_id, item.source_unit_ids, item.source_element_ids) for item in view.edges
        ),
        claims=(
            (
                item.claim_id,
                item.evidence_unit_ids,
                item.evidence_element_ids,
            )
            for item in view.claim_candidates
        ),
        text_items=(
            (item.serialized_identity, item.unit_id, item.slice_id is not None)
            for item in view.text_units
        ),
        source_ranges=((item.range_id, item.unit_ids) for item in view.source_ranges),
        source_elements=(
            (item.serialized_identity, item.element_id, item.source_unit_ids)
            for item in view.source_elements
        ),
    )
    report = validate_provider_material_closure(
        material,
        snapshot_id=build.snapshot_id,
        unitization=build.unitization,
        source_index=build.source_index,
        ledger_artifact=build.provenance_ledger,
        expected_graph_digest=view.graph_digest,
        expected_source_index_digest=view.source_index_digest,
        expected_ledger_digest=view.provenance_ledger_digest,
    )
    return build, view, material, report


def test_provider_visible_material_closes_to_typed_source_plane_records() -> None:
    _, view, material, report = _view_and_report()

    assert report.valid
    assert report.resolutions
    assert all(resolution.source_references for resolution in report.resolutions)
    assert all(resolution.ledger_event_digests for resolution in report.resolutions)
    assert SourceRecordKind.TEXT_UNIT in {
        reference.record_kind
        for resolution in report.resolutions
        for reference in resolution.source_references
    }
    assert SourceRecordKind.SOURCE_RANGE in {
        reference.record_kind
        for resolution in report.resolutions
        for reference in resolution.source_references
    }
    assert "provider_visible_material" not in view.to_mapping()


def test_text_slice_resolves_through_its_parent_source_unit() -> None:
    build = _build()
    unit_id = build.unitization.units[0].unit_id
    material = ProviderVisibleMaterial(
        material_id="slice:provider-packet",
        material_kind=ProviderMaterialKind.TEXT_SLICE,
        source_unit_ids=(unit_id,),
    )

    report = validate_provider_material_closure(
        (material,),
        snapshot_id=build.snapshot_id,
        unitization=build.unitization,
        source_index=build.source_index,
        ledger_artifact=build.provenance_ledger,
        expected_graph_digest=build.graph.content_digest,
        expected_source_index_digest=build.source_index.content_digest,
        expected_ledger_digest=build.provenance_ledger.content_digest,
    )

    assert report.valid
    assert {
        reference.record_id
        for reference in report.resolutions[0].source_references
        if reference.record_kind is SourceRecordKind.TEXT_UNIT
    } == {unit_id}


def test_unknown_graph_identity_fails_empty_without_fabricated_source_refs() -> None:
    build = _build()
    material = ProviderVisibleMaterial(
        material_id="node:unknown",
        material_kind=ProviderMaterialKind.GRAPH_NODE,
        source_unit_ids=(),
    )

    report = validate_provider_material_closure(
        (material,),
        snapshot_id=build.snapshot_id,
        unitization=build.unitization,
        source_index=build.source_index,
        ledger_artifact=build.provenance_ledger,
        expected_graph_digest=build.graph.content_digest,
        expected_source_index_digest=build.source_index.content_digest,
        expected_ledger_digest=build.provenance_ledger.content_digest,
    )

    assert not report.valid
    assert report.issues[0].code == "unknown_graph_object"
    assert report.resolutions[0].source_references == ()
    assert report.resolutions[0].ledger_event_digests == ()


def test_unrelated_ledger_event_cannot_supply_graph_grounding() -> None:
    build, _, material, _ = _view_and_report()
    graph_material = next(
        item
        for item in material
        if item.material_kind in {ProviderMaterialKind.GRAPH_NODE, ProviderMaterialKind.GRAPH_CLAIM}
    )
    unitization_event_index = next(
        index
        for index, event in enumerate(build.provenance_ledger.events)
        if event.event_type is ProvenanceEventType.UNITIZATION
    )
    pre_canonicalization = ProvenanceLedger(
        build.provenance_ledger.events[: unitization_event_index + 1]
    ).to_artifact()

    report = validate_provider_material_closure(
        (graph_material,),
        snapshot_id=build.snapshot_id,
        unitization=build.unitization,
        source_index=build.source_index,
        ledger_artifact=pre_canonicalization,
        expected_graph_digest=build.graph.content_digest,
        expected_source_index_digest=build.source_index.content_digest,
        expected_ledger_digest=pre_canonicalization.content_digest,
    )

    assert not report.valid
    assert any(issue.code == "missing_canonicalization_event" for issue in report.issues)
    assert report.resolutions[0].source_references == ()


def test_final_stage_request_material_is_typed_source_or_explicit_non_source() -> None:
    build, view, stage_material, _ = _view_and_report()
    anchor_id = next(
        reference.anchor_id
        for unit in build.unitization.units
        for reference in unit.source_references
        if reference.anchor_id is not None
    )
    materials = final_provider_visible_material(
        stage_view_materials=stage_material,
        unitization=build.unitization,
        anchor_ids=(anchor_id,),
        retrieval_hits=(("retrieval-hit:1", anchor_id),),
        upstream_claim_ids=("stage-claim:1",),
        external_evidence_ids=("external-evidence:1",),
        metadata_ids=("metadata:stage-policy", "metadata:response-schema"),
        provenance_ids=("provenance:request-digest",),
    )

    report = validate_provider_material_closure(
        materials,
        snapshot_id=build.snapshot_id,
        unitization=build.unitization,
        source_index=build.source_index,
        ledger_artifact=build.provenance_ledger,
        expected_graph_digest=view.graph_digest,
        expected_source_index_digest=view.source_index_digest,
        expected_ledger_digest=view.provenance_ledger_digest,
    )

    assert report.valid
    by_kind = {resolution.material.material_kind: resolution for resolution in report.resolutions}
    for kind in (ProviderMaterialKind.ANCHOR, ProviderMaterialKind.RETRIEVAL_HIT):
        assert by_kind[kind].material.disposition is (ProviderMaterialDisposition.SOURCE_GROUNDED)
        assert by_kind[kind].source_references
        assert by_kind[kind].ledger_event_digests
    for kind in (
        ProviderMaterialKind.UPSTREAM_CLAIM,
        ProviderMaterialKind.EXTERNAL_EVIDENCE,
        ProviderMaterialKind.REQUEST_METADATA,
        ProviderMaterialKind.REQUEST_PROVENANCE,
    ):
        assert by_kind[kind].material.disposition is (
            ProviderMaterialDisposition.NON_SOURCE_METADATA
        )
        assert by_kind[kind].material.non_source_reason
        assert by_kind[kind].source_references == ()
        assert by_kind[kind].ledger_event_digests == ()


def test_unknown_final_request_anchor_fails_closed() -> None:
    build, view, stage_material, _ = _view_and_report()
    materials = final_provider_visible_material(
        stage_view_materials=stage_material,
        unitization=build.unitization,
        anchor_ids=("anchor:unknown",),
        retrieval_hits=(),
        upstream_claim_ids=(),
        external_evidence_ids=(),
        metadata_ids=(),
        provenance_ids=(),
    )

    report = validate_provider_material_closure(
        materials,
        snapshot_id=build.snapshot_id,
        unitization=build.unitization,
        source_index=build.source_index,
        ledger_artifact=build.provenance_ledger,
        expected_graph_digest=view.graph_digest,
        expected_source_index_digest=view.source_index_digest,
        expected_ledger_digest=view.provenance_ledger_digest,
    )

    unknown = next(
        resolution
        for resolution in report.resolutions
        if resolution.material.material_id == "anchor:unknown"
    )
    assert not report.valid
    assert any(
        issue.code == "missing_source_binding" and issue.material_id == "anchor:unknown"
        for issue in report.issues
    )
    assert unknown.source_references == ()
    assert unknown.ledger_event_digests == ()

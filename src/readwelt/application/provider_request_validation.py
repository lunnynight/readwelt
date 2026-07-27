"""Provenance-closure validation for the exact final provider envelope."""

from __future__ import annotations

from collections.abc import Mapping

from readwelt.article_graph import ArticleGraphBuildResult
from readwelt.article_graph.digest import stable_identifier
from readwelt.provenance import (
    final_provider_visible_material,
    provider_visible_material,
    validate_provider_material_closure,
)
from readwelt.providers import StageRequest
from readwelt.stage_views import StageView


def validate_final_provider_request(
    request: StageRequest,
    stage_view: StageView,
    graph_build: ArticleGraphBuildResult,
) -> None:
    packet = request.evidence_packet
    anchors = request_page_items(packet.get("anchors"))
    retrieval_hits = request_page_items(packet.get("retrieval_hits"))
    upstream_claims = request_page_items(packet.get("upstream_claims"))
    external_evidence = request_page_items(packet.get("external_evidence"))
    stage_materials = provider_visible_material(
        nodes=(
            (item.node_id, item.source_unit_ids, item.source_element_ids)
            for item in stage_view.nodes
        ),
        edges=(
            (item.edge_id, item.source_unit_ids, item.source_element_ids)
            for item in stage_view.edges
        ),
        claims=(
            (
                item.claim_id,
                item.evidence_unit_ids,
                item.evidence_element_ids,
            )
            for item in stage_view.claim_candidates
        ),
        text_items=(
            (
                item.serialized_identity,
                item.unit_id,
                item.slice_id is not None,
            )
            for item in stage_view.text_units
        ),
        source_ranges=((item.range_id, item.unit_ids) for item in stage_view.source_ranges),
        source_elements=(
            (
                item.serialized_identity,
                item.element_id,
                item.source_unit_ids,
            )
            for item in stage_view.source_elements
        ),
    )
    materials = final_provider_visible_material(
        stage_view_materials=stage_materials,
        unitization=graph_build.unitization,
        anchor_ids=(
            str(item["anchor_id"])
            for item in anchors
            if isinstance(item, Mapping) and isinstance(item.get("anchor_id"), str)
        ),
        retrieval_hits=(
            (
                stable_identifier("retrieval_hit", item),
                str(item["anchor_id"]),
            )
            for item in retrieval_hits
            if isinstance(item, Mapping) and isinstance(item.get("anchor_id"), str)
        ),
        upstream_claim_ids=(
            str(item["claim_id"])
            for item in upstream_claims
            if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)
        ),
        external_evidence_ids=(
            (
                str(item["evidence_id"])
                if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
                else stable_identifier("external_evidence", item)
            )
            for item in external_evidence
        ),
        metadata_ids=(
            f"metadata:{key}"
            for key in sorted(packet)
            if key
            not in {
                "anchors",
                "retrieval_hits",
                "upstream_claims",
                "external_evidence",
                "stage_view",
            }
        ),
        provenance_ids=(f"provenance:{key}" for key in sorted(request.provenance)),
    )
    closure = validate_provider_material_closure(
        materials,
        snapshot_id=graph_build.snapshot_id,
        unitization=graph_build.unitization,
        source_index=graph_build.source_index,
        ledger_artifact=graph_build.provenance_ledger,
        expected_graph_digest=stage_view.graph_digest,
        expected_source_index_digest=stage_view.source_index_digest,
        expected_ledger_digest=stage_view.provenance_ledger_digest,
    )
    if not closure.valid:
        first_issue = closure.issues[0]
        raise ValueError(
            "final provider request provenance closure failed: "
            f"{first_issue.code}: {first_issue.detail}"
        )


def request_page_items(value: object) -> tuple[object, ...]:
    items = value.get("items", ()) if isinstance(value, Mapping) else value
    if not isinstance(items, (list, tuple)):
        return ()
    return tuple(items)

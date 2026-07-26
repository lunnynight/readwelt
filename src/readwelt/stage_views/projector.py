"""Budgeted ArticleGraph projections for the six reading stages."""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil

from readwelt.article_graph import ArticleGraphBuildResult
from readwelt.article_graph.digest import content_digest
from readwelt.domain.reading import ReadingClaim, ReadingStage
from readwelt.semantic.models import SemanticEvidencePacket

from .models import (
    SelectionReason,
    StageContext,
    StageView,
    StageViewCapabilityOutcome,
    StageViewEdge,
    StageViewNode,
    StageViewTextUnit,
    StageViewUpstreamClaim,
)

_STAGE_KIND_PRIORITY: dict[ReadingStage, tuple[str, ...]] = {
    ReadingStage.MAINLINE: ("claim", "evidence", "concept", "entity", "event"),
    ReadingStage.STRUCTURE: (
        "claim",
        "evidence",
        "example",
        "objection",
        "qualification",
    ),
    ReadingStage.DECOMPRESSION: ("concept", "entity", "event", "claim"),
    ReadingStage.AUTHOR_MODEL: ("claim", "concept", "entity", "event"),
    ReadingStage.BOUNDARIES: (
        "claim",
        "qualification",
        "objection",
        "evidence",
        "example",
    ),
    ReadingStage.TRANSFER: ("claim", "concept", "event", "qualification"),
}


class StageViewProjector:
    """Project graph-grounded context while leaving locator choice explicit."""

    schema_version = "stage-view.v1"

    def project(
        self,
        build: ArticleGraphBuildResult,
        context: StageContext,
        *,
        upstream_claims: Sequence[ReadingClaim] = (),
        locator_packet: SemanticEvidencePacket | None = None,
    ) -> StageView:
        if locator_packet is not None:
            if locator_packet.snapshot_id != build.snapshot_id:
                raise ValueError("locator packet belongs to a different snapshot")
            if locator_packet.stage is not None and locator_packet.stage is not context.stage:
                raise ValueError("locator packet belongs to a different reading stage")

        unit_by_id = {unit.unit_id: unit for unit in build.unitization.units}
        anchor_to_unit = {
            reference.anchor_id: unit.unit_id
            for unit in build.unitization.units
            for reference in unit.source_references
            if reference.anchor_id is not None
        }
        knowledge_unit_ids, graph_insufficient = _knowledge_units(build, context.stage)
        ranked_ids, locator_ids = _ranked_unit_ids(
            build,
            knowledge_unit_ids,
            anchor_to_unit,
            locator_packet,
        )
        selected_units: list[StageViewTextUnit] = []
        reasons: list[SelectionReason] = []
        used_tokens = 0
        for unit_id in ranked_ids:
            unit = unit_by_id.get(unit_id)
            if unit is None:
                continue
            tokens = _estimated_tokens(unit.exact_text)
            if used_tokens + tokens > context.token_budget:
                continue
            selected_units.append(
                StageViewTextUnit(
                    unit_id=unit.unit_id,
                    kind=unit.kind,
                    text=unit.exact_text,
                    anchor_ids=tuple(
                        reference.anchor_id
                        for reference in unit.source_references
                        if reference.anchor_id is not None
                    ),
                    ordinal=unit.ordinal,
                    estimated_tokens=tokens,
                )
            )
            used_tokens += tokens
            reasons.append(
                SelectionReason(
                    object_type="text_unit",
                    object_id=unit.unit_id,
                    reason=(
                        f"locator:{locator_packet.retrieval_backend}"
                        if unit.unit_id in locator_ids and locator_packet is not None
                        else f"stage_kind:{context.stage.value}"
                    ),
                    priority=len(reasons),
                )
            )

        selected_ids = {unit.unit_id for unit in selected_units}
        stage_kinds = frozenset(_STAGE_KIND_PRIORITY[context.stage])
        nodes = tuple(
            StageViewNode(
                node_id=node.node_id,
                kind=node.kind,
                label=node.label,
                text=None,
                epistemic_status=node.epistemic_status.value,
                source_unit_ids=tuple(
                    unit_id for unit_id in node.source_unit_ids if unit_id in selected_ids
                ),
            )
            for node in build.graph.nodes
            if node.kind in stage_kinds
            and selected_ids.intersection(node.source_unit_ids)
        )
        selected_node_ids = {node.node_id for node in nodes}
        edges = tuple(
            StageViewEdge(
                edge_id=edge.edge_id,
                relation=edge.relation,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                epistemic_status=edge.epistemic_status.value,
                source_unit_ids=tuple(
                    unit_id for unit_id in edge.source_unit_ids if unit_id in selected_ids
                ),
            )
            for edge in build.graph.edges
            if edge.source_node_id in selected_node_ids
            and edge.target_node_id in selected_node_ids
            and selected_ids.intersection(edge.source_unit_ids)
        )
        view_claims = tuple(
            StageViewUpstreamClaim(
                claim_id=claim.claim_id,
                text=claim.text,
                decision=claim.decision.value,
                anchor_ids=claim.anchor_ids,
            )
            for claim in upstream_claims
            if not context.upstream_claim_ids or claim.claim_id in context.upstream_claim_ids
        )
        for node in nodes:
            reasons.append(
                SelectionReason(
                    object_type="node",
                    object_id=node.node_id,
                    reason=f"grounded_in_selected_unit:{node.kind}",
                    priority=len(reasons),
                )
            )
        for edge in edges:
            reasons.append(
                SelectionReason(
                    object_type="edge",
                    object_id=edge.edge_id,
                    reason=f"connects_selected_nodes:{edge.relation}",
                    priority=len(reasons),
                )
            )
        unresolved_conflict_ids = tuple(
            conflict.conflict_id
            for conflict in build.merge_report.conflicts
            if conflict.resolution == "unresolved"
        )
        missing_capabilities = tuple(
            item.value for item in build.capability_report.missing_capabilities
        )
        capability_outcomes = tuple(
            StageViewCapabilityOutcome(
                backend_id=extraction.backend.backend_id,
                capability=outcome.capability.value,
                status=outcome.status.value,
                message=outcome.message,
            )
            for extraction in build.extractions
            for outcome in extraction.outcomes
        )
        coverage_complete = build.unitization.coverage.has_complete_text_coverage
        locator_backend = (
            locator_packet.retrieval_backend
            if locator_packet is not None and locator_ids
            else None
        )
        fallback_backend = locator_backend if graph_insufficient else None
        digest_value = {
            "schema_version": self.schema_version,
            "snapshot_id": build.snapshot_id,
            "stage": context.stage.value,
            "task_intent": context.task_intent,
            "nodes": nodes,
            "edges": edges,
            "text_units": tuple(selected_units),
            "upstream_claims": view_claims,
            "unresolved_conflict_ids": unresolved_conflict_ids,
            "missing_capabilities": missing_capabilities,
            "capability_outcomes": capability_outcomes,
            "coverage_complete": coverage_complete,
            "token_budget": context.token_budget,
            "estimated_tokens": used_tokens,
            "selection_reasons": tuple(reasons),
            "locator_backend": locator_backend,
            "fallback_backend": fallback_backend,
            "graph_digest": build.graph.content_digest,
            "source_index_digest": build.source_index.content_digest,
            "provenance_ledger_digest": build.provenance_ledger.content_digest,
        }
        return StageView(
            schema_version=self.schema_version,
            snapshot_id=build.snapshot_id,
            stage=context.stage,
            task_intent=context.task_intent,
            nodes=nodes,
            edges=edges,
            text_units=tuple(selected_units),
            upstream_claims=view_claims,
            unresolved_conflict_ids=unresolved_conflict_ids,
            missing_capabilities=missing_capabilities,
            capability_outcomes=capability_outcomes,
            coverage_complete=coverage_complete,
            token_budget=context.token_budget,
            estimated_tokens=used_tokens,
            selection_reasons=tuple(reasons),
            locator_backend=locator_backend,
            fallback_backend=fallback_backend,
            graph_digest=build.graph.content_digest,
            source_index_digest=build.source_index.content_digest,
            provenance_ledger_digest=build.provenance_ledger.content_digest,
            content_digest=content_digest(digest_value),
        )


def _knowledge_units(
    build: ArticleGraphBuildResult,
    stage: ReadingStage,
) -> tuple[frozenset[str], bool]:
    priorities = _STAGE_KIND_PRIORITY[stage]
    preferred = {
        unit_id
        for node in build.graph.nodes
        if node.kind in priorities
        for unit_id in build.source_index.units_for_node(node.node_id)
    }
    preferred.update(
        unit_id
        for claim in build.graph.claims
        for unit_id in build.source_index.evidence_units_for_claim(claim.claim_id)
    )
    if preferred:
        return frozenset(preferred), False
    return frozenset(unit.unit_id for unit in build.unitization.units), True


def _ranked_unit_ids(
    build: ArticleGraphBuildResult,
    knowledge_unit_ids: frozenset[str],
    anchor_to_unit: dict[str, str],
    locator_packet: SemanticEvidencePacket | None,
) -> tuple[tuple[str, ...], frozenset[str]]:
    locator_ids: list[str] = []
    if locator_packet is not None:
        ordered_anchor_ids = (
            tuple(hit.anchor_id for hit in locator_packet.hits)
            or tuple(anchor.anchor_id for anchor in locator_packet.anchors)
        )
        locator_ids.extend(
            unit_id
            for anchor_id in ordered_anchor_ids
            if (unit_id := anchor_to_unit.get(anchor_id)) is not None
            and unit_id in knowledge_unit_ids
        )
    ordered = tuple(
        dict.fromkeys(
            (
                *locator_ids,
                *(
                    unit.unit_id
                    for unit in sorted(
                        build.unitization.units,
                        key=lambda item: (item.ordinal, item.unit_id),
                    )
                    if unit.unit_id in knowledge_unit_ids
                ),
            )
        )
    )
    return ordered, frozenset(locator_ids)


def _estimated_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4))

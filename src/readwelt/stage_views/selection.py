"""Stage policy ranking, rescue expansion, and graph selection."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from readwelt.article_graph import ArticleGraphBuildResult, ConfidenceSource
from readwelt.domain.reading import ReadingClaim, ReadingStage
from readwelt.semantic.models import SemanticEvidencePacket

from .models import (
    SelectionReason,
    StageContext,
    StageViewClaim,
    StageViewConfidenceSource,
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
_RESCUE_ORDER = {
    "initial": 0,
    "neighbors": 1,
    "structure": 2,
    "targeted": 3,
    "section": 4,
}


def selected_graph(
    build: ArticleGraphBuildResult,
    stage: ReadingStage,
    selected_source_ids: Collection[str],
    selected_element_ids: Collection[str] = (),
) -> tuple[
    tuple[StageViewNode, ...],
    tuple[StageViewEdge, ...],
    tuple[StageViewClaim, ...],
]:
    selected_ids = set(selected_source_ids)
    selected_elements = set(selected_element_ids)
    stage_kinds = frozenset(_STAGE_KIND_PRIORITY[stage])
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
            source_element_ids=tuple(
                element_id
                for element_id in node.source_element_ids
                if element_id in selected_elements
            ),
            confidence=node.confidence,
            confidence_method=node.confidence_method,
            confidence_sources=_confidence_sources(node.confidence_sources),
            ambiguity=node.ambiguity,
            candidate_ids=node.candidate_ids,
            mention_ids=node.mention_ids,
        )
        for node in build.graph.nodes
        if node.kind in stage_kinds
        and (
            selected_ids.intersection(node.source_unit_ids)
            or selected_elements.intersection(node.source_element_ids)
        )
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
            source_element_ids=tuple(
                element_id
                for element_id in edge.source_element_ids
                if element_id in selected_elements
            ),
            confidence=edge.confidence,
            confidence_method=edge.confidence_method,
            confidence_sources=_confidence_sources(edge.confidence_sources),
            ambiguity=edge.ambiguity,
            candidate_ids=edge.candidate_ids,
        )
        for edge in build.graph.edges
        if edge.source_node_id in selected_node_ids
        and edge.target_node_id in selected_node_ids
        and (
            selected_ids.intersection(edge.source_unit_ids)
            or selected_elements.intersection(edge.source_element_ids)
        )
    )
    connected_node_ids = {
        node_id for edge in edges for node_id in (edge.source_node_id, edge.target_node_id)
    }
    # A canonical Claim already carries its own identity, text, grounding, and
    # confidence lineage below. Keep its parallel claim-node only when an edge
    # needs that node as an argument endpoint; otherwise it is duplicate prompt
    # material.
    nodes = tuple(
        node for node in nodes if node.kind != "claim" or node.node_id in connected_node_ids
    )
    claims = tuple(
        StageViewClaim(
            claim_id=claim.claim_id,
            text=claim.text,
            epistemic_status=claim.epistemic_status.value,
            evidence_unit_ids=tuple(
                unit_id for unit_id in claim.evidence_unit_ids if unit_id in selected_ids
            ),
            evidence_element_ids=tuple(
                element_id
                for element_id in claim.evidence_element_ids
                if element_id in selected_elements
            ),
            confidence=claim.confidence,
            confidence_method=claim.confidence_method,
            confidence_sources=_confidence_sources(claim.confidence_sources),
            ambiguity=claim.ambiguity,
            candidate_ids=claim.candidate_ids,
            mention_ids=claim.mention_ids,
        )
        for claim in build.graph.claims
        if (
            selected_ids.intersection(claim.evidence_unit_ids)
            or selected_elements.intersection(claim.evidence_element_ids)
        )
    )
    return nodes, edges, claims


def _confidence_sources(
    values: Sequence[ConfidenceSource],
) -> tuple[StageViewConfidenceSource, ...]:
    return tuple(
        StageViewConfidenceSource(
            candidate_id=value.candidate_id,
            score=value.score,
            method=value.method,
            mention_id=value.mention_id,
        )
        for value in values
    )


def upstream_claims(
    context: StageContext,
    claims: Sequence[ReadingClaim],
) -> tuple[StageViewUpstreamClaim, ...]:
    return tuple(
        StageViewUpstreamClaim(
            claim_id=claim.claim_id,
            text=claim.text,
            decision=claim.decision.value,
            anchor_ids=claim.anchor_ids,
        )
        for claim in claims
        if not context.upstream_claim_ids or claim.claim_id in context.upstream_claim_ids
    )


def selection_reasons(
    selected: tuple[StageViewTextUnit, ...],
    nodes: tuple[StageViewNode, ...],
    edges: tuple[StageViewEdge, ...],
    claims: tuple[StageViewClaim, ...],
    locator_ids: frozenset[str],
    locator_packet: SemanticEvidencePacket | None,
    context: StageContext,
) -> tuple[SelectionReason, ...]:
    reasons: list[SelectionReason] = []
    for unit in selected:
        reasons.append(
            SelectionReason(
                object_type="text_unit",
                object_id=unit.serialized_identity,
                reason=(
                    f"locator:{locator_packet.retrieval_backend}"
                    if unit.unit_id in locator_ids and locator_packet is not None
                    else f"rescue:{context.rescue_level}"
                ),
                priority=len(reasons),
            )
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
    for claim in claims:
        reasons.append(
            SelectionReason(
                object_type="graph_claim",
                object_id=claim.claim_id,
                reason="grounded_claim_candidate",
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
    return tuple(reasons)


def knowledge_units(
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


def constrain_units_to_admitted_anchors(
    build: ArticleGraphBuildResult,
    unit_ids: frozenset[str],
    allowed_anchor_ids: tuple[str, ...] | None,
) -> frozenset[str]:
    if allowed_anchor_ids is None:
        return unit_ids
    admitted = frozenset(allowed_anchor_ids)
    return frozenset(
        unit.unit_id
        for unit in build.unitization.units
        if unit.unit_id in unit_ids
        and (
            anchors := {
                reference.anchor_id
                for reference in unit.source_references
                if reference.anchor_id is not None
            }
        )
        and anchors.issubset(admitted)
    )


def ranked_unit_ids(
    build: ArticleGraphBuildResult,
    knowledge_unit_ids: frozenset[str],
    anchor_to_unit: dict[str, str],
    locator_packet: SemanticEvidencePacket | None,
) -> tuple[tuple[str, ...], frozenset[str]]:
    locator_ids: list[str] = []
    if locator_packet is not None:
        ordered_anchor_ids = tuple(hit.anchor_id for hit in locator_packet.hits) or tuple(
            anchor.anchor_id for anchor in locator_packet.anchors
        )
        locator_ids.extend(
            unit_id
            for anchor_id in ordered_anchor_ids
            if (unit_id := anchor_to_unit.get(anchor_id)) is not None
            and unit_id in knowledge_unit_ids
        )
    stage_ordered = tuple(
        unit.unit_id
        for unit in sorted(
            build.unitization.units,
            key=lambda item: (item.ordinal, item.unit_id),
        )
        if unit.unit_id in knowledge_unit_ids
    )
    ordered = tuple(dict.fromkeys(locator_ids or stage_ordered))
    return ordered, frozenset(locator_ids)


def apply_rescue_ladder(
    build: ArticleGraphBuildResult,
    ranked_ids: tuple[str, ...],
    eligible_unit_ids: frozenset[str],
    anchor_to_unit: dict[str, str],
    context: StageContext,
) -> tuple[str, ...]:
    level = _RESCUE_ORDER[context.rescue_level]
    unit_by_id = {unit.unit_id: unit for unit in build.unitization.units}
    children: dict[str, list[str]] = {}
    for source_unit in build.unitization.units:
        if source_unit.parent_unit_id is not None:
            children.setdefault(source_unit.parent_unit_id, []).append(source_unit.unit_id)
    ordered = list(ranked_ids)
    seeds = tuple(ranked_ids)
    if level >= 1:
        for unit_id in seeds:
            neighbor_unit = unit_by_id.get(unit_id)
            if neighbor_unit is None:
                continue
            ordered.extend(
                item
                for item in (
                    neighbor_unit.previous_unit_id,
                    neighbor_unit.next_unit_id,
                )
                if item is not None and item in eligible_unit_ids
            )
    if level >= 2:
        for unit_id in seeds:
            structure_unit = unit_by_id.get(unit_id)
            if structure_unit is None:
                continue
            if (
                structure_unit.parent_unit_id is not None
                and structure_unit.parent_unit_id in eligible_unit_ids
            ):
                ordered.append(structure_unit.parent_unit_id)
            ordered.extend(
                child for child in children.get(unit_id, ()) if child in eligible_unit_ids
            )
    if level >= 3:
        ordered.extend(
            targeted_unit_id
            for anchor_id in context.targeted_anchor_ids
            if (targeted_unit_id := anchor_to_unit.get(anchor_id)) is not None
            and targeted_unit_id in eligible_unit_ids
        )
    if level >= 4:
        ordered.extend(
            unit.unit_id
            for unit in sorted(
                build.unitization.units,
                key=lambda item: (item.ordinal, item.unit_id),
            )
            if unit.unit_id in eligible_unit_ids
        )
    return tuple(dict.fromkeys(ordered))

"""Relation reconciliation phase for deterministic canonicalization."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from readwelt.extraction import valid_relation_kind

from ._audit import conflict, decision
from ._normalization import merge_attributes, sorted_union
from .confidence import confidence_lineage, decision_confidence
from .digest import stable_identifier
from .models import (
    ArticleEdge,
    CanonicalizationPhase,
    CanonicalizationPolicy,
    ConflictRecord,
    EpistemicStatus,
    MergeDecision,
    MergeOutcome,
)


def reconcile_relations(
    candidates: tuple[dict[str, Any], ...],
    candidate_to_node: Mapping[str, str],
    policy: CanonicalizationPolicy,
) -> tuple[
    tuple[ArticleEdge, ...],
    tuple[MergeDecision, ...],
    tuple[ConflictRecord, ...],
]:
    valid_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    decisions: list[MergeDecision] = []
    conflicts: list[ConflictRecord] = []
    for candidate in candidates:
        if not valid_relation_kind(candidate["relation"]):
            rejected = decision(
                CanonicalizationPhase.RELATION_RECONCILIATION,
                MergeOutcome.REJECT,
                (candidate["candidate_id"],),
                (),
                ("unknown_unnamespaced_relation_kind",),
                (*candidate["source_unit_ids"], *candidate["source_element_ids"]),
                policy,
                0.0,
            )
            decisions.append(rejected)
            conflicts.append(
                conflict(
                    CanonicalizationPhase.RELATION_RECONCILIATION,
                    rejected.candidate_ids,
                    "relation is outside the closed taxonomy",
                    rejected.evidence_refs,
                    rejected,
                )
            )
            continue
        source_id = candidate_to_node.get(candidate["source_candidate_id"])
        target_id = candidate_to_node.get(candidate["target_candidate_id"])
        if (
            source_id is not None
            and target_id is not None
            and (candidate["source_unit_ids"] or candidate["source_element_ids"])
        ):
            valid_groups[(candidate["relation"], source_id, target_id)].append(candidate)
            continue
        invalid_reason = (
            "relation_endpoint_unresolved"
            if source_id is None or target_id is None
            else "grounding_required_but_missing"
        )
        rejected = decision(
            CanonicalizationPhase.RELATION_RECONCILIATION,
            MergeOutcome.REJECT,
            (candidate["candidate_id"],),
            (),
            (invalid_reason,),
            (*candidate["source_unit_ids"], *candidate["source_element_ids"]),
            policy,
            1.0,
        )
        decisions.append(rejected)
        conflicts.append(
            conflict(
                CanonicalizationPhase.RELATION_RECONCILIATION,
                rejected.candidate_ids,
                invalid_reason,
                rejected.evidence_refs,
                rejected,
            )
        )

    edges: list[ArticleEdge] = []
    for key in sorted(valid_groups):
        group_edges, merge_decision, group_conflict = _reconcile_group(
            key, sorted(valid_groups[key], key=lambda item: item["candidate_id"]), policy
        )
        edges.extend(group_edges)
        decisions.append(merge_decision)
        if group_conflict is not None:
            conflicts.append(group_conflict)
    return (
        tuple(sorted(edges, key=lambda item: item.edge_id)),
        tuple(decisions),
        tuple(conflicts),
    )


def _reconcile_group(
    key: tuple[str, str, str],
    group: list[dict[str, Any]],
    policy: CanonicalizationPolicy,
) -> tuple[list[ArticleEdge], MergeDecision, ConflictRecord | None]:
    ambiguous = any(item["ambiguity"] for item in group)
    merge_group = len(group) > 1 and not ambiguous
    partitions = (group,) if merge_group else tuple((item,) for item in group)
    edges: list[ArticleEdge] = []
    for partition in partitions:
        candidate_ids = tuple(item["candidate_id"] for item in partition)
        score, method, sources = confidence_lineage(partition)
        edges.append(
            ArticleEdge(
                edge_id=stable_identifier("canonical_edge", policy.policy_id, key, candidate_ids),
                relation=key[0],
                source_node_id=key[1],
                target_node_id=key[2],
                epistemic_status=EpistemicStatus.CANONICALIZED,
                candidate_ids=candidate_ids,
                source_unit_ids=sorted_union(item["source_unit_ids"] for item in partition),
                source_element_ids=sorted_union(item["source_element_ids"] for item in partition),
                confidence=score,
                confidence_method=method,
                confidence_sources=sources,
                ambiguity=sorted_union(item["ambiguity"] for item in partition),
                attributes=merge_attributes(partition),
            )
        )
    outcome = (
        MergeOutcome.MERGE
        if merge_group
        else MergeOutcome.DEFER
        if ambiguous
        else MergeOutcome.KEEP_SEPARATE
    )
    reasons = (
        ("same_relation_and_canonical_endpoints",)
        if merge_group
        else ("relation_ambiguity_requires_explicit_resolution",)
        if ambiguous
        else ("single_grounded_relation",)
    )
    merge_decision = decision(
        CanonicalizationPhase.RELATION_RECONCILIATION,
        outcome,
        tuple(item["candidate_id"] for item in group),
        tuple(edge.edge_id for edge in edges),
        reasons,
        sorted_union((*item["source_unit_ids"], *item["source_element_ids"]) for item in group),
        policy,
        decision_confidence(group),
    )
    group_conflict = (
        conflict(
            CanonicalizationPhase.RELATION_RECONCILIATION,
            merge_decision.candidate_ids,
            "relation ambiguity preserved",
            merge_decision.evidence_refs,
            merge_decision,
        )
        if outcome is MergeOutcome.DEFER
        else None
    )
    return edges, merge_decision, group_conflict

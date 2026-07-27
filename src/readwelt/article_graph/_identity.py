"""Conservative identity resolution preserving every mention."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from readwelt.extraction import valid_candidate_kind

from ._audit import conflict, decision
from ._normalization import identity_key, merge_attributes, sorted_union
from .confidence import confidence_lineage, decision_confidence
from .digest import stable_identifier
from .models import (
    ArticleNode,
    CanonicalizationPhase,
    CanonicalizationPolicy,
    ConflictRecord,
    EpistemicStatus,
    Mention,
    MergeDecision,
    MergeOutcome,
)


def resolve_identities(
    candidates: tuple[dict[str, Any], ...],
    policy: CanonicalizationPolicy,
) -> tuple[
    tuple[Mention, ...],
    tuple[ArticleNode, ...],
    dict[str, str],
    tuple[MergeDecision, ...],
    tuple[ConflictRecord, ...],
]:
    mentions, accepted, decisions, conflicts = _ground_candidates(candidates, policy)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in accepted:
        identity_text = candidate["label"] or candidate["text"] or candidate["candidate_id"]
        groups[
            (
                candidate["kind"],
                identity_key(identity_text, policy.case_sensitive_identity),
            )
        ].append(candidate)

    nodes: list[ArticleNode] = []
    candidate_to_node: dict[str, str] = {}
    mention_by_candidate = {item.candidate_id: item for item in mentions}
    for key in sorted(groups):
        group_nodes, group_map, merge_decision, group_conflict = _resolve_group(
            key,
            sorted(groups[key], key=lambda item: item["candidate_id"]),
            mention_by_candidate,
            policy,
        )
        nodes.extend(group_nodes)
        candidate_to_node.update(group_map)
        decisions.append(merge_decision)
        if group_conflict is not None:
            conflicts.append(group_conflict)
    return (
        tuple(sorted(mentions, key=lambda item: item.mention_id)),
        tuple(sorted(nodes, key=lambda item: item.node_id)),
        candidate_to_node,
        tuple(decisions),
        tuple(conflicts),
    )


def _ground_candidates(
    candidates: tuple[dict[str, Any], ...],
    policy: CanonicalizationPolicy,
) -> tuple[
    list[Mention],
    list[dict[str, Any]],
    list[MergeDecision],
    list[ConflictRecord],
]:
    mentions: list[Mention] = []
    accepted: list[dict[str, Any]] = []
    decisions: list[MergeDecision] = []
    conflicts: list[ConflictRecord] = []
    for candidate in candidates:
        if not valid_candidate_kind(candidate["kind"]):
            rejected = decision(
                CanonicalizationPhase.IDENTITY_RESOLUTION,
                MergeOutcome.REJECT,
                (candidate["candidate_id"],),
                (),
                ("unknown_unnamespaced_candidate_kind",),
                (*candidate["source_unit_ids"], *candidate["source_element_ids"]),
                policy,
                0.0,
            )
            decisions.append(rejected)
            conflicts.append(
                conflict(
                    CanonicalizationPhase.IDENTITY_RESOLUTION,
                    (candidate["candidate_id"],),
                    "candidate kind is outside the closed taxonomy",
                    rejected.evidence_refs,
                    rejected,
                )
            )
            continue
        score, method, sources = confidence_lineage((candidate,))
        mentions.append(
            Mention(
                mention_id=stable_identifier("mention", candidate["candidate_id"]),
                candidate_id=candidate["candidate_id"],
                kind=candidate["kind"],
                label=candidate["label"],
                text=candidate["text"],
                epistemic_status=candidate["epistemic_status"],
                source_unit_ids=candidate["source_unit_ids"],
                source_element_ids=candidate["source_element_ids"],
                confidence=score,
                confidence_method=method,
                confidence_sources=sources,
                ambiguity=candidate["ambiguity"],
                attributes=candidate["attributes"],
            )
        )
        if (
            candidate["kind"] not in policy.source_required_kinds
            or candidate["source_unit_ids"]
            or candidate["source_element_ids"]
        ):
            accepted.append(candidate)
            continue
        rejected = decision(
            CanonicalizationPhase.IDENTITY_RESOLUTION,
            MergeOutcome.REJECT,
            (candidate["candidate_id"],),
            (),
            ("grounding_required_but_missing",),
            (),
            policy,
            1.0,
        )
        decisions.append(rejected)
        conflicts.append(
            conflict(
                CanonicalizationPhase.IDENTITY_RESOLUTION,
                (candidate["candidate_id"],),
                "source-required candidate has no known source unit or element",
                (),
                rejected,
            )
        )
    return mentions, accepted, decisions, conflicts


def _resolve_group(
    key: tuple[str, str],
    group: list[dict[str, Any]],
    mentions: dict[str, Mention],
    policy: CanonicalizationPolicy,
) -> tuple[list[ArticleNode], dict[str, str], MergeDecision, ConflictRecord | None]:
    ambiguous = any(item["ambiguity"] for item in group)
    low_confidence = any(
        item["confidence"] is None or item["confidence"] < policy.merge_confidence_threshold
        for item in group
    )
    common_grounding = _grounding_keys(group[0])
    for item in group[1:]:
        common_grounding.intersection_update(_grounding_keys(item))
    cross_unit_identity = len(group) > 1 and not common_grounding
    merge_group = (
        len(group) > 1 and not ambiguous and not low_confidence and not cross_unit_identity
    )
    partitions = (group,) if merge_group else tuple((item,) for item in group)
    nodes: list[ArticleNode] = []
    candidate_to_node: dict[str, str] = {}
    for partition in partitions:
        candidate_ids = tuple(item["candidate_id"] for item in partition)
        node_id = stable_identifier(
            "canonical_node",
            policy.policy_id,
            key,
            candidate_ids if not merge_group else "merged",
        )
        representative = partition[0]
        score, method, sources = confidence_lineage(
            partition,
            {candidate_id: mentions[candidate_id].mention_id for candidate_id in candidate_ids},
        )
        nodes.append(
            ArticleNode(
                node_id=node_id,
                kind=representative["kind"],
                label=representative["label"] or representative["text"],
                epistemic_status=EpistemicStatus.CANONICALIZED,
                mention_ids=tuple(
                    mentions[candidate_id].mention_id for candidate_id in candidate_ids
                ),
                source_unit_ids=sorted_union(item["source_unit_ids"] for item in partition),
                source_element_ids=sorted_union(item["source_element_ids"] for item in partition),
                attributes=merge_attributes(partition),
                confidence=score,
                confidence_method=method,
                confidence_sources=sources,
                ambiguity=sorted_union(item["ambiguity"] for item in partition),
                candidate_ids=candidate_ids,
            )
        )
        candidate_to_node.update({candidate_id: node_id for candidate_id in candidate_ids})

    outcome, reasons = _identity_outcome(
        group, merge_group, ambiguous, low_confidence, cross_unit_identity
    )
    evidence = sorted_union(
        (*item["source_unit_ids"], *item["source_element_ids"]) for item in group
    )
    merge_decision = decision(
        CanonicalizationPhase.IDENTITY_RESOLUTION,
        outcome,
        tuple(item["candidate_id"] for item in group),
        tuple(dict.fromkeys(candidate_to_node.values())),
        reasons,
        evidence,
        policy,
        decision_confidence(group),
    )
    group_conflict = (
        conflict(
            CanonicalizationPhase.IDENTITY_RESOLUTION,
            merge_decision.candidate_ids,
            "identity ambiguity preserved",
            evidence,
            merge_decision,
        )
        if outcome is MergeOutcome.DEFER
        else None
    )
    return nodes, candidate_to_node, merge_decision, group_conflict


def _grounding_keys(candidate: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        *(("unit", item) for item in candidate["source_unit_ids"]),
        *(("element", item) for item in candidate["source_element_ids"]),
    }


def _identity_outcome(
    group: list[dict[str, Any]],
    merge_group: bool,
    ambiguous: bool,
    low_confidence: bool,
    cross_unit_identity: bool,
) -> tuple[MergeOutcome, tuple[str, ...]]:
    if merge_group:
        return MergeOutcome.MERGE, ("normalized_kind_and_label_match_with_shared_source_unit",)
    if len(group) > 1 and ambiguous:
        return MergeOutcome.DEFER, ("candidate_ambiguity_requires_explicit_resolution",)
    if cross_unit_identity:
        return MergeOutcome.DEFER, ("same_name_across_source_units_is_not_identity_evidence",)
    if len(group) > 1 and low_confidence:
        return MergeOutcome.KEEP_SEPARATE, ("merge_confidence_below_policy_threshold",)
    return MergeOutcome.KEEP_SEPARATE, ("no_supported_identity_peer",)

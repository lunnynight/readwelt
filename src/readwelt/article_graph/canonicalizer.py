"""Deterministic, conservative three-phase canonicalization."""

from __future__ import annotations

from collections.abc import Iterable

from ._claims import assemble_claims
from ._identity import resolve_identities
from ._normalization import normalize_extraction, unique_candidates
from ._phases import reconcile_relations
from .digest import content_digest
from .models import (
    ARTICLE_GRAPH_SCHEMA_VERSION,
    ArticleGraph,
    CanonicalizationPolicy,
    CanonicalizationResult,
    MergeOutcome,
    MergeReport,
)
from .protocols import ExtractionInput


class Canonicalizer:
    """Pure canonical projection with no network, model, or clock dependency."""

    schema_version = ARTICLE_GRAPH_SCHEMA_VERSION

    def canonicalize(
        self,
        extractions: Iterable[ExtractionInput],
        policy: CanonicalizationPolicy | None = None,
    ) -> CanonicalizationResult:
        selected_policy = policy or CanonicalizationPolicy()
        normalized = tuple(
            sorted(
                (normalize_extraction(item) for item in extractions),
                key=lambda item: item["extraction_id"],
            )
        )
        snapshot_ids = {item["snapshot_id"] for item in normalized}
        if not normalized:
            raise ValueError("canonicalization requires at least one extraction")
        if len(snapshot_ids) != 1:
            raise ValueError("all extraction artifacts must belong to one snapshot")
        snapshot_id = next(iter(snapshot_ids))

        candidates = unique_candidates(
            candidate for extraction in normalized for candidate in extraction["nodes"]
        )
        relation_candidates = unique_candidates(
            candidate for extraction in normalized for candidate in extraction["edges"]
        )
        mentions, nodes, candidate_to_node, identity_decisions, identity_conflicts = (
            resolve_identities(candidates, selected_policy)
        )
        edges, relation_decisions, relation_conflicts = reconcile_relations(
            relation_candidates,
            candidate_to_node,
            selected_policy,
        )
        claims, claim_decisions, claim_conflicts = assemble_claims(
            candidates,
            {mention.candidate_id: mention for mention in mentions},
            candidate_to_node,
            selected_policy,
        )

        decisions = tuple(
            sorted(
                (*identity_decisions, *relation_decisions, *claim_decisions),
                key=lambda item: item.decision_id,
            )
        )
        conflicts = tuple(
            sorted(
                (*identity_conflicts, *relation_conflicts, *claim_conflicts),
                key=lambda item: item.conflict_id,
            )
        )
        rejected = tuple(
            sorted(
                {
                    candidate_id
                    for decision in decisions
                    if decision.outcome is MergeOutcome.REJECT
                    for candidate_id in decision.candidate_ids
                }
            )
        )
        deferred = tuple(
            sorted(
                {
                    candidate_id
                    for decision in decisions
                    if decision.outcome is MergeOutcome.DEFER
                    for candidate_id in decision.candidate_ids
                }
            )
        )
        report_payload = {
            "schema_version": "merge-report.v1",
            "policy_id": selected_policy.policy_id,
            "decisions": decisions,
            "conflicts": conflicts,
            "rejected_candidate_ids": rejected,
            "deferred_candidate_ids": deferred,
        }
        report = MergeReport(
            schema_version="merge-report.v1",
            policy_id=selected_policy.policy_id,
            decisions=decisions,
            conflicts=conflicts,
            rejected_candidate_ids=rejected,
            deferred_candidate_ids=deferred,
            content_digest=content_digest(report_payload),
        )

        available = tuple(
            sorted(
                {
                    str(capability)
                    for extraction in normalized
                    for capability in extraction["available_capabilities"]
                }
            )
        )
        missing = tuple(
            sorted(
                {
                    str(capability)
                    for extraction in normalized
                    for capability in extraction["missing_capabilities"]
                }
            )
        )
        graph_payload = {
            "schema_version": self.schema_version,
            "snapshot_id": snapshot_id,
            "mentions": mentions,
            "nodes": nodes,
            "edges": edges,
            "claims": claims,
            "available_capabilities": available,
            "missing_capabilities": missing,
        }
        graph = ArticleGraph(
            schema_version=self.schema_version,
            snapshot_id=snapshot_id,
            mentions=mentions,
            nodes=nodes,
            edges=edges,
            claims=claims,
            available_capabilities=available,
            missing_capabilities=missing,
            content_digest=content_digest(graph_payload),
        )
        return CanonicalizationResult(graph=graph, merge_report=report)

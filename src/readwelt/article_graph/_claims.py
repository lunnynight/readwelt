"""Claim assembly phase for canonicalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._audit import conflict, decision
from ._normalization import identity_key
from .confidence import confidence_lineage, decision_confidence
from .digest import stable_identifier
from .models import (
    CanonicalizationPhase,
    CanonicalizationPolicy,
    Claim,
    ConflictRecord,
    EpistemicStatus,
    Mention,
    MergeDecision,
    MergeOutcome,
)


def assemble_claims(
    candidates: tuple[dict[str, Any], ...],
    mentions: Mapping[str, Mention],
    candidate_to_node: Mapping[str, str],
    policy: CanonicalizationPolicy,
) -> tuple[
    tuple[Claim, ...],
    tuple[MergeDecision, ...],
    tuple[ConflictRecord, ...],
]:
    claims: list[Claim] = []
    decisions: list[MergeDecision] = []
    conflicts: list[ConflictRecord] = []
    for candidate in candidates:
        if candidate["kind"] != "claim" or candidate["candidate_id"] not in candidate_to_node:
            continue
        text = candidate["text"] or candidate["label"]
        if not text:
            merge_decision = decision(
                CanonicalizationPhase.CLAIM_ASSEMBLY,
                MergeOutcome.REJECT,
                (candidate["candidate_id"],),
                (),
                ("claim_text_missing",),
                (*candidate["source_unit_ids"], *candidate["source_element_ids"]),
                policy,
                1.0,
            )
            decisions.append(merge_decision)
            conflicts.append(
                conflict(
                    CanonicalizationPhase.CLAIM_ASSEMBLY,
                    merge_decision.candidate_ids,
                    "claim candidate has no text",
                    merge_decision.evidence_refs,
                    merge_decision,
                )
            )
            continue
        claim_id = stable_identifier(
            "canonical_claim",
            policy.policy_id,
            identity_key(text, policy.case_sensitive_identity),
            candidate["candidate_id"],
        )
        mention = mentions[candidate["candidate_id"]]
        score, method, sources = confidence_lineage(
            (candidate,),
            {candidate["candidate_id"]: mention.mention_id},
        )
        claim = Claim(
            claim_id=claim_id,
            text=text,
            epistemic_status=EpistemicStatus.CANONICALIZED,
            mention_ids=(mention.mention_id,),
            evidence_unit_ids=candidate["source_unit_ids"],
            evidence_element_ids=candidate["source_element_ids"],
            confidence=score,
            confidence_method=method,
            confidence_sources=sources,
            candidate_ids=(candidate["candidate_id"],),
            ambiguity=candidate["ambiguity"],
            attributes=candidate["attributes"],
        )
        claims.append(claim)
        outcome = MergeOutcome.DEFER if candidate["ambiguity"] else MergeOutcome.KEEP_SEPARATE
        merge_decision = decision(
            CanonicalizationPhase.CLAIM_ASSEMBLY,
            outcome,
            (candidate["candidate_id"],),
            (claim_id,),
            (
                "claim_ambiguity_requires_explicit_resolution"
                if candidate["ambiguity"]
                else "grounded_claim_assembled",
            ),
            (*candidate["source_unit_ids"], *candidate["source_element_ids"]),
            policy,
            decision_confidence((candidate,)),
        )
        decisions.append(merge_decision)
        if outcome is MergeOutcome.DEFER:
            conflicts.append(
                conflict(
                    CanonicalizationPhase.CLAIM_ASSEMBLY,
                    merge_decision.candidate_ids,
                    "claim ambiguity preserved",
                    merge_decision.evidence_refs,
                    merge_decision,
                )
            )
    return (
        tuple(sorted(claims, key=lambda item: item.claim_id)),
        tuple(decisions),
        tuple(conflicts),
    )

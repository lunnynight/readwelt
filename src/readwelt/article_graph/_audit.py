"""Internal construction of content-addressed decisions and conflicts."""

from __future__ import annotations

from .digest import content_digest, stable_identifier
from .models import (
    CanonicalizationPhase,
    CanonicalizationPolicy,
    ConflictRecord,
    MergeDecision,
    MergeOutcome,
)


def decision(
    phase: CanonicalizationPhase,
    outcome: MergeOutcome,
    candidate_ids: tuple[str, ...],
    canonical_ids: tuple[str, ...],
    reasons: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    policy: CanonicalizationPolicy,
    confidence: float,
) -> MergeDecision:
    sorted_candidate_ids = tuple(sorted(candidate_ids))
    sorted_canonical_ids = tuple(sorted(canonical_ids))
    sorted_evidence_refs = tuple(sorted(evidence_refs))
    payload = {
        "phase": phase,
        "outcome": outcome,
        "candidate_ids": sorted_candidate_ids,
        "canonical_object_ids": sorted_canonical_ids,
        "reasons": reasons,
        "evidence_refs": sorted_evidence_refs,
        "policy_id": policy.policy_id,
        "confidence": confidence,
    }
    digest = content_digest(payload)
    return MergeDecision(
        decision_id=stable_identifier("merge_decision", digest),
        phase=phase,
        outcome=outcome,
        candidate_ids=sorted_candidate_ids,
        canonical_object_ids=sorted_canonical_ids,
        reasons=reasons,
        evidence_refs=sorted_evidence_refs,
        policy_id=policy.policy_id,
        confidence=confidence,
        content_digest=digest,
    )


def conflict(
    phase: CanonicalizationPhase,
    candidate_ids: tuple[str, ...],
    reason: str,
    evidence_refs: tuple[str, ...],
    merge_decision: MergeDecision,
) -> ConflictRecord:
    sorted_candidate_ids = tuple(sorted(candidate_ids))
    sorted_evidence_refs = tuple(sorted(evidence_refs))
    payload = {
        "phase": phase,
        "candidate_ids": sorted_candidate_ids,
        "reason": reason,
        "evidence_refs": sorted_evidence_refs,
        "decision_id": merge_decision.decision_id,
        "resolution": "unresolved",
    }
    return ConflictRecord(
        conflict_id=stable_identifier("conflict", content_digest(payload)),
        phase=phase,
        candidate_ids=sorted_candidate_ids,
        reason=reason,
        evidence_refs=sorted_evidence_refs,
        decision_id=merge_decision.decision_id,
        resolution="unresolved",
        content_digest=content_digest(payload),
    )

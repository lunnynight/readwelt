"""Immutable contracts for the six-stage reverse-reading pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from readwelt.domain.spans import SpanAnchor
from readwelt.domain.status import EpistemicStatus, ExecutionStatus


class ReadingStage(StrEnum):
    MAINLINE = "stage_1_mainline"
    STRUCTURE = "stage_2_structure"
    DECOMPRESSION = "stage_3_decompression"
    AUTHOR_MODEL = "stage_4_author_model"
    BOUNDARIES = "stage_5_boundaries"
    TRANSFER = "stage_6_transfer"


class LedgerDecision(StrEnum):
    ACCEPTED = "accepted"
    QUALIFIED = "qualified"
    CONTESTED = "contested"
    REJECTED = "rejected"
    UNDERDETERMINED = "underdetermined"


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    """Bounded evidence made available to one pipeline execution.

    External evidence is deliberately separate so the engine can prove that it
    was not exposed to stages 1 and 2.
    """

    run_id: str
    anchors: tuple[SpanAnchor, ...]
    retrieval_queries: tuple[str, ...] = ()
    omitted_sections: tuple[str, ...] = ()
    omitted_anchor_ids: tuple[str, ...] = ()
    coverage_complete: bool = True
    external_evidence: tuple[str, ...] = ()
    token_budget: int = 0

    def __post_init__(self) -> None:
        if self.token_budget < 0:
            raise ValueError("token_budget cannot be negative")
        if len({anchor.anchor_id for anchor in self.anchors}) != len(self.anchors):
            raise ValueError("evidence anchor ids must be unique")
        if len(set(self.omitted_anchor_ids)) != len(self.omitted_anchor_ids):
            raise ValueError("omitted evidence anchor ids must be unique")


@dataclass(frozen=True, slots=True)
class ReadingClaim:
    claim_id: str
    text: str
    stage: ReadingStage
    anchor_ids: tuple[str, ...]
    decision: LedgerDecision
    source_claim_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id or not self.text.strip():
            raise ValueError("claim_id and text are required")
        if len(set(self.anchor_ids)) != len(self.anchor_ids):
            raise ValueError("claim anchor ids must be unique")


@dataclass(frozen=True, slots=True)
class ReadingGap:
    gap_id: str
    kind: str
    description: str
    origin_stage: ReadingStage
    affected_claim_ids: tuple[str, ...] = ()
    critical: bool = False
    repairable: bool = False
    resolved: bool = False


@dataclass(frozen=True, slots=True)
class StageArtifact:
    artifact_id: str
    run_id: str
    stage: ReadingStage
    claims: tuple[ReadingClaim, ...]
    gaps: tuple[ReadingGap, ...]
    warnings: tuple[str, ...]
    input_artifact_ids: tuple[str, ...]
    provider: str
    model: str | None
    status: EpistemicStatus
    content_digest: str
    provider_provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")
        if any(claim.stage is not self.stage for claim in self.claims):
            raise ValueError("artifact claims must belong to its stage")
        if any(gap.origin_stage is not self.stage for gap in self.gaps):
            raise ValueError("artifact gaps must belong to its stage")

    @property
    def accepted_claims(self) -> tuple[ReadingClaim, ...]:
        return tuple(
            claim
            for claim in self.claims
            if claim.decision in (LedgerDecision.ACCEPTED, LedgerDecision.QUALIFIED)
        )


@dataclass(frozen=True, slots=True)
class LedgerLine:
    claim_id: str
    stage: ReadingStage
    decision: LedgerDecision
    supporting_anchor_ids: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReadingClaimLedger:
    ledger_id: str
    run_id: str
    policy_version: str
    lines: tuple[LedgerLine, ...]
    unresolved_claim_ids: tuple[str, ...]
    rejected_claim_ids: tuple[str, ...]
    content_digest: str

    def __post_init__(self) -> None:
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")


@dataclass(frozen=True, slots=True)
class ReadingBundle:
    run_id: str
    snapshot_id: str
    artifacts: tuple[StageArtifact, ...]
    ledger: ReadingClaimLedger
    transitions: tuple[str, ...]
    execution_status: ExecutionStatus
    epistemic_status: EpistemicStatus
    failure: str | None = None

    def __post_init__(self) -> None:
        if self.execution_status is ExecutionStatus.FAILED and self.failure is None:
            raise ValueError("failed bundle must include a failure")
        if self.execution_status is not ExecutionStatus.FAILED and self.failure is not None:
            raise ValueError("only failed bundles may include a failure")

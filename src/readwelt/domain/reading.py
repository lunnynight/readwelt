"""Immutable contracts for the six-stage reverse-reading pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from readwelt.domain.ids import stable_id
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


class StageInputStatus(StrEnum):
    """Whether a stage candidate was produced from complete bounded input."""

    COMPLETE = "complete"
    PROVISIONAL = "provisional"
    BLOCKED = "blocked"


class SourceCitationKind(StrEnum):
    """Provider-visible identities that can ground a stage conclusion."""

    ANCHOR = "anchor"
    UNIT = "unit"
    RANGE = "range"
    ELEMENT = "element"
    GRAPH_OBJECT = "graph_object"


@dataclass(frozen=True, slots=True)
class SourceCitation:
    """Typed, provenance-closed reference admitted to one stage request."""

    kind: SourceCitationKind
    identity: str
    schema_version: str = "source-citation.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "source-citation.v1":
            raise ValueError(f"unsupported source citation: {self.schema_version}")
        if not self.identity.strip():
            raise ValueError("source citation identity is required")


@dataclass(frozen=True, slots=True)
class ExternalEvidence:
    """Typed external material available for StageView policy admission."""

    evidence_id: str
    content: str
    provenance: tuple[tuple[str, str], ...]
    schema_version: str = "external-evidence.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "external-evidence.v1":
            raise ValueError(f"unsupported external evidence: {self.schema_version}")
        if not self.evidence_id or not self.content.strip():
            raise ValueError("external evidence identity and content are required")
        if not self.provenance:
            raise ValueError("external evidence provenance is required")

    @classmethod
    def from_legacy(cls, content: str) -> ExternalEvidence:
        """Normalize the historical string form at the domain boundary."""

        return cls(
            evidence_id=stable_id("external_evidence", content),
            content=content,
            provenance=(("origin", "legacy_evidence_packet"),),
        )


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    anchor_id: str
    section_id: str
    lexical_rank: int
    lexical_score: float
    dense_rank: int | None
    dense_score: float | None
    fused_score: float


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
    external_evidence: tuple[ExternalEvidence, ...] = ()
    token_budget: int = 0
    stage: ReadingStage | None = None
    retrieval_backend: str = "rust-bm25-v1"
    retrieval_hits: tuple[RetrievalHit, ...] = ()

    def __post_init__(self) -> None:
        normalized_external = tuple(
            ExternalEvidence.from_legacy(item) if isinstance(item, str) else item
            for item in self.external_evidence
        )
        if any(not isinstance(item, ExternalEvidence) for item in normalized_external):
            raise ValueError("external evidence must use the typed evidence contract")
        if len({item.evidence_id for item in normalized_external}) != len(normalized_external):
            raise ValueError("external evidence ids must be unique")
        object.__setattr__(self, "external_evidence", normalized_external)
        if self.token_budget < 0:
            raise ValueError("token_budget cannot be negative")
        if len({anchor.anchor_id for anchor in self.anchors}) != len(self.anchors):
            raise ValueError("evidence anchor ids must be unique")
        if len(set(self.omitted_anchor_ids)) != len(self.omitted_anchor_ids):
            raise ValueError("omitted evidence anchor ids must be unique")
        hit_ids = tuple(hit.anchor_id for hit in self.retrieval_hits)
        if len(set(hit_ids)) != len(hit_ids):
            raise ValueError("retrieval hit anchor ids must be unique")
        if not set(hit_ids).issubset(anchor.anchor_id for anchor in self.anchors):
            raise ValueError("retrieval hits must refer to admitted evidence anchors")


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
    source_citations: tuple[SourceCitation, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id or not self.text.strip():
            raise ValueError("claim_id and text are required")
        if len(set(self.anchor_ids)) != len(self.anchor_ids):
            raise ValueError("claim anchor ids must be unique")
        citations = self.source_citations
        if not citations:
            citations = tuple(
                SourceCitation(SourceCitationKind.ANCHOR, anchor_id)
                for anchor_id in self.anchor_ids
            )
            object.__setattr__(self, "source_citations", citations)
        if len(set(citations)) != len(citations):
            raise ValueError("claim source citations must be unique")
        cited_anchor_ids = tuple(
            citation.identity
            for citation in citations
            if citation.kind is SourceCitationKind.ANCHOR
        )
        if self.anchor_ids and cited_anchor_ids != self.anchor_ids:
            raise ValueError("claim anchor ids must match typed anchor citations")
        if not self.anchor_ids and cited_anchor_ids:
            object.__setattr__(self, "anchor_ids", cited_anchor_ids)


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
class StageInputState:
    """Versioned settlement state for the exact StageView used by a candidate."""

    status: StageInputStatus
    stage_view_digest: str
    coverage_digest: str | None
    continuation_digest: str | None
    blocking_reasons: tuple[str, ...]
    unresolved_critical_ids: tuple[str, ...]
    schema_version: str = "stage-input-state.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "stage-input-state.v1":
            raise ValueError(f"unsupported stage input state: {self.schema_version}")
        if not self.stage_view_digest.startswith("sha256:"):
            raise ValueError("stage_view_digest must be a sha256 digest")
        for digest in (self.coverage_digest, self.continuation_digest):
            if digest is not None and not digest.startswith("sha256:"):
                raise ValueError("stage input lineage digests must be sha256 digests")
        if self.status is StageInputStatus.COMPLETE and (
            self.continuation_digest is not None
            or self.blocking_reasons
            or self.unresolved_critical_ids
        ):
            raise ValueError("complete stage input cannot retain unresolved traversal state")


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
    input_state: StageInputState | None = None

    def __post_init__(self) -> None:
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")
        if any(claim.stage is not self.stage for claim in self.claims):
            raise ValueError("artifact claims must belong to its stage")
        if any(gap.origin_stage is not self.stage for gap in self.gaps):
            raise ValueError("artifact gaps must belong to its stage")

    @property
    def accepted_claims(self) -> tuple[ReadingClaim, ...]:
        if not self.fully_settled:
            return ()
        return tuple(
            claim
            for claim in self.claims
            if claim.decision in (LedgerDecision.ACCEPTED, LedgerDecision.QUALIFIED)
        )

    @property
    def fully_settled(self) -> bool:
        """Historical artifacts without the v1 state remain complete."""

        return self.input_state is None or self.input_state.status is StageInputStatus.COMPLETE


@dataclass(frozen=True, slots=True)
class LedgerLine:
    claim_id: str
    stage: ReadingStage
    decision: LedgerDecision
    supporting_anchor_ids: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    source_citations: tuple[SourceCitation, ...] = ()


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

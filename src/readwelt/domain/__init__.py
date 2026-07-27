"""Stable domain contracts exposed by Readwelt."""

from readwelt.domain.artifacts import ArtifactRef, ArtifactStatus
from readwelt.domain.documents import (
    DocumentSection,
    SourceDocumentSnapshot,
    SourceElement,
    SourceElementProjectionStatus,
)
from readwelt.domain.ids import stable_id
from readwelt.domain.reading import (
    EvidencePacket,
    ExternalEvidence,
    LedgerDecision,
    LedgerLine,
    ReadingBundle,
    ReadingClaim,
    ReadingClaimLedger,
    ReadingGap,
    ReadingStage,
    RetrievalHit,
    SourceCitation,
    SourceCitationKind,
    StageArtifact,
    StageInputState,
    StageInputStatus,
)
from readwelt.domain.run import ReadingRun
from readwelt.domain.spans import SpanAnchor
from readwelt.domain.status import (
    EpistemicStatus,
    ExecutionStatus,
    ModelStatus,
    PublicationStatus,
)

__all__ = [
    "ArtifactRef",
    "ArtifactStatus",
    "DocumentSection",
    "EvidencePacket",
    "ExternalEvidence",
    "EpistemicStatus",
    "ExecutionStatus",
    "LedgerDecision",
    "LedgerLine",
    "ModelStatus",
    "PublicationStatus",
    "ReadingBundle",
    "ReadingClaim",
    "ReadingClaimLedger",
    "ReadingGap",
    "ReadingRun",
    "ReadingStage",
    "RetrievalHit",
    "SourceCitation",
    "SourceCitationKind",
    "SourceDocumentSnapshot",
    "SourceElement",
    "SourceElementProjectionStatus",
    "SpanAnchor",
    "StageArtifact",
    "StageInputState",
    "StageInputStatus",
    "stable_id",
]

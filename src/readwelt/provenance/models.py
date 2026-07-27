"""Independent provenance event schema."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from readwelt.article_graph.digest import content_digest as calculate_digest
from readwelt.article_graph.models import EpistemicStatus

PROVENANCE_SCHEMA_VERSION = "provenance-event.v1"
GENESIS_DIGEST = "sha256:" + ("0" * 64)


class ProvenanceEventType(StrEnum):
    ADOPTION = "adoption"
    UNITIZATION = "unitization"
    EXTRACTION = "extraction"
    GROUNDING = "grounding"
    CANONICALIZATION = "canonicalization"
    CONFLICT = "conflict"
    PROJECTION = "projection"


@dataclass(frozen=True, slots=True)
class ProducerIdentity:
    producer_id: str
    producer_version: str
    schema_version: str
    model_id: str | None = None
    model_revision: str | None = None

    def __post_init__(self) -> None:
        if not self.producer_id.strip() or not self.producer_version.strip():
            raise ValueError("producer identity and version are required")
        if not self.schema_version.strip():
            raise ValueError("producer schema version is required")


@dataclass(frozen=True, slots=True)
class ProvenanceEvent:
    sequence: int
    event_type: ProvenanceEventType
    timestamp: str
    producer: ProducerIdentity
    epistemic_status: EpistemicStatus
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    source_refs: tuple[str, ...]
    confidence: float
    ambiguity: tuple[str, ...]
    payload: tuple[tuple[str, Any], ...]
    previous_digest: str
    digest: str
    schema_version: str = PROVENANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("provenance sequence cannot be negative")
        if not self.timestamp.strip():
            raise ValueError("provenance timestamp is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        for value in (self.previous_digest, self.digest):
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError("provenance digests must be sha256 digests")


@dataclass(frozen=True, slots=True)
class ChainVerification:
    valid: bool
    event_count: int
    head_digest: str
    first_invalid_sequence: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProvenanceLedgerArtifact:
    """Immutable, serializer-friendly durable ledger representation."""

    schema_version: str
    events: tuple[ProvenanceEvent, ...]
    head_digest: str
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "provenance-ledger.v1":
            raise ValueError(f"unsupported provenance ledger schema: {self.schema_version}")
        expected_head = self.events[-1].digest if self.events else GENESIS_DIGEST
        if self.head_digest != expected_head:
            raise ValueError("provenance artifact head does not match its events")
        for value in (self.head_digest, self.content_digest):
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError("provenance artifact digests must be sha256 digests")
        expected_content_digest = calculate_digest(
            {
                "schema_version": self.schema_version,
                "events": self.events,
                "head_digest": self.head_digest,
            }
        )
        if self.content_digest != expected_content_digest:
            raise ValueError("provenance artifact content digest mismatch")

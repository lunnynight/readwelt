"""Append-only, content-addressed provenance ledger."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from readwelt.article_graph.digest import canonical_value, content_digest
from readwelt.article_graph.models import EpistemicStatus

from .models import (
    GENESIS_DIGEST,
    PROVENANCE_SCHEMA_VERSION,
    ChainVerification,
    ProducerIdentity,
    ProvenanceEvent,
    ProvenanceEventType,
    ProvenanceLedgerArtifact,
)


class ProvenanceLedger:
    """An in-memory append-only sequence suitable for durable serialization."""

    def __init__(self, events: Iterable[ProvenanceEvent] = ()) -> None:
        self._events: list[ProvenanceEvent] = list(events)
        verification = self.verify_chain()
        if not verification.valid:
            raise ValueError(
                f"invalid provenance chain at {verification.first_invalid_sequence}: "
                f"{verification.reason}"
            )

    @property
    def events(self) -> tuple[ProvenanceEvent, ...]:
        return tuple(self._events)

    @property
    def head_digest(self) -> str:
        return self._events[-1].digest if self._events else GENESIS_DIGEST

    def append(
        self,
        event_type: ProvenanceEventType | str,
        *,
        producer: ProducerIdentity,
        epistemic_status: EpistemicStatus | str,
        inputs: Iterable[str] = (),
        outputs: Iterable[str] = (),
        source_refs: Iterable[str] = (),
        confidence: float = 1.0,
        ambiguity: Iterable[str] = (),
        payload: Mapping[str, Any] | Iterable[tuple[str, Any]] = (),
        timestamp: str | None = None,
    ) -> ProvenanceEvent:
        """Append exactly one event and return its content identity.

        Pass ``timestamp`` when deterministic replay bytes are required.  The
        ledger never rewrites an existing timestamp or digest.
        """

        sequence = len(self._events)
        normalized_payload = _payload_tuple(payload)
        normalized_inputs = tuple(sorted(set(inputs)))
        normalized_outputs = tuple(sorted(set(outputs)))
        normalized_source_refs = tuple(sorted(set(source_refs)))
        normalized_ambiguity = tuple(sorted(set(ambiguity)))
        event_payload = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "sequence": sequence,
            "event_type": ProvenanceEventType(event_type),
            "timestamp": timestamp or datetime.now(UTC).isoformat(),
            "producer": producer,
            "epistemic_status": EpistemicStatus(epistemic_status),
            "inputs": normalized_inputs,
            "outputs": normalized_outputs,
            "source_refs": normalized_source_refs,
            "confidence": confidence,
            "ambiguity": normalized_ambiguity,
            "payload": normalized_payload,
            "previous_digest": self.head_digest,
        }
        event = ProvenanceEvent(
            sequence=sequence,
            event_type=ProvenanceEventType(event_type),
            timestamp=str(event_payload["timestamp"]),
            producer=producer,
            epistemic_status=EpistemicStatus(epistemic_status),
            inputs=normalized_inputs,
            outputs=normalized_outputs,
            source_refs=normalized_source_refs,
            confidence=confidence,
            ambiguity=normalized_ambiguity,
            payload=normalized_payload,
            previous_digest=self.head_digest,
            digest=content_digest(event_payload),
        )
        self._events.append(event)
        return event

    def verify_chain(self) -> ChainVerification:
        previous = GENESIS_DIGEST
        for expected_sequence, event in enumerate(self._events):
            if event.sequence != expected_sequence:
                return ChainVerification(
                    valid=False,
                    event_count=len(self._events),
                    head_digest=self.head_digest,
                    first_invalid_sequence=expected_sequence,
                    reason="non-contiguous sequence",
                )
            if event.previous_digest != previous:
                return ChainVerification(
                    valid=False,
                    event_count=len(self._events),
                    head_digest=self.head_digest,
                    first_invalid_sequence=expected_sequence,
                    reason="previous digest mismatch",
                )
            expected_digest = content_digest(_event_digest_payload(event))
            if event.digest != expected_digest:
                return ChainVerification(
                    valid=False,
                    event_count=len(self._events),
                    head_digest=self.head_digest,
                    first_invalid_sequence=expected_sequence,
                    reason="event content digest mismatch",
                )
            previous = event.digest
        return ChainVerification(
            valid=True,
            event_count=len(self._events),
            head_digest=previous,
        )

    def event(self, digest: str) -> ProvenanceEvent | None:
        return next((event for event in self._events if event.digest == digest), None)

    def to_artifact(self) -> ProvenanceLedgerArtifact:
        payload = {
            "schema_version": "provenance-ledger.v1",
            "events": self.events,
            "head_digest": self.head_digest,
        }
        return ProvenanceLedgerArtifact(
            schema_version="provenance-ledger.v1",
            events=self.events,
            head_digest=self.head_digest,
            content_digest=content_digest(payload),
        )

    @classmethod
    def from_artifact(cls, artifact: ProvenanceLedgerArtifact) -> ProvenanceLedger:
        ledger = cls(artifact.events)
        expected = ledger.to_artifact()
        if expected.content_digest != artifact.content_digest:
            raise ValueError("provenance ledger artifact content digest mismatch")
        return ledger


def _event_digest_payload(event: ProvenanceEvent) -> dict[str, Any]:
    return {
        "schema_version": event.schema_version,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "producer": event.producer,
        "epistemic_status": event.epistemic_status,
        "inputs": event.inputs,
        "outputs": event.outputs,
        "source_refs": event.source_refs,
        "confidence": event.confidence,
        "ambiguity": event.ambiguity,
        "payload": event.payload,
        "previous_digest": event.previous_digest,
    }


def _payload_tuple(
    payload: Mapping[str, Any] | Iterable[tuple[str, Any]],
) -> tuple[tuple[str, Any], ...]:
    items = payload.items() if isinstance(payload, Mapping) else payload
    return tuple(
        sorted(
            ((str(key), canonical_value(value)) for key, value in items),
            key=lambda pair: pair[0],
        )
    )

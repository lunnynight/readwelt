"""Provider-visible graph locating candidates and selection diagnostics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StageViewConfidenceSource:
    candidate_id: str
    score: float
    method: str
    mention_id: str | None = None


@dataclass(frozen=True, slots=True)
class StageViewNode:
    node_id: str
    kind: str
    label: str | None
    text: str | None
    epistemic_status: str
    source_unit_ids: tuple[str, ...]
    source_element_ids: tuple[str, ...] = ()
    confidence: float | None = None
    confidence_method: str = "unresolved"
    confidence_sources: tuple[StageViewConfidenceSource, ...] = ()
    ambiguity: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    mention_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StageViewEdge:
    edge_id: str
    relation: str
    source_node_id: str
    target_node_id: str
    epistemic_status: str
    source_unit_ids: tuple[str, ...]
    source_element_ids: tuple[str, ...] = ()
    confidence: float | None = None
    confidence_method: str = "unresolved"
    confidence_sources: tuple[StageViewConfidenceSource, ...] = ()
    ambiguity: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StageViewClaim:
    claim_id: str
    text: str
    epistemic_status: str
    evidence_unit_ids: tuple[str, ...]
    evidence_element_ids: tuple[str, ...] = ()
    confidence: float | None = None
    confidence_method: str = "unresolved"
    confidence_sources: tuple[StageViewConfidenceSource, ...] = ()
    ambiguity: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    mention_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StageViewUpstreamClaim:
    claim_id: str
    text: str
    decision: str
    anchor_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionReason:
    object_type: str
    object_id: str
    reason: str
    priority: int


@dataclass(frozen=True, slots=True)
class StageViewCapabilityOutcome:
    backend_id: str
    capability: str
    status: str
    message: str | None

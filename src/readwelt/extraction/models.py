"""Host-neutral contracts for immutable, source-grounded extraction artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class BackendCapability(StrEnum):
    SENTENCE = "sentence"
    TOKEN = "token"
    POS = "pos"
    NER = "ner"
    DEPENDENCY = "dependency"
    SRL = "srl"
    COREFERENCE = "coreference"
    ENTITY = "entity"
    RELATION = "relation"
    EVENT = "event"
    CONCEPT = "concept"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    EXAMPLE = "example"
    OBJECTION = "objection"
    QUALIFICATION = "qualification"


class CapabilityStatus(StrEnum):
    UNSUPPORTED = "unsupported"
    NOT_RUN = "not_run"
    EMPTY = "empty"
    FAILED = "failed"
    PARTIAL = "partial"
    COMPLETE = "complete"


class NetworkBehavior(StrEnum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


class ExtractionEpistemicStatus(StrEnum):
    EXPLICIT = "explicit"
    LINGUISTIC_INFERENCE = "linguistic_inference"
    SEMANTIC_INFERENCE = "semantic_inference"


@dataclass(frozen=True, slots=True)
class BackendDescriptor:
    backend_id: str
    name: str
    version: str
    model_revision: str | None
    supported_capabilities: tuple[BackendCapability, ...]
    required_resources: tuple[str, ...] = ()
    license_name: str | None = None
    license_url: str | None = None
    network_behavior: NetworkBehavior = NetworkBehavior.NONE
    deterministic: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.backend_id.strip() or not self.name.strip() or not self.version.strip():
            raise ValueError("backend id, name, and version are required")
        if len(set(self.supported_capabilities)) != len(self.supported_capabilities):
            raise ValueError("supported capabilities must be unique")
        object.__setattr__(self, "metadata", MappingProxyType(dict(sorted(self.metadata.items()))))


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Stable extraction-side reference to an anchored source unit or sub-range."""

    unit_id: str
    reference_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    exact_text: str | None = None

    def __post_init__(self) -> None:
        if not self.unit_id.strip():
            raise ValueError("source reference unit_id is required")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("source reference offsets must be supplied together")
        if self.start_offset is not None and (
            self.start_offset < 0 or self.end_offset is None or self.end_offset < self.start_offset
        ):
            raise ValueError("source reference offsets are invalid")


@dataclass(frozen=True, slots=True)
class ExtractionInput:
    """Small adapter DTO; callers need not expose their article-IR implementation."""

    document_id: str
    snapshot_id: str
    unit_id: str
    text: str
    source_references: tuple[SourceReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.document_id.strip() or not self.snapshot_id.strip() or not self.unit_id.strip():
            raise ValueError("extraction input document_id, snapshot_id, and unit_id are required")


@dataclass(frozen=True, slots=True)
class SourceGrounding:
    source_references: tuple[SourceReference, ...]
    exact: bool = True

    @property
    def grounded(self) -> bool:
        return bool(self.source_references)

    @property
    def source_unit_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.unit_id for item in self.source_references))


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    score: float
    method: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("confidence score must be between zero and one")
        if not self.method.strip():
            raise ValueError("confidence method is required")


@dataclass(frozen=True, slots=True)
class Ambiguity:
    code: str
    message: str
    alternatives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise ValueError("ambiguity code and message are required")


@dataclass(frozen=True, slots=True)
class UnresolvedReference:
    reference: str
    reason: str
    candidate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reference.strip() or not self.reason.strip():
            raise ValueError("unresolved reference and reason are required")


@dataclass(frozen=True, slots=True)
class CandidateNode:
    candidate_id: str
    kind: str
    label: str | None
    text: str | None
    grounding: SourceGrounding
    confidence: ConfidenceAssessment
    epistemic_status: ExtractionEpistemicStatus
    attributes: tuple[tuple[str, str], ...] = ()
    ambiguity: tuple[Ambiguity, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.kind.strip():
            raise ValueError("candidate node id and kind are required")
        if not self.grounding.grounded:
            raise ValueError("candidate nodes must fail empty when source grounding is absent")

    @property
    def source_unit_ids(self) -> tuple[str, ...]:
        return self.grounding.source_unit_ids


@dataclass(frozen=True, slots=True)
class CandidateEdge:
    candidate_id: str
    relation: str
    source_candidate_id: str
    target_candidate_id: str
    grounding: SourceGrounding
    confidence: ConfidenceAssessment
    epistemic_status: ExtractionEpistemicStatus
    attributes: tuple[tuple[str, str], ...] = ()
    ambiguity: tuple[Ambiguity, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            (
                self.candidate_id.strip(),
                self.relation.strip(),
                self.source_candidate_id.strip(),
                self.target_candidate_id.strip(),
            )
        ):
            raise ValueError("candidate edge identity, relation, and endpoints are required")
        if not self.grounding.grounded:
            raise ValueError("candidate edges must fail empty when source grounding is absent")

    @property
    def source_unit_ids(self) -> tuple[str, ...]:
        return self.grounding.source_unit_ids


@dataclass(frozen=True, slots=True)
class CapabilityOutcome:
    capability: BackendCapability
    status: CapabilityStatus
    input_unit_ids: tuple[str, ...]
    covered_unit_ids: tuple[str, ...] = ()
    candidate_count: int = 0
    message: str | None = None

    def __post_init__(self) -> None:
        if self.candidate_count < 0:
            raise ValueError("candidate count cannot be negative")
        if not set(self.covered_unit_ids).issubset(self.input_unit_ids):
            raise ValueError("covered units must be extraction inputs")
        if self.status is CapabilityStatus.EMPTY and self.candidate_count != 0:
            raise ValueError("empty capability outcomes cannot contain candidates")
        if self.status is CapabilityStatus.UNSUPPORTED and self.covered_unit_ids:
            raise ValueError("unsupported capability outcomes cannot cover units")


@dataclass(frozen=True, slots=True)
class ExtractionCoverage:
    input_unit_ids: tuple[str, ...]
    covered_unit_ids: tuple[str, ...]
    uncovered_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        inputs = set(self.input_unit_ids)
        covered = set(self.covered_unit_ids)
        uncovered = set(self.uncovered_unit_ids)
        if not covered.issubset(inputs) or not uncovered.issubset(inputs):
            raise ValueError("coverage may only reference extraction input units")
        if covered & uncovered:
            raise ValueError("units cannot be both covered and uncovered")
        if covered | uncovered != inputs:
            raise ValueError("coverage must account for every extraction input unit")

    @property
    def complete(self) -> bool:
        return not self.uncovered_unit_ids


@dataclass(frozen=True, slots=True)
class DegradationReport:
    missing_capabilities: tuple[BackendCapability, ...]
    failed_capabilities: tuple[BackendCapability, ...]
    partial_capabilities: tuple[BackendCapability, ...]
    messages: tuple[str, ...] = ()

    @property
    def degraded(self) -> bool:
        return bool(
            self.missing_capabilities or self.failed_capabilities or self.partial_capabilities
        )

    @classmethod
    def from_outcomes(cls, outcomes: tuple[CapabilityOutcome, ...]) -> DegradationReport:
        return cls(
            missing_capabilities=tuple(
                item.capability
                for item in outcomes
                if item.status in {CapabilityStatus.UNSUPPORTED, CapabilityStatus.NOT_RUN}
            ),
            failed_capabilities=tuple(
                item.capability for item in outcomes if item.status is CapabilityStatus.FAILED
            ),
            partial_capabilities=tuple(
                item.capability for item in outcomes if item.status is CapabilityStatus.PARTIAL
            ),
            messages=tuple(item.message for item in outcomes if item.message is not None),
        )


@dataclass(frozen=True, slots=True)
class GraphExtraction:
    """Immutable backend output; it deliberately contains no canonical graph."""

    schema_version: str
    extraction_id: str
    document_id: str
    snapshot_id: str
    backend: BackendDescriptor
    input_unit_ids: tuple[str, ...]
    candidate_nodes: tuple[CandidateNode, ...]
    candidate_edges: tuple[CandidateEdge, ...]
    outcomes: tuple[CapabilityOutcome, ...]
    coverage: ExtractionCoverage
    degradation: DegradationReport
    unresolved_references: tuple[UnresolvedReference, ...] = ()
    warnings: tuple[str, ...] = ()
    content_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != "graph-extraction.v1":
            raise ValueError(f"unsupported graph extraction schema: {self.schema_version}")
        if not self.extraction_id.strip():
            raise ValueError("extraction id is required")
        if not self.document_id.strip() or not self.snapshot_id.strip():
            raise ValueError("graph extraction document_id and snapshot_id are required")
        if self.coverage.input_unit_ids != self.input_unit_ids:
            raise ValueError("coverage input order must match extraction input order")
        node_ids = tuple(item.candidate_id for item in self.candidate_nodes)
        edge_ids = tuple(item.candidate_id for item in self.candidate_edges)
        if len(set(node_ids)) != len(node_ids) or len(set(edge_ids)) != len(edge_ids):
            raise ValueError("candidate ids must be unique within their artifact")
        if len({item.capability for item in self.outcomes}) != len(self.outcomes):
            raise ValueError("graph extraction capability outcomes must be unique")
        expected = graph_extraction_digest(self)
        if self.content_digest and self.content_digest != expected:
            raise ValueError("graph extraction content digest does not match its content")
        object.__setattr__(self, "content_digest", expected)

    @property
    def available_capabilities(self) -> tuple[BackendCapability, ...]:
        available_statuses = {
            CapabilityStatus.EMPTY,
            CapabilityStatus.PARTIAL,
            CapabilityStatus.COMPLETE,
        }
        return tuple(
            item.capability for item in self.outcomes if item.status in available_statuses
        )

    @property
    def missing_capabilities(self) -> tuple[BackendCapability, ...]:
        return tuple(
            item.capability
            for item in self.outcomes
            if item.status
            in {
                CapabilityStatus.UNSUPPORTED,
                CapabilityStatus.NOT_RUN,
                CapabilityStatus.FAILED,
            }
        )


def graph_extraction_digest(extraction: GraphExtraction) -> str:
    value = {
        item.name: getattr(extraction, item.name)
        for item in fields(extraction)
    }
    value["content_digest"] = ""
    payload = json.dumps(
        _json_value(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def stable_id(namespace: str, *values: str) -> str:
    payload = "\x1f".join((namespace, *values)).encode()
    return f"{namespace}:{hashlib.sha256(payload).hexdigest()[:24]}"


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value

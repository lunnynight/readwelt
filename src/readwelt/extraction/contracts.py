"""Stable backend, source-grounding, and candidate extraction contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from . import taxonomy as _taxonomy


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
    PREMISE = "premise"
    CONCLUSION = "conclusion"
    EVIDENCE = "evidence"
    EXAMPLE = "example"
    OBJECTION = "objection"
    QUALIFICATION = "qualification"
    SUPPORT_RELATION = "relation:support"
    REFUTATION_RELATION = "relation:refutation"
    CAUSATION_RELATION = "relation:causation"
    CONTRAST_RELATION = "relation:contrast"
    QUALIFICATION_RELATION = "relation:qualification"
    EXEMPLIFICATION_RELATION = "relation:exemplification"
    PREMISE_TO_CLAIM_RELATION = "relation:premise-to-claim"
    CONCLUSION_FLOW_RELATION = "relation:conclusion-flow"


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
    taxonomy_schema_version: str | None = None
    emitted_candidate_kinds: tuple[str, ...] = ()
    emitted_relations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.backend_id.strip() or not self.name.strip() or not self.version.strip():
            raise ValueError("backend id, name, and version are required")
        if len(set(self.supported_capabilities)) != len(self.supported_capabilities):
            raise ValueError("supported capabilities must be unique")
        if len(set(self.emitted_candidate_kinds)) != len(self.emitted_candidate_kinds):
            raise ValueError("emitted candidate kinds must be unique")
        if len(set(self.emitted_relations)) != len(self.emitted_relations):
            raise ValueError("emitted relations must be unique")
        if self.taxonomy_schema_version is not None:
            if self.taxonomy_schema_version != _taxonomy.ARGUMENT_TAXONOMY_SCHEMA_VERSION:
                raise ValueError("unsupported backend argument taxonomy")
            if any(
                not _taxonomy.valid_candidate_kind(item) for item in self.emitted_candidate_kinds
            ):
                raise ValueError("backend candidate extensions must be namespaced")
            if any(not _taxonomy.valid_relation_kind(item) for item in self.emitted_relations):
                raise ValueError("backend relation extensions must be namespaced")
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(sorted(self.metadata.items()))),
        )


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Stable extraction-side reference to a source unit, element, or sub-range."""

    unit_id: str | None = None
    reference_id: str | None = None
    element_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    exact_text: str | None = None

    def __post_init__(self) -> None:
        if self.unit_id is not None and not self.unit_id.strip():
            raise ValueError("source reference unit_id cannot be empty")
        if self.element_id is not None and not self.element_id.strip():
            raise ValueError("source reference element_id cannot be empty")
        if self.unit_id is None and self.element_id is None:
            raise ValueError("source reference requires a unit_id or element_id")
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
        return tuple(
            dict.fromkeys(
                item.unit_id for item in self.source_references if item.unit_id is not None
            )
        )

    @property
    def source_element_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                item.element_id for item in self.source_references if item.element_id is not None
            )
        )


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

    @property
    def source_element_ids(self) -> tuple[str, ...]:
        return self.grounding.source_element_ids


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

    @property
    def source_element_ids(self) -> tuple[str, ...]:
        return self.grounding.source_element_ids

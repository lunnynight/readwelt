"""Host-neutral contracts for immutable, source-grounded extraction artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any

from . import contracts as _contracts
from .taxonomy import ARGUMENT_TAXONOMY_SCHEMA_VERSION

Ambiguity = _contracts.Ambiguity
BackendCapability = _contracts.BackendCapability
BackendDescriptor = _contracts.BackendDescriptor
CandidateEdge = _contracts.CandidateEdge
CandidateNode = _contracts.CandidateNode
CapabilityStatus = _contracts.CapabilityStatus
ConfidenceAssessment = _contracts.ConfidenceAssessment
ExtractionEpistemicStatus = _contracts.ExtractionEpistemicStatus
ExtractionInput = _contracts.ExtractionInput
NetworkBehavior = _contracts.NetworkBehavior
SourceGrounding = _contracts.SourceGrounding
SourceReference = _contracts.SourceReference
UnresolvedReference = _contracts.UnresolvedReference


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
        if self.schema_version not in {
            "graph-extraction.v1",
            "graph-extraction.v2",
            "graph-extraction.v3",
        }:
            raise ValueError(f"unsupported graph extraction schema: {self.schema_version}")
        v1_has_element_only_reference = any(
            reference.unit_id is None
            for candidate in self.candidate_nodes
            for reference in candidate.grounding.source_references
        ) or any(
            reference.unit_id is None
            for candidate in self.candidate_edges
            for reference in candidate.grounding.source_references
        )
        if self.schema_version == "graph-extraction.v1" and v1_has_element_only_reference:
            raise ValueError("graph-extraction.v1 references require source unit ids")
        if self.schema_version == "graph-extraction.v3":
            if self.backend.taxonomy_schema_version != ARGUMENT_TAXONOMY_SCHEMA_VERSION:
                raise ValueError("graph-extraction.v3 requires the argument taxonomy")
            undeclared_kinds = {item.kind for item in self.candidate_nodes} - set(
                self.backend.emitted_candidate_kinds
            )
            undeclared_relations = {item.relation for item in self.candidate_edges} - set(
                self.backend.emitted_relations
            )
            if undeclared_kinds or undeclared_relations:
                raise ValueError("graph extraction emitted undeclared taxonomy identities")
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
        return tuple(item.capability for item in self.outcomes if item.status in available_statuses)

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
    value = {item.name: getattr(extraction, item.name) for item in fields(extraction)}
    value["content_digest"] = ""
    payload = json.dumps(
        _json_value(
            value,
            omit_absent_element_id=extraction.schema_version == "graph-extraction.v1",
            omit_taxonomy_descriptor=extraction.schema_version
            in {"graph-extraction.v1", "graph-extraction.v2"},
        ),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def stable_id(namespace: str, *values: str) -> str:
    payload = "\x1f".join((namespace, *values)).encode()
    return f"{namespace}:{hashlib.sha256(payload).hexdigest()[:24]}"


def _json_value(
    value: Any,
    *,
    omit_absent_element_id: bool = True,
    omit_taxonomy_descriptor: bool = True,
) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        result = {
            item.name: _json_value(
                getattr(value, item.name),
                omit_absent_element_id=omit_absent_element_id,
                omit_taxonomy_descriptor=omit_taxonomy_descriptor,
            )
            for item in fields(value)
        }
        # ``element_id`` is an additive graph-extraction.v1 field. Omitting its
        # absent value preserves the digest of historical v1 artifacts while a
        # claimed native element still participates in the digest.
        if (
            omit_absent_element_id
            and isinstance(value, SourceReference)
            and value.element_id is None
        ):
            result.pop("element_id")
        if omit_taxonomy_descriptor and isinstance(value, BackendDescriptor):
            result.pop("taxonomy_schema_version")
            result.pop("emitted_candidate_kinds")
            result.pop("emitted_relations")
        return result
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(
                item,
                omit_absent_element_id=omit_absent_element_id,
                omit_taxonomy_descriptor=omit_taxonomy_descriptor,
            )
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [
            _json_value(
                item,
                omit_absent_element_id=omit_absent_element_id,
                omit_taxonomy_descriptor=omit_taxonomy_descriptor,
            )
            for item in value
        ]
    if isinstance(value, StrEnum):
        return value.value
    return value

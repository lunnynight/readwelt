"""Immutable contracts for provider-to-Source-Plane provenance closure."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from readwelt.article_graph.digest import content_digest

PROVENANCE_CLOSURE_SCHEMA_VERSION = "provenance-closure.v1"


class ProviderMaterialKind(StrEnum):
    """Kinds serialized into a final provider-bound StageRequest."""

    TEXT_UNIT = "text_unit"
    TEXT_SLICE = "text_slice"
    GRAPH_NODE = "graph_node"
    GRAPH_EDGE = "graph_edge"
    GRAPH_CLAIM = "graph_claim"
    ANCHOR = "anchor"
    RETRIEVAL_HIT = "retrieval_hit"
    SOURCE_RANGE = "source_range"
    SOURCE_ELEMENT = "source_element"
    UPSTREAM_CLAIM = "upstream_claim"
    EXTERNAL_EVIDENCE = "external_evidence"
    REQUEST_METADATA = "request_metadata"
    REQUEST_PROVENANCE = "request_provenance"


class ProviderMaterialDisposition(StrEnum):
    SOURCE_GROUNDED = "source_grounded"
    NON_SOURCE_METADATA = "non_source_metadata"


class SourceRecordKind(StrEnum):
    """Typed Source Plane records reached by provenance closure."""

    TEXT_UNIT = "text_unit"
    SOURCE_RANGE = "source_range"
    SOURCE_ELEMENT = "source_element"
    SOURCE_REFERENCE = "source_reference"


@dataclass(frozen=True, slots=True)
class ProviderVisibleMaterial:
    """One locating object that is actually serialized for a provider."""

    material_id: str
    material_kind: ProviderMaterialKind
    source_unit_ids: tuple[str, ...]
    source_element_ids: tuple[str, ...] = ()
    disposition: ProviderMaterialDisposition = ProviderMaterialDisposition.SOURCE_GROUNDED
    non_source_reason: str | None = None
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        if not self.material_id:
            raise ValueError("provider-visible material identity is required")
        if len(self.source_unit_ids) != len(set(self.source_unit_ids)):
            raise ValueError("provider-visible source units must be unique")
        if len(self.source_element_ids) != len(set(self.source_element_ids)):
            raise ValueError("provider-visible source elements must be unique")
        non_source_kinds = {
            ProviderMaterialKind.UPSTREAM_CLAIM,
            ProviderMaterialKind.EXTERNAL_EVIDENCE,
            ProviderMaterialKind.REQUEST_METADATA,
            ProviderMaterialKind.REQUEST_PROVENANCE,
        }
        source_kinds = set(ProviderMaterialKind) - non_source_kinds
        if self.material_kind in source_kinds and (
            self.disposition is not ProviderMaterialDisposition.SOURCE_GROUNDED
        ):
            raise ValueError(f"{self.material_kind.value} must be source-grounded")
        if self.material_kind in non_source_kinds and (
            self.disposition is not ProviderMaterialDisposition.NON_SOURCE_METADATA
        ):
            raise ValueError(f"{self.material_kind.value} must be explicit non-source metadata")
        if self.disposition is ProviderMaterialDisposition.NON_SOURCE_METADATA:
            if self.source_unit_ids or self.source_element_ids:
                raise ValueError("non-source provider material cannot claim source records")
            if self.non_source_reason is None or not self.non_source_reason.strip():
                raise ValueError("non-source provider material requires a reason")
        elif self.non_source_reason is not None:
            raise ValueError("source-grounded provider material cannot have a non-source reason")
        if self.material_kind in {
            ProviderMaterialKind.SOURCE_RANGE,
            ProviderMaterialKind.SOURCE_ELEMENT,
        } and not (self.source_record_id or self.material_id):
            raise ValueError("Source Plane provider material requires a record identity")

    def to_mapping(self) -> dict[str, object]:
        mapping: dict[str, object] = {
            "material_id": self.material_id,
            "material_kind": self.material_kind.value,
            "source_unit_ids": list(self.source_unit_ids),
            "source_element_ids": list(self.source_element_ids),
            "disposition": self.disposition.value,
            "non_source_reason": self.non_source_reason,
        }
        if self.source_record_id is not None:
            mapping["source_record_id"] = self.source_record_id
        return mapping


@dataclass(frozen=True, slots=True)
class TypedSourceReference:
    """A typed, non-fabricated reference to one Source Plane record."""

    record_id: str
    record_kind: SourceRecordKind
    snapshot_id: str
    via_unit_id: str | None = None

    def __post_init__(self) -> None:
        if not all((self.record_id, self.snapshot_id)):
            raise ValueError("typed source reference identity is required")


@dataclass(frozen=True, slots=True)
class ProviderMaterialResolution:
    material: ProviderVisibleMaterial
    source_references: tuple[TypedSourceReference, ...]
    ledger_event_digests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProvenanceClosureIssue:
    code: str
    material_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class ProvenanceClosureReport:
    schema_version: str
    snapshot_id: str
    resolutions: tuple[ProviderMaterialResolution, ...]
    issues: tuple[ProvenanceClosureIssue, ...]
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != PROVENANCE_CLOSURE_SCHEMA_VERSION:
            raise ValueError(f"unsupported provenance closure schema: {self.schema_version}")
        if not self.snapshot_id:
            raise ValueError("provenance closure snapshot identity is required")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("provenance closure digest must be sha256")
        expected = content_digest(
            {
                "schema_version": self.schema_version,
                "snapshot_id": self.snapshot_id,
                "resolutions": self.resolutions,
                "issues": self.issues,
            }
        )
        if self.content_digest != expected:
            raise ValueError("provenance closure content digest mismatch")

    @property
    def valid(self) -> bool:
        return not self.issues

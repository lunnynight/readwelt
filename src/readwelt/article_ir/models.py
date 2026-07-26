"""Lossless, revision-aware text units and source coverage records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CoverageStatus = Literal["covered", "unsupported", "uncovered"]
CoverageScope = Literal["source_range", "structure", "normalization"]


@dataclass(frozen=True, slots=True)
class SourceReference:
    """A source locator without requiring layout data that may not exist."""

    reference_id: str
    snapshot_id: str
    document_id: str
    section_id: str | None = None
    anchor_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    exact_text: str | None = None
    prefix: str = ""
    suffix: str = ""
    page: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    element_id: str | None = None
    textual_anchor: str | None = None
    kind: str | None = None
    parent_element_id: str | None = None
    heading_trail: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reference_id or not self.snapshot_id or not self.document_id:
            raise ValueError("source reference identity fields are required")
        has_start = self.start_offset is not None
        has_end = self.end_offset is not None
        if has_start != has_end:
            raise ValueError("source character range requires both offsets")
        if has_start:
            assert self.start_offset is not None
            assert self.end_offset is not None
            if self.start_offset < 0 or self.end_offset < self.start_offset:
                raise ValueError("invalid source character range")
            if self.exact_text is None:
                raise ValueError("character source reference requires exact_text")
            if self.end_offset - self.start_offset != len(self.exact_text):
                raise ValueError("source character range must span exact_text")
        elif self.exact_text is not None:
            raise ValueError("exact_text requires a source character range")
        if self.page is not None and self.page < 1:
            raise ValueError("page must be positive")
        if self.bounding_box is not None and self.page is None:
            raise ValueError("bounding_box requires a page")
        if not any(
            (
                has_start,
                self.page is not None,
                self.element_id is not None,
                self.textual_anchor is not None,
                self.anchor_id is not None,
            )
        ):
            raise ValueError("source reference requires at least one locator")


@dataclass(frozen=True, slots=True)
class AnchoredTextUnit:
    """Exact source text plus stable navigation and revision identity."""

    unit_id: str
    schema_version: str
    snapshot_id: str
    document_id: str
    revision_id: str
    ordinal: int
    kind: str
    exact_text: str
    content_hash: str
    structural_path: tuple[str, ...]
    heading_trail: tuple[str, ...]
    source_references: tuple[SourceReference, ...]
    parent_unit_id: str | None = None
    previous_unit_id: str | None = None
    next_unit_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "anchored-text-unit.v1":
            raise ValueError(f"unsupported anchored text schema: {self.schema_version}")
        if not all((self.unit_id, self.snapshot_id, self.document_id, self.revision_id)):
            raise ValueError("anchored text identity fields are required")
        if self.revision_id != self.snapshot_id:
            raise ValueError("v1 revision_id must be the source snapshot_id")
        if self.ordinal < 0:
            raise ValueError("ordinal cannot be negative")
        if not self.kind.strip():
            raise ValueError("unit kind is required")
        if not self.content_hash.startswith("sha256:"):
            raise ValueError("content_hash must be a sha256 digest")
        if not self.source_references:
            raise ValueError("anchored text unit requires a source reference")
        if any(
            reference.snapshot_id != self.snapshot_id
            or reference.document_id != self.document_id
            for reference in self.source_references
        ):
            raise ValueError("unit source references must belong to its revision")
        ranged_text = "".join(
            reference.exact_text or ""
            for reference in self.source_references
            if reference.start_offset is not None
        )
        if ranged_text and ranged_text != self.exact_text:
            raise ValueError("unit exact_text must equal its character references")


@dataclass(frozen=True, slots=True)
class CoverageRecord:
    """One explicit coverage outcome for source, structure, or normalization."""

    record_id: str
    status: CoverageStatus
    scope: CoverageScope
    reason: str
    snapshot_id: str
    start_offset: int | None = None
    end_offset: int | None = None
    section_id: str | None = None
    unit_ids: tuple[str, ...] = ()
    detail: str | None = None

    def __post_init__(self) -> None:
        if not self.record_id or not self.snapshot_id or not self.reason.strip():
            raise ValueError("coverage record identity and reason are required")
        has_start = self.start_offset is not None
        has_end = self.end_offset is not None
        if has_start != has_end:
            raise ValueError("coverage range requires both offsets")
        if has_start:
            assert self.start_offset is not None
            assert self.end_offset is not None
            if self.start_offset < 0 or self.end_offset < self.start_offset:
                raise ValueError("invalid coverage range")
        if self.scope == "source_range" and not has_start:
            raise ValueError("source_range coverage requires offsets")


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Deterministic accounting for every non-whitespace source range."""

    schema_version: str
    snapshot_id: str
    document_id: str
    source_length: int
    records: tuple[CoverageRecord, ...]
    normalization_transformations: tuple[str, ...]
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "coverage-report.v1":
            raise ValueError(f"unsupported coverage schema: {self.schema_version}")
        if self.source_length < 0:
            raise ValueError("source_length cannot be negative")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")
        if any(record.snapshot_id != self.snapshot_id for record in self.records):
            raise ValueError("coverage records must belong to this snapshot")

    @property
    def covered(self) -> tuple[CoverageRecord, ...]:
        return tuple(record for record in self.records if record.status == "covered")

    @property
    def unsupported(self) -> tuple[CoverageRecord, ...]:
        return tuple(record for record in self.records if record.status == "unsupported")

    @property
    def uncovered(self) -> tuple[CoverageRecord, ...]:
        return tuple(record for record in self.records if record.status == "uncovered")

    @property
    def has_complete_text_coverage(self) -> bool:
        return not any(
            record.scope == "source_range" and record.status != "covered"
            for record in self.records
        )


@dataclass(frozen=True, slots=True)
class UnitizationResult:
    schema_version: str
    snapshot_id: str
    units: tuple[AnchoredTextUnit, ...]
    coverage: CoverageReport
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "anchored-text-unitization.v1":
            raise ValueError(f"unsupported unitization schema: {self.schema_version}")
        if self.coverage.snapshot_id != self.snapshot_id:
            raise ValueError("coverage belongs to another snapshot")
        if any(unit.snapshot_id != self.snapshot_id for unit in self.units):
            raise ValueError("text units belong to another snapshot")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")

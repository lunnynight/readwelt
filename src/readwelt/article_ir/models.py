"""Lossless, revision-aware text units and source coverage records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from readwelt.domain.documents import SourceElement

CoverageStatus = Literal["covered", "unsupported", "uncovered"]
CoverageScope = Literal[
    "source_range",
    "element",
    "structure",
    "capability",
    "normalization",
]
SourceRangeKind = Literal["unit", "gap", "unsupported", "uncovered"]

HISTORICAL_UNITIZATION_SCHEMA_VERSION = "anchored-text-unitization.v1"
ARTICLE_SOURCE_PLANE_SCHEMA_VERSION = "article-source-plane.v1"


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
            reference.snapshot_id != self.snapshot_id or reference.document_id != self.document_id
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
class SourceRangeRecord:
    """A complete, non-overlapping address record over normalized source text."""

    range_id: str
    snapshot_id: str
    schema_version: str
    start_offset: int
    end_offset: int
    kind: SourceRangeKind
    content_hash: str
    unit_ids: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.range_id or not self.snapshot_id:
            raise ValueError("source range identity fields are required")
        if self.schema_version != "source-range.v1":
            raise ValueError(f"unsupported source range schema: {self.schema_version}")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise ValueError("source range must be non-empty and ordered")
        if not self.content_hash.startswith("sha256:"):
            raise ValueError("source range content_hash must be a sha256 digest")
        if self.kind == "unit" and not self.unit_ids:
            raise ValueError("unit source range requires at least one unit")
        if self.kind != "unit" and self.unit_ids:
            raise ValueError("non-unit source range cannot claim unit ownership")
        if self.kind in {"unsupported", "uncovered"} and not self.reason:
            raise ValueError(f"{self.kind} source range requires a reason")


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
    """Deterministic accounting for every normalized source range."""

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
            record.scope == "source_range" and record.status != "covered" for record in self.records
        )


@dataclass(frozen=True, slots=True)
class SourcePlaneCoverageManifest:
    """Versioned coverage dimensions without conflating source and semantics."""

    schema_version: str
    snapshot_id: str
    source_length: int
    range_coverage: tuple[CoverageRecord, ...]
    element_coverage: tuple[CoverageRecord, ...]
    structure_coverage: tuple[CoverageRecord, ...]
    capability_coverage: tuple[CoverageRecord, ...]
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "source-plane-coverage.v1":
            raise ValueError(f"unsupported source plane coverage schema: {self.schema_version}")
        if self.source_length < 0:
            raise ValueError("source plane source_length cannot be negative")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("source plane coverage digest must be sha256")
        dimensions = (
            ("source_range", self.range_coverage),
            ("element", self.element_coverage),
            ("structure", self.structure_coverage),
            ("capability", self.capability_coverage),
        )
        if any(
            record.snapshot_id != self.snapshot_id or record.scope != scope
            for scope, records in dimensions
            for record in records
        ):
            raise ValueError("source plane coverage records belong to another dimension")

    @property
    def has_complete_source_reachability(self) -> bool:
        return not any(record.status != "covered" for record in self.range_coverage)


@dataclass(frozen=True, slots=True)
class UnitizationResult:
    schema_version: str
    snapshot_id: str
    units: tuple[AnchoredTextUnit, ...]
    coverage: CoverageReport
    content_digest: str
    source_ranges: tuple[SourceRangeRecord, ...] = ()
    source_elements: tuple[SourceElement, ...] = ()
    coverage_manifest: SourcePlaneCoverageManifest | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in {
            HISTORICAL_UNITIZATION_SCHEMA_VERSION,
            ARTICLE_SOURCE_PLANE_SCHEMA_VERSION,
        }:
            raise ValueError(f"unsupported unitization schema: {self.schema_version}")
        if self.coverage.snapshot_id != self.snapshot_id:
            raise ValueError("coverage belongs to another snapshot")
        if any(unit.snapshot_id != self.snapshot_id for unit in self.units):
            raise ValueError("text units belong to another snapshot")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")
        expected_start = 0
        for source_range in self.source_ranges:
            if source_range.snapshot_id != self.snapshot_id:
                raise ValueError("source ranges belong to another snapshot")
            if source_range.start_offset != expected_start:
                raise ValueError("source ranges must be complete, ordered, and non-overlapping")
            expected_start = source_range.end_offset
        if self.source_ranges and expected_start != self.coverage.source_length:
            raise ValueError("source ranges must cover the complete normalized source")
        if any(element.snapshot_id != self.snapshot_id for element in self.source_elements):
            raise ValueError("source elements belong to another snapshot")
        if (
            self.coverage_manifest is not None
            and self.coverage_manifest.snapshot_id != self.snapshot_id
        ):
            raise ValueError("source plane coverage manifest belongs to another snapshot")
        if self.schema_version == HISTORICAL_UNITIZATION_SCHEMA_VERSION and (
            self.source_ranges or self.source_elements or self.coverage_manifest is not None
        ):
            raise ValueError("historical unitization cannot contain aggregate Source Plane fields")
        if (
            self.schema_version == ARTICLE_SOURCE_PLANE_SCHEMA_VERSION
            and self.coverage_manifest is None
        ):
            raise ValueError("article-source-plane.v1 requires a coverage manifest")

    def range_at(self, offset: int) -> SourceRangeRecord | None:
        """Resolve one normalized source offset without semantic extraction."""

        if offset < 0 or offset >= self.coverage.source_length:
            return None
        return next(
            (
                source_range
                for source_range in self.source_ranges
                if source_range.start_offset <= offset < source_range.end_offset
            ),
            None,
        )

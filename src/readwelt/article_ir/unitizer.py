"""Deterministic conversion of source snapshots into anchored text units."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from readwelt.domain.documents import DocumentSection, SourceDocumentSnapshot, SourceElement
from readwelt.domain.ids import stable_id

from .models import (
    ARTICLE_SOURCE_PLANE_SCHEMA_VERSION,
    AnchoredTextUnit,
    CoverageRecord,
    CoverageReport,
    CoverageStatus,
    SourcePlaneCoverageManifest,
    SourceRangeKind,
    SourceRangeRecord,
    SourceReference,
    UnitizationResult,
)

_UNIT_SCHEMA = "anchored-text-unit.v1"
_UNITIZATION_SCHEMA = ARTICLE_SOURCE_PLANE_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class _Candidate:
    section: DocumentSection
    source_ordinal: int
    unit_id: str


class DeterministicUnitizer:
    """Unitize only facts present in a snapshot; never infer missing structure."""

    schema_version = _UNITIZATION_SCHEMA

    def unitize(
        self,
        snapshot: SourceDocumentSnapshot,
        normalized_text: str,
    ) -> UnitizationResult:
        candidates, problem_records = self._candidates(snapshot, normalized_text)
        units = self._units(snapshot, candidates)
        range_records = self._range_coverage(
            snapshot,
            normalized_text,
            units,
            problem_records,
        )
        source_ranges = self._source_ranges(snapshot, normalized_text, range_records)
        structure_records = self._structure_coverage(snapshot, candidates)
        element_records = self._element_coverage(snapshot)
        capability_records = self._capability_coverage(snapshot)
        represented_problem_ids = {
            record.detail
            for record in range_records
            if record.status == "unsupported" and record.detail is not None
        }
        unplaced_problems = tuple(
            record for record in problem_records if record.record_id not in represented_problem_ids
        )
        records = tuple(
            (
                *range_records,
                *unplaced_problems,
                *element_records,
                *structure_records,
                *capability_records,
            )
        )
        coverage = self._coverage_report(snapshot, normalized_text, records)
        coverage_manifest = self._coverage_manifest(
            snapshot,
            normalized_text,
            range_records,
            element_records,
            structure_records,
            capability_records,
        )
        payload = {
            "schema_version": self.schema_version,
            "snapshot_id": snapshot.snapshot_id,
            "units": [_unit_value(unit) for unit in units],
            "source_ranges": [_source_range_value(item) for item in source_ranges],
            "source_elements": [
                (
                    element.element_id,
                    element.schema_version,
                    element.ordinal,
                    element.reading_order,
                    element.projection_status,
                    element.kind,
                    element.content_layer,
                    element.start_offset,
                    element.end_offset,
                    element.parent_element_id,
                    element.child_element_ids,
                    element.previous_element_id,
                    element.next_element_id,
                    element.structural_relations,
                    element.page,
                    element.bounding_box,
                    element.native_reference,
                    element.raw_payload_ref,
                )
                for element in snapshot.source_elements
            ],
            "coverage_digest": coverage.content_digest,
            "coverage_manifest_digest": coverage_manifest.content_digest,
        }
        return UnitizationResult(
            schema_version=self.schema_version,
            snapshot_id=snapshot.snapshot_id,
            units=units,
            coverage=coverage,
            content_digest=_digest(payload),
            source_ranges=source_ranges,
            source_elements=snapshot.source_elements,
            coverage_manifest=coverage_manifest,
        )

    def _candidates(
        self,
        snapshot: SourceDocumentSnapshot,
        text: str,
    ) -> tuple[tuple[_Candidate, ...], tuple[CoverageRecord, ...]]:
        candidates: list[_Candidate] = []
        problems: list[CoverageRecord] = []
        for source_ordinal, section in enumerate(snapshot.sections):
            start = section.start_offset
            end = section.end_offset
            reason: str | None = None
            if end > len(text):
                reason = "section_range_exceeds_normalized_text"
            elif section.anchor.start_offset != start or section.anchor.end_offset != end:
                reason = "section_and_anchor_ranges_disagree"
            elif section.anchor.exact_text != text[start:end]:
                reason = "anchor_text_differs_from_normalized_text"
            if reason is not None:
                bounded_start = min(start, len(text))
                bounded_end = min(max(end, bounded_start), len(text))
                problems.append(
                    CoverageRecord(
                        record_id=stable_id(
                            "coverage",
                            snapshot.snapshot_id,
                            "unsupported",
                            section.section_id,
                            reason,
                        ),
                        status="unsupported",
                        scope="source_range",
                        reason=reason,
                        snapshot_id=snapshot.snapshot_id,
                        start_offset=bounded_start,
                        end_offset=bounded_end,
                        section_id=section.section_id,
                    )
                )
                continue
            unit_id = stable_id(
                "text_unit",
                snapshot.snapshot_id,
                _UNIT_SCHEMA,
                section.section_id,
                str(start),
                str(end),
                section.anchor.exact_text,
            )
            candidates.append(
                _Candidate(
                    section=section,
                    source_ordinal=source_ordinal,
                    unit_id=unit_id,
                )
            )
        candidates.sort(
            key=lambda candidate: (
                candidate.section.start_offset,
                candidate.section.end_offset,
                candidate.source_ordinal,
                candidate.section.section_id,
            )
        )
        return tuple(candidates), tuple(problems)

    @staticmethod
    def _units(
        snapshot: SourceDocumentSnapshot,
        candidates: tuple[_Candidate, ...],
    ) -> tuple[AnchoredTextUnit, ...]:
        element_by_id = {element.element_id: element for element in snapshot.source_elements}
        element_to_unit = {
            candidate.section.element_id: candidate.unit_id
            for candidate in candidates
            if candidate.section.element_id is not None
        }
        units: list[AnchoredTextUnit] = []
        for ordinal, candidate in enumerate(candidates):
            section = candidate.section
            anchor = section.anchor
            reference = SourceReference(
                reference_id=stable_id(
                    "source_ref",
                    snapshot.snapshot_id,
                    section.section_id,
                    anchor.anchor_id,
                    str(anchor.start_offset),
                    str(anchor.end_offset),
                ),
                snapshot_id=snapshot.snapshot_id,
                document_id=snapshot.document_id,
                section_id=section.section_id,
                anchor_id=anchor.anchor_id,
                start_offset=anchor.start_offset,
                end_offset=anchor.end_offset,
                exact_text=anchor.exact_text,
                prefix=anchor.prefix,
                suffix=anchor.suffix,
                page=section.page if section.page is not None else anchor.page,
                bounding_box=section.bounding_box,
                element_id=section.element_id,
                kind=section.kind,
                parent_element_id=section.parent_element_id,
                heading_trail=section.heading_trail,
            )
            units.append(
                AnchoredTextUnit(
                    unit_id=candidate.unit_id,
                    schema_version=_UNIT_SCHEMA,
                    snapshot_id=snapshot.snapshot_id,
                    document_id=snapshot.document_id,
                    revision_id=snapshot.snapshot_id,
                    ordinal=ordinal,
                    kind=section.kind or "paragraph",
                    exact_text=anchor.exact_text,
                    content_hash=_text_hash(anchor.exact_text),
                    structural_path=_structural_path(
                        section.element_id,
                        section.section_id,
                        element_by_id,
                    ),
                    heading_trail=(
                        section.heading_trail
                        if section.heading_trail
                        else (section.title,)
                        if section.title is not None
                        else ()
                    ),
                    source_references=(reference,),
                    parent_unit_id=(
                        element_to_unit.get(section.parent_element_id)
                        if section.parent_element_id is not None
                        else None
                    ),
                    previous_unit_id=candidates[ordinal - 1].unit_id if ordinal else None,
                    next_unit_id=(
                        candidates[ordinal + 1].unit_id if ordinal + 1 < len(candidates) else None
                    ),
                )
            )
        return tuple(units)

    @staticmethod
    def _element_coverage(
        snapshot: SourceDocumentSnapshot,
    ) -> tuple[CoverageRecord, ...]:
        records: list[CoverageRecord] = []
        for element in snapshot.source_elements:
            status: CoverageStatus = (
                "unsupported" if element.projection_status == "unresolved" else "covered"
            )
            records.append(
                CoverageRecord(
                    record_id=stable_id(
                        "coverage",
                        snapshot.snapshot_id,
                        "element",
                        element.element_id,
                        element.projection_status,
                    ),
                    status=status,
                    scope="element",
                    reason=f"source_element_{element.projection_status}",
                    snapshot_id=snapshot.snapshot_id,
                    start_offset=element.start_offset,
                    end_offset=element.end_offset,
                    detail=element.element_id,
                )
            )
        return tuple(records)

    @staticmethod
    def _capability_coverage(
        snapshot: SourceDocumentSnapshot,
    ) -> tuple[CoverageRecord, ...]:
        records: list[CoverageRecord] = []
        for ordinal, finding in enumerate(snapshot.parse_findings):
            lowered = finding.casefold()
            status: CoverageStatus = (
                "unsupported"
                if any(marker in lowered for marker in ("unsupported", "unresolved", "not_exposed"))
                else "covered"
            )
            records.append(
                CoverageRecord(
                    record_id=stable_id(
                        "coverage",
                        snapshot.snapshot_id,
                        "capability",
                        str(ordinal),
                        finding,
                    ),
                    status=status,
                    scope="capability",
                    reason=finding,
                    snapshot_id=snapshot.snapshot_id,
                )
            )
        return tuple(records)

    @staticmethod
    def _range_coverage(
        snapshot: SourceDocumentSnapshot,
        text: str,
        units: tuple[AnchoredTextUnit, ...],
        problem_records: tuple[CoverageRecord, ...],
    ) -> tuple[CoverageRecord, ...]:
        owners: list[list[str]] = [[] for _ in text]
        for unit in units:
            for reference in unit.source_references:
                if reference.start_offset is None or reference.end_offset is None:
                    continue
                for offset in range(reference.start_offset, reference.end_offset):
                    owners[offset].append(unit.unit_id)

        records: list[CoverageRecord] = []
        offset = 0
        while offset < len(text):
            unit_ids = tuple(sorted(set(owners[offset])))
            problems = tuple(
                problem
                for problem in problem_records
                if problem.start_offset is not None
                and problem.end_offset is not None
                and problem.start_offset <= offset < problem.end_offset
            )
            problem_ids = tuple(problem.record_id for problem in problems)
            is_gap = text[offset].isspace() and not unit_ids and not problems
            end = offset + 1
            while (
                end < len(text)
                and tuple(sorted(set(owners[end]))) == unit_ids
                and tuple(
                    problem.record_id
                    for problem in problem_records
                    if problem.start_offset is not None
                    and problem.end_offset is not None
                    and problem.start_offset <= end < problem.end_offset
                )
                == problem_ids
                and (text[end].isspace() and not unit_ids and not problems) == is_gap
            ):
                end += 1
            if unit_ids:
                status: CoverageStatus = "covered"
                reason = "anchored_text_unit"
            elif problems:
                status = "unsupported"
                reason = problems[0].reason
            elif is_gap:
                status = "covered"
                reason = "normalized_source_gap"
            else:
                status = "uncovered"
                reason = "no_valid_source_element"
            records.append(
                CoverageRecord(
                    record_id=stable_id(
                        "coverage",
                        snapshot.snapshot_id,
                        status,
                        str(offset),
                        str(end),
                        *unit_ids,
                    ),
                    status=status,
                    scope="source_range",
                    reason=reason,
                    snapshot_id=snapshot.snapshot_id,
                    start_offset=offset,
                    end_offset=end,
                    section_id=problems[0].section_id if len(problems) == 1 else None,
                    unit_ids=unit_ids,
                    detail=(
                        "multiple_units_overlap"
                        if len(unit_ids) > 1
                        else problems[0].record_id
                        if len(problems) == 1
                        else ",".join(problem_ids)
                        if problems
                        else None
                    ),
                )
            )
            offset = end
        return tuple(records)

    @staticmethod
    def _source_ranges(
        snapshot: SourceDocumentSnapshot,
        text: str,
        records: tuple[CoverageRecord, ...],
    ) -> tuple[SourceRangeRecord, ...]:
        ranges: list[SourceRangeRecord] = []
        for record in records:
            if record.scope != "source_range":
                continue
            assert record.start_offset is not None
            assert record.end_offset is not None
            exact_text = text[record.start_offset : record.end_offset]
            kind: SourceRangeKind
            if record.unit_ids:
                kind = "unit"
            elif record.status == "unsupported":
                kind = "unsupported"
            elif record.status == "uncovered":
                kind = "uncovered"
            else:
                kind = "gap"
            ranges.append(
                SourceRangeRecord(
                    range_id=stable_id(
                        "source_range",
                        snapshot.snapshot_id,
                        str(record.start_offset),
                        str(record.end_offset),
                        kind,
                    ),
                    snapshot_id=snapshot.snapshot_id,
                    schema_version="source-range.v1",
                    start_offset=record.start_offset,
                    end_offset=record.end_offset,
                    kind=kind,
                    content_hash=_text_hash(exact_text),
                    unit_ids=record.unit_ids,
                    reason=(record.reason if kind in {"unsupported", "uncovered"} else None),
                )
            )
        return tuple(ranges)

    @staticmethod
    def _structure_coverage(
        snapshot: SourceDocumentSnapshot,
        candidates: tuple[_Candidate, ...],
    ) -> tuple[CoverageRecord, ...]:
        records: list[CoverageRecord] = []
        for candidate in candidates:
            section = candidate.section
            missing: list[str] = []
            if section.kind is None:
                missing.append("kind")
            if not section.heading_trail:
                missing.append("heading_trail")
            if section.parent_element_id is None:
                missing.append("parent")
            if section.element_id is None:
                missing.append("element")
            if section.page is None:
                missing.append("page")
            if section.bounding_box is None:
                missing.append("bounding_box")
            if not missing:
                continue
            reason = f"xberg_structure_unavailable:{','.join(missing)}"
            records.append(
                CoverageRecord(
                    record_id=stable_id(
                        "coverage",
                        snapshot.snapshot_id,
                        "structure",
                        section.section_id,
                        reason,
                    ),
                    status="unsupported",
                    scope="structure",
                    reason=reason,
                    snapshot_id=snapshot.snapshot_id,
                    section_id=section.section_id,
                    unit_ids=(candidate.unit_id,),
                )
            )
        return tuple(records)

    @staticmethod
    def _coverage_report(
        snapshot: SourceDocumentSnapshot,
        text: str,
        records: tuple[CoverageRecord, ...],
    ) -> CoverageReport:
        transformations = tuple(
            finding.split(":", 1)[1].strip()
            for finding in snapshot.parse_findings
            if finding.lower().startswith(("normalization:", "normalized:")) and ":" in finding
        )
        payload = {
            "snapshot_id": snapshot.snapshot_id,
            "document_id": snapshot.document_id,
            "source_length": len(text),
            "records": [_coverage_value(record) for record in records],
            "normalization_transformations": transformations,
        }
        return CoverageReport(
            schema_version="coverage-report.v1",
            snapshot_id=snapshot.snapshot_id,
            document_id=snapshot.document_id,
            source_length=len(text),
            records=records,
            normalization_transformations=transformations,
            content_digest=_digest(payload),
        )

    @staticmethod
    def _coverage_manifest(
        snapshot: SourceDocumentSnapshot,
        text: str,
        range_records: tuple[CoverageRecord, ...],
        element_records: tuple[CoverageRecord, ...],
        structure_records: tuple[CoverageRecord, ...],
        capability_records: tuple[CoverageRecord, ...],
    ) -> SourcePlaneCoverageManifest:
        payload = {
            "schema_version": "source-plane-coverage.v1",
            "snapshot_id": snapshot.snapshot_id,
            "source_length": len(text),
            "range_coverage": [_coverage_value(item) for item in range_records],
            "element_coverage": [_coverage_value(item) for item in element_records],
            "structure_coverage": [_coverage_value(item) for item in structure_records],
            "capability_coverage": [_coverage_value(item) for item in capability_records],
        }
        return SourcePlaneCoverageManifest(
            schema_version="source-plane-coverage.v1",
            snapshot_id=snapshot.snapshot_id,
            source_length=len(text),
            range_coverage=range_records,
            element_coverage=element_records,
            structure_coverage=structure_records,
            capability_coverage=capability_records,
            content_digest=_digest(payload),
        )


def unitize_snapshot(
    snapshot: SourceDocumentSnapshot,
    normalized_text: str,
) -> UnitizationResult:
    """Convenience entry point for the deterministic Source Plane unitizer."""

    return DeterministicUnitizer().unitize(snapshot, normalized_text)


def _text_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _structural_path(
    element_id: str | None,
    section_id: str,
    element_by_id: dict[str, SourceElement],
) -> tuple[str, ...]:
    if element_id is None or element_id not in element_by_id:
        return (section_id,)
    path: list[str] = []
    visited: set[str] = set()
    current_id: str | None = element_id
    while current_id is not None and current_id in element_by_id:
        if current_id in visited:
            break
        visited.add(current_id)
        path.append(current_id)
        current_id = element_by_id[current_id].parent_element_id
    path.reverse()
    return (*path, section_id)


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _unit_value(unit: AnchoredTextUnit) -> object:
    return {
        "unit_id": unit.unit_id,
        "schema_version": unit.schema_version,
        "snapshot_id": unit.snapshot_id,
        "document_id": unit.document_id,
        "revision_id": unit.revision_id,
        "ordinal": unit.ordinal,
        "kind": unit.kind,
        "exact_text": unit.exact_text,
        "content_hash": unit.content_hash,
        "structural_path": unit.structural_path,
        "heading_trail": unit.heading_trail,
        "source_references": [
            (
                reference.reference_id,
                reference.section_id,
                reference.anchor_id,
                reference.start_offset,
                reference.end_offset,
                reference.exact_text,
                reference.prefix,
                reference.suffix,
                reference.page,
                reference.bounding_box,
                reference.element_id,
                reference.textual_anchor,
                reference.kind,
                reference.parent_element_id,
                reference.heading_trail,
            )
            for reference in unit.source_references
        ],
        "parent_unit_id": unit.parent_unit_id,
        "previous_unit_id": unit.previous_unit_id,
        "next_unit_id": unit.next_unit_id,
    }


def _source_range_value(source_range: SourceRangeRecord) -> object:
    return {
        "range_id": source_range.range_id,
        "snapshot_id": source_range.snapshot_id,
        "schema_version": source_range.schema_version,
        "start_offset": source_range.start_offset,
        "end_offset": source_range.end_offset,
        "kind": source_range.kind,
        "content_hash": source_range.content_hash,
        "unit_ids": source_range.unit_ids,
        "reason": source_range.reason,
    }


def _coverage_value(record: CoverageRecord) -> object:
    return (
        record.record_id,
        record.status,
        record.scope,
        record.reason,
        record.start_offset,
        record.end_offset,
        record.section_id,
        record.unit_ids,
        record.detail,
    )

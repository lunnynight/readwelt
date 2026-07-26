"""Deterministic conversion of source snapshots into anchored text units."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from readwelt.domain.documents import DocumentSection, SourceDocumentSnapshot
from readwelt.domain.ids import stable_id

from .models import (
    AnchoredTextUnit,
    CoverageRecord,
    CoverageReport,
    CoverageStatus,
    SourceReference,
    UnitizationResult,
)

_UNIT_SCHEMA = "anchored-text-unit.v1"
_UNITIZATION_SCHEMA = "anchored-text-unitization.v1"


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
        structure_records = self._structure_coverage(snapshot, candidates)
        represented_problem_ids = {
            record.detail
            for record in range_records
            if record.status == "unsupported" and record.detail is not None
        }
        unplaced_problems = tuple(
            record
            for record in problem_records
            if record.record_id not in represented_problem_ids
        )
        records = tuple((*range_records, *unplaced_problems, *structure_records))
        coverage = self._coverage_report(snapshot, normalized_text, records)
        payload = {
            "schema_version": self.schema_version,
            "snapshot_id": snapshot.snapshot_id,
            "units": [_unit_value(unit) for unit in units],
            "coverage_digest": coverage.content_digest,
        }
        return UnitizationResult(
            schema_version=self.schema_version,
            snapshot_id=snapshot.snapshot_id,
            units=units,
            coverage=coverage,
            content_digest=_digest(payload),
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
                    structural_path=(section.section_id,),
                    heading_trail=(
                        section.heading_trail
                        if section.heading_trail
                        else (section.title,)
                        if section.title is not None
                        else ()
                    ),
                    source_references=(reference,),
                    previous_unit_id=candidates[ordinal - 1].unit_id if ordinal else None,
                    next_unit_id=(
                        candidates[ordinal + 1].unit_id
                        if ordinal + 1 < len(candidates)
                        else None
                    ),
                )
            )
        return tuple(units)

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
            if text[offset].isspace():
                offset += 1
                continue
            unit_ids = tuple(sorted(set(owners[offset])))
            problems = tuple(
                problem
                for problem in problem_records
                if problem.start_offset is not None
                and problem.end_offset is not None
                and problem.start_offset <= offset < problem.end_offset
            )
            problem_ids = tuple(problem.record_id for problem in problems)
            end = offset + 1
            while (
                end < len(text)
                and not text[end].isspace()
                and tuple(sorted(set(owners[end]))) == unit_ids
                and tuple(
                    problem.record_id
                    for problem in problem_records
                    if problem.start_offset is not None
                    and problem.end_offset is not None
                    and problem.start_offset <= end < problem.end_offset
                )
                == problem_ids
            ):
                end += 1
            if unit_ids:
                status: CoverageStatus = "covered"
                reason = "anchored_text_unit"
            elif problems:
                status = "unsupported"
                reason = problems[0].reason
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
            if finding.lower().startswith(("normalization:", "normalized:"))
            and ":" in finding
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


def unitize_snapshot(
    snapshot: SourceDocumentSnapshot,
    normalized_text: str,
) -> UnitizationResult:
    """Convenience entry point for the deterministic v1 unitizer."""

    return DeterministicUnitizer().unitize(snapshot, normalized_text)


def _text_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


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

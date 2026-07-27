"""Corpus and Source Plane acceptance helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence

from benchmarks.articlegraph.long_document_models import (
    DocumentMeasurement,
    LongDocumentCase,
)


def validate_required_corpus(cases: Iterable[LongDocumentCase]) -> tuple[str, ...]:
    """Return missing acceptance dimensions instead of silently weakening corpus."""

    settled = tuple(cases)
    formats = {case.source_format for case in settled}
    languages = {case.language.casefold() for case in settled}
    structures = {case.structure_kind.casefold() for case in settled}
    tags = {tag.casefold() for case in settled for tag in case.corpus_tags}
    missing: list[str] = []
    for required_format in ("txt", "html", "native_pdf", "scanned_pdf", "epub"):
        if required_format not in formats:
            missing.append(f"format:{required_format}")
    if not any(language.startswith("zh") for language in languages):
        missing.append("language:zh")
    if not any(language.startswith("en") for language in languages):
        missing.append("language:en")
    for required_structure in ("argument", "exposition", "narrative"):
        if required_structure not in structures:
            missing.append(f"structure:{required_structure}")
    for required_tag in (
        "repeated_passages",
        "quotations",
        "tables",
        "figures",
        "captions",
        "numbers",
        "missing_structure",
    ):
        if required_tag not in tags:
            missing.append(f"tag:{required_tag}")
    if not any(case.length_class == "100k_plus" for case in settled):
        missing.append("length:100k_plus")
    return tuple(missing)


def acceptance_failures(
    documents: Sequence[DocumentMeasurement],
    *,
    hard_serialized_token_budget: int,
) -> tuple[str, ...]:
    failures: list[str] = []
    coverage_fields = (
        "source_unit_coverage",
        "source_range_coverage",
        "source_element_coverage",
        "source_root_coverage",
        "traversal_visited_coverage",
        "traversal_presented_coverage",
        "traversal_range_visited_coverage",
        "traversal_range_presented_coverage",
        "traversal_element_visited_coverage",
        "traversal_element_presented_coverage",
        "traversal_source_root_visited_coverage",
        "traversal_source_root_presented_coverage",
    )
    for document in documents:
        for field_name in coverage_fields:
            if getattr(document, field_name) != 1.0:
                failures.append(
                    f"{document.case_id}:{field_name}:"
                    f"{getattr(document, field_name):.6f}"
                )
        if not document.traversal_complete:
            failures.append(f"{document.case_id}:traversal_incomplete")
        if not document.structural_reference_closure:
            failures.extend(
                f"{document.case_id}:structural_reference_closure:{failure}"
                for failure in document.structural_reference_failures
            )
        if not document.hard_budget_respected:
            failures.append(f"{document.case_id}:hard_budget_exceeded")
        if document.cursor_loop_detected:
            failures.append(f"{document.case_id}:cursor_loop_detected")
        lexical = next(
            (
                strategy
                for strategy in document.strategies
                if strategy.strategy == "lexical"
            ),
            None,
        )
        if lexical is None or not lexical.enabled:
            failures.append(f"{document.case_id}:lexical_control_not_enabled")
        elif lexical.input_tokens > hard_serialized_token_budget:
            failures.append(f"{document.case_id}:lexical_control_budget_exceeded")
        elif (
            lexical.must_hit_recall != 1.0
            or lexical.critical_anchor_miss_rate != 0.0
        ):
            failures.append(f"{document.case_id}:lexical_must_hit_gate_failed")
    return tuple(failures)


def source_range_coverage(case: LongDocumentCase) -> float:
    ranges = case.build.unitization.source_ranges
    if not ranges:
        return 1.0 if case.build.unitization.coverage.source_length == 0 else 0.0
    valid = 0
    for record in ranges:
        exact_text = case.normalized_text[record.start_offset : record.end_offset]
        digest = f"sha256:{hashlib.sha256(exact_text.encode()).hexdigest()}"
        if (
            digest == record.content_hash
            and case.build.unitization.range_at(record.start_offset) == record
            and case.build.unitization.range_at(record.end_offset - 1) == record
            and case.build.source_index.range_at_offset(record.start_offset)
            == record.range_id
        ):
            valid += 1
    return valid / len(ranges)


def source_unit_coverage(case: LongDocumentCase) -> float:
    units = case.build.unitization.units
    if not units:
        return 1.0 if not case.normalized_text else 0.0
    indexed = frozenset(case.build.source_index.source_unit_ids)
    valid = 0
    for unit in units:
        reference = unit.source_references[0] if unit.source_references else None
        if (
            unit.unit_id in indexed
            and reference is not None
            and reference.start_offset is not None
            and reference.end_offset is not None
            and case.normalized_text[
                reference.start_offset : reference.end_offset
            ]
            == unit.exact_text
        ):
            valid += 1
    return valid / len(units)


def source_element_coverage(case: LongDocumentCase) -> float:
    elements = case.build.unitization.source_elements
    if not elements:
        return 1.0
    indexed = frozenset(case.build.source_index.source_element_ids)
    manifest = case.build.unitization.coverage_manifest
    covered_records = (
        {
            record.detail
            for record in manifest.element_coverage
            if record.detail is not None
        }
        if manifest is not None
        else set()
    )
    valid = sum(
        element.element_id in indexed and element.element_id in covered_records
        for element in elements
    )
    return valid / len(elements)


def source_root_coverage(case: LongDocumentCase) -> float:
    roots = tuple(
        element
        for element in case.build.unitization.source_elements
        if element.kind == "source_document"
    )
    if not roots:
        return 0.0
    indexed = frozenset(case.build.source_index.source_element_ids)
    manifest = case.build.unitization.coverage_manifest
    covered_records = (
        {
            record.detail
            for record in manifest.element_coverage
            if record.status == "covered" and record.detail is not None
        }
        if manifest is not None
        else set()
    )
    valid = sum(
        root.element_id in indexed
        and root.element_id in covered_records
        and root.raw_payload_ref is not None
        for root in roots
    )
    return valid / len(roots)


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = fraction * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

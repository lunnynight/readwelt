"""Benchmark orchestration over stable model and measurement modules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict

from benchmarks.articlegraph.long_document_acceptance import (
    acceptance_failures,
    percentile,
    source_element_coverage,
    source_range_coverage,
    source_root_coverage,
    source_unit_coverage,
)
from benchmarks.articlegraph.long_document_measurement import (
    measure_strategy,
    must_hit_targets,
)
from benchmarks.articlegraph.long_document_models import (
    STRATEGIES,
    CandidateProvider,
    DocumentMeasurement,
    LongDocumentBenchmarkReport,
    LongDocumentCase,
)
from benchmarks.articlegraph.long_document_traversal import (
    bounded_traversal,
    coverage_fraction,
)
from readwelt.token_budget import DEFAULT_TOKEN_COUNTER


def run_long_document_benchmark(
    cases: Iterable[LongDocumentCase],
    *,
    token_budget: int,
    hard_serialized_token_budget: int,
    dense_candidates: CandidateProvider | None = None,
    reranked_candidates: CandidateProvider | None = None,
    max_pages: int = 10_000,
) -> LongDocumentBenchmarkReport:
    """Run source acceptance, bounded traversal, and like-budget baselines."""

    settled_cases = tuple(cases)
    if not settled_cases:
        raise ValueError("long-document benchmark requires at least one case")
    if token_budget < 1 or hard_serialized_token_budget < 1:
        raise ValueError("benchmark budgets must be positive")
    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    documents = tuple(
        _measure_document(
            case,
            token_budget=token_budget,
            hard_serialized_token_budget=hard_serialized_token_budget,
            dense_candidates=dense_candidates,
            reranked_candidates=reranked_candidates,
            max_pages=max_pages,
        )
        for case in settled_cases
    )
    tags = tuple(
        sorted(
            {
                *(f"format:{case.source_format}" for case in settled_cases),
                *(f"language:{case.language}" for case in settled_cases),
                *(f"length:{case.length_class}" for case in settled_cases),
                *(tag for case in settled_cases for tag in case.corpus_tags),
            }
        )
    )
    failures = acceptance_failures(
        documents,
        hard_serialized_token_budget=hard_serialized_token_budget,
    )
    payload = {
        "schema_version": "articlegraph-long-document-benchmark.v2",
        "token_budget": token_budget,
        "hard_serialized_token_budget": hard_serialized_token_budget,
        "token_counter_id": DEFAULT_TOKEN_COUNTER.counter_id,
        "token_count_mode": DEFAULT_TOKEN_COUNTER.mode.value,
        "token_count_guarantee": DEFAULT_TOKEN_COUNTER.guarantee,
        "documents": [asdict(document) for document in documents],
        "corpus_tags": tags,
        "acceptance_passed": not failures,
        "acceptance_failures": failures,
    }
    return LongDocumentBenchmarkReport(
        schema_version="articlegraph-long-document-benchmark.v2",
        token_budget=token_budget,
        hard_serialized_token_budget=hard_serialized_token_budget,
        token_counter_id=DEFAULT_TOKEN_COUNTER.counter_id,
        token_count_mode=DEFAULT_TOKEN_COUNTER.mode.value,
        token_count_guarantee=DEFAULT_TOKEN_COUNTER.guarantee,
        documents=documents,
        corpus_tags=tags,
        acceptance_passed=not failures,
        acceptance_failures=failures,
        content_digest=_digest(payload),
    )


def merge_long_document_reports(
    reports: Iterable[LongDocumentBenchmarkReport],
) -> LongDocumentBenchmarkReport:
    """Merge sequential per-document runs without retaining every build in memory."""

    settled = tuple(reports)
    if not settled:
        raise ValueError("at least one long-document report is required")
    first = settled[0]
    identity = (
        first.schema_version,
        first.token_budget,
        first.hard_serialized_token_budget,
        first.token_counter_id,
        first.token_count_mode,
        first.token_count_guarantee,
    )
    if any(
        (
            report.schema_version,
            report.token_budget,
            report.hard_serialized_token_budget,
            report.token_counter_id,
            report.token_count_mode,
            report.token_count_guarantee,
        )
        != identity
        for report in settled[1:]
    ):
        raise ValueError("long-document reports use incompatible benchmark policies")
    documents = tuple(
        document
        for report in settled
        for document in report.documents
    )
    case_ids = tuple(document.case_id for document in documents)
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("long-document reports contain duplicate cases")
    tags = tuple(sorted({tag for report in settled for tag in report.corpus_tags}))
    failures = acceptance_failures(
        documents,
        hard_serialized_token_budget=first.hard_serialized_token_budget,
    )
    payload = {
        "schema_version": first.schema_version,
        "token_budget": first.token_budget,
        "hard_serialized_token_budget": first.hard_serialized_token_budget,
        "token_counter_id": first.token_counter_id,
        "token_count_mode": first.token_count_mode,
        "token_count_guarantee": first.token_count_guarantee,
        "documents": [asdict(document) for document in documents],
        "corpus_tags": tags,
        "acceptance_passed": not failures,
        "acceptance_failures": failures,
    }
    return LongDocumentBenchmarkReport(
        schema_version=first.schema_version,
        token_budget=first.token_budget,
        hard_serialized_token_budget=first.hard_serialized_token_budget,
        token_counter_id=first.token_counter_id,
        token_count_mode=first.token_count_mode,
        token_count_guarantee=first.token_count_guarantee,
        documents=documents,
        corpus_tags=tags,
        acceptance_passed=not failures,
        acceptance_failures=failures,
        content_digest=_digest(payload),
    )


def _measure_document(
    case: LongDocumentCase,
    *,
    token_budget: int,
    hard_serialized_token_budget: int,
    dense_candidates: CandidateProvider | None,
    reranked_candidates: CandidateProvider | None,
    max_pages: int,
) -> DocumentMeasurement:
    unit_coverage = source_unit_coverage(case)
    range_coverage = source_range_coverage(case)
    element_coverage = source_element_coverage(case)
    root_coverage = source_root_coverage(case)
    targets = must_hit_targets(case)
    traversal = bounded_traversal(
        case,
        token_budget=token_budget,
        hard_serialized_token_budget=hard_serialized_token_budget,
        max_pages=max_pages,
    )
    strategies = tuple(
        measure_strategy(
            strategy,
            case,
            targets=targets,
            token_budget=token_budget,
            hard_serialized_token_budget=hard_serialized_token_budget,
            traversal=traversal,
            dense_candidates=dense_candidates,
            reranked_candidates=reranked_candidates,
        )
        for strategy in STRATEGIES
    )
    manifest = case.build.unitization.coverage_manifest
    unresolved = (
        sum(
            record.status != "covered"
            for records in (
                manifest.element_coverage,
                manifest.structure_coverage,
                manifest.capability_coverage,
            )
            for record in records
        )
        if manifest is not None
        else 1
    )
    ingestion_failures = (
        {
            f"ingestion:{record.reason}"
            for record in manifest.capability_coverage
            if record.status == "unsupported"
        }
        if manifest is not None
        else {"ingestion:source_plane_coverage_manifest_missing"}
    )
    structural_reference_failures = tuple(
        sorted(
            record.reason
            for record in manifest.capability_coverage
            if record.status == "unsupported"
            and record.reason.startswith(
                (
                    "source_element_parent_unresolved:",
                    "source_element_children_unresolved:",
                    "source_element_relations_unresolved:",
                )
            )
        )
        if manifest is not None
        else ("source_plane_coverage_manifest_missing",)
    )
    failures = tuple(
        sorted(
            ingestion_failures
            | {
                (
                    f"{extraction.backend.backend_id}:"
                    f"{outcome.capability.value}:{outcome.status.value}"
                )
                for extraction in case.build.extractions
                for outcome in extraction.outcomes
                if outcome.status.value == "failed"
            }
        )
    )
    unit_count = len(case.build.unitization.units)
    source_root_ids = tuple(
        element.element_id
        for element in case.build.unitization.source_elements
        if element.kind == "source_document"
    )
    return DocumentMeasurement(
        case_id=case.case_id,
        source_format=case.source_format,
        language=case.language,
        length_class=case.length_class,
        structure_kind=case.structure_kind,
        backend_configuration=case.backend_configuration,
        source_unit_coverage=unit_coverage,
        source_range_coverage=range_coverage,
        source_element_coverage=element_coverage,
        source_root_coverage=root_coverage,
        structural_reference_closure=not structural_reference_failures,
        structural_reference_failures=structural_reference_failures,
        traversal_visited_coverage=(
            len(traversal.visited_unit_ids) / unit_count if unit_count else 1.0
        ),
        traversal_presented_coverage=(
            len(traversal.presented_unit_ids) / unit_count if unit_count else 1.0
        ),
        traversal_range_visited_coverage=coverage_fraction(
            traversal.visited_range_ids,
            case.build.source_index.source_range_ids,
        ),
        traversal_range_presented_coverage=coverage_fraction(
            traversal.presented_range_ids,
            case.build.source_index.source_range_ids,
        ),
        traversal_element_visited_coverage=coverage_fraction(
            traversal.visited_element_ids,
            case.build.source_index.source_element_ids,
        ),
        traversal_element_presented_coverage=coverage_fraction(
            traversal.presented_element_ids,
            case.build.source_index.source_element_ids,
        ),
        traversal_source_root_visited_coverage=coverage_fraction(
            tuple(
                element_id
                for element_id in source_root_ids
                if element_id in traversal.visited_element_ids
            ),
            source_root_ids,
        ),
        traversal_source_root_presented_coverage=coverage_fraction(
            tuple(
                element_id
                for element_id in source_root_ids
                if element_id in traversal.presented_element_ids
            ),
            source_root_ids,
        ),
        traversal_complete=traversal.complete,
        hard_budget_respected=traversal.hard_budget_respected,
        cursor_loop_detected=traversal.cursor_loop_detected,
        traversal_page_count=len(traversal.page_latencies_ms),
        traversal_input_tokens=traversal.input_tokens,
        traversal_p50_latency_ms=percentile(traversal.page_latencies_ms, 0.50),
        traversal_p95_latency_ms=percentile(traversal.page_latencies_ms, 0.95),
        peak_memory_bytes=traversal.peak_memory_bytes,
        backend_failures=failures,
        unresolved_projections=unresolved,
        strategies=strategies,
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

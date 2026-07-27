"""Bounded Source Plane traversal measurement."""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Sequence
from dataclasses import dataclass, replace

from benchmarks.articlegraph.long_document_models import LongDocumentCase
from readwelt.domain import ReadingStage
from readwelt.stage_views import StageContext, StageViewProjector


@dataclass(frozen=True, slots=True)
class TraversalMeasurement:
    complete: bool
    hard_budget_respected: bool
    cursor_loop_detected: bool
    visited_unit_ids: tuple[str, ...]
    presented_unit_ids: tuple[str, ...]
    visited_range_ids: tuple[str, ...]
    presented_range_ids: tuple[str, ...]
    visited_element_ids: tuple[str, ...]
    presented_element_ids: tuple[str, ...]
    input_tokens: int
    page_latencies_ms: tuple[float, ...]
    peak_memory_bytes: int


def bounded_traversal(
    case: LongDocumentCase,
    *,
    token_budget: int,
    hard_serialized_token_budget: int,
    max_pages: int,
) -> TraversalMeasurement:
    projector = StageViewProjector()
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="benchmark deterministic complete source traversal",
        token_budget=token_budget,
        hard_serialized_token_budget=hard_serialized_token_budget,
        rescue_level="section",
    )
    cursor_digests: set[str] = set()
    visited: set[str] = set()
    presented: set[str] = set()
    visited_ranges: set[str] = set()
    presented_ranges: set[str] = set()
    visited_elements: set[str] = set()
    presented_elements: set[str] = set()
    blocked: set[str] = set()
    page_latencies: list[float] = []
    input_tokens = 0
    hard_budget_respected = True
    cursor_loop = False

    tracemalloc.start()
    try:
        for _ in range(max_pages):
            started = time.perf_counter()
            view = projector.project(case.build, context)
            try:
                mapping = view.to_mapping()
            except ValueError as exc:
                raise ValueError(
                    "provider-bound StageView budget failure "
                    f"for {case.case_id} page {len(page_latencies) + 1}: "
                    f"nodes={len(view.nodes)}, edges={len(view.edges)}, "
                    f"text_units={len(view.text_units)}, "
                    f"omitted={len(view.coverage.omitted) if view.coverage else 0}, "
                    f"hard_budget={hard_serialized_token_budget}"
                ) from exc
            page_latencies.append((time.perf_counter() - started) * 1_000)
            serialized_value = mapping["estimated_serialized_tokens"]
            if not isinstance(serialized_value, int):
                raise TypeError("serialized token estimate must be an integer")
            serialized_tokens = serialized_value
            input_tokens += serialized_tokens
            hard_budget_respected &= (
                serialized_tokens <= hard_serialized_token_budget
            )
            if view.coverage is not None:
                visited.update(view.coverage.visited_unit_ids)
                presented.update(view.coverage.completed_unit_ids)
                visited_ranges.update(view.coverage.visited_range_ids)
                presented_ranges.update(view.coverage.completed_range_ids)
                visited_elements.update(view.coverage.visited_element_ids)
                presented_elements.update(view.coverage.completed_element_ids)
            blocked.update(
                identity
                for record in view.blocking_records
                if (
                    identity := (
                        record.source_unit_id
                        or record.source_range_id
                        or record.source_element_id
                    )
                )
            )
            if view.continuation is None:
                break
            if view.continuation.content_digest in cursor_digests:
                cursor_loop = True
                break
            cursor_digests.add(view.continuation.content_digest)
            context = replace(context, continuation=view.continuation)
        else:
            cursor_loop = True
        _, peak_memory = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    source_units = frozenset(case.build.source_index.source_unit_ids)
    source_ranges = frozenset(case.build.source_index.source_range_ids)
    source_elements = frozenset(case.build.source_index.source_element_ids)
    return TraversalMeasurement(
        complete=(
            not cursor_loop
            and source_units.issubset(visited)
            and source_units.issubset(presented | blocked)
            and source_ranges.issubset(visited_ranges)
            and source_ranges.issubset(presented_ranges | blocked)
            and source_elements.issubset(visited_elements)
            and source_elements.issubset(presented_elements | blocked)
        ),
        hard_budget_respected=hard_budget_respected,
        cursor_loop_detected=cursor_loop,
        visited_unit_ids=tuple(
            unit_id
            for unit_id in case.build.source_index.source_unit_ids
            if unit_id in visited
        ),
        presented_unit_ids=tuple(
            unit_id
            for unit_id in case.build.source_index.source_unit_ids
            if unit_id in presented
        ),
        visited_range_ids=tuple(
            range_id
            for range_id in case.build.source_index.source_range_ids
            if range_id in visited_ranges
        ),
        presented_range_ids=tuple(
            range_id
            for range_id in case.build.source_index.source_range_ids
            if range_id in presented_ranges or range_id in blocked
        ),
        visited_element_ids=tuple(
            element_id
            for element_id in case.build.source_index.source_element_ids
            if element_id in visited_elements
        ),
        presented_element_ids=tuple(
            element_id
            for element_id in case.build.source_index.source_element_ids
            if element_id in presented_elements or element_id in blocked
        ),
        input_tokens=input_tokens,
        page_latencies_ms=tuple(page_latencies),
        peak_memory_bytes=peak_memory,
    )


def coverage_fraction(
    visited: Sequence[str],
    source: Sequence[str],
) -> float:
    return len(visited) / len(source) if source else 1.0

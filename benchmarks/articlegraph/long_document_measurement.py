"""Equal-budget locating-candidate measurements."""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Iterable, Mapping, Sequence

from benchmarks.articlegraph.long_document_models import (
    CandidateProvider,
    LongDocumentCase,
    RetrievalStrategy,
    StrategyMeasurement,
)
from benchmarks.articlegraph.long_document_traversal import TraversalMeasurement
from readwelt.token_budget import DEFAULT_TOKEN_COUNTER


def measure_strategy(
    strategy: RetrievalStrategy,
    case: LongDocumentCase,
    *,
    targets: Mapping[str, tuple[str, ...]],
    token_budget: int,
    hard_serialized_token_budget: int,
    traversal: TraversalMeasurement,
    dense_candidates: CandidateProvider | None,
    reranked_candidates: CandidateProvider | None,
) -> StrategyMeasurement:
    started = time.perf_counter()
    tracemalloc.start()
    enabled = True
    reason: str | None = None
    page_count = 1
    fallback_rate = 0.0

    try:
        if strategy == "full_text":
            candidates = case.build.source_index.source_unit_ids
            if estimated_unit_tokens(case, candidates) > token_budget:
                enabled = False
                reason = "full_text_exceeds_identical_token_budget"
                candidates = ()
        elif strategy == "lexical":
            candidates = lexical_candidates(case)
        elif strategy == "dense":
            if dense_candidates is None:
                enabled = False
                reason = "dense_backend_not_enabled"
                candidates = ()
            else:
                candidates = external_candidates(case, dense_candidates)
        elif strategy == "hybrid":
            if dense_candidates is None:
                enabled = False
                reason = "dense_backend_not_enabled_for_hybrid"
                candidates = ()
            else:
                candidates = tuple(
                    dict.fromkeys(
                        (
                            *lexical_candidates(case),
                            *external_candidates(case, dense_candidates),
                        )
                    )
                )
        elif strategy == "reranking":
            if reranked_candidates is None:
                enabled = False
                reason = "reranking_backend_not_enabled"
                candidates = ()
            else:
                candidates = external_candidates(case, reranked_candidates)
        else:
            candidates = traversal.presented_unit_ids
            page_count = len(traversal.page_latencies_ms)
            fallback_rate = 0.0

        if strategy == "source_coverage_rescue":
            selected = candidates
            input_tokens = traversal.input_tokens
        elif enabled:
            selected, input_tokens = fit_candidate_packet(
                case,
                candidates,
                targets=targets,
                token_budget=token_budget,
                hard_serialized_token_budget=hard_serialized_token_budget,
            )
            if candidates and not selected:
                enabled = False
                reason = "smallest_candidate_packet_exceeds_hard_serialized_budget"
                input_tokens = 0
        else:
            selected = ()
            input_tokens = 0
        recall_value, miss_rate = (
            recall(targets, selected) if enabled else (0.0, 1.0)
        )
        _, peak_memory = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    return StrategyMeasurement(
        strategy=strategy,
        enabled=enabled,
        must_hit_recall=recall_value,
        critical_anchor_miss_rate=miss_rate,
        input_tokens=input_tokens,
        full_text_fallback_rate=fallback_rate,
        page_count=page_count,
        latency_ms=(time.perf_counter() - started) * 1_000,
        peak_memory_bytes=peak_memory,
        selected_unit_ids=tuple(selected),
        reason=reason,
    )


def must_hit_targets(case: LongDocumentCase) -> dict[str, tuple[str, ...]]:
    targets = {
        query: case.build.source_index.locate_lexical(query).unit_ids
        for query in case.must_hit_queries
    }
    unresolved = tuple(query for query, unit_ids in targets.items() if not unit_ids)
    if unresolved:
        raise ValueError(
            f"must-hit queries do not resolve in {case.case_id}: {unresolved}"
        )
    return targets


def lexical_candidates(case: LongDocumentCase) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            unit_id
            for query in case.must_hit_queries
            for unit_id in case.build.source_index.locate_lexical(query).unit_ids
        )
    )


def external_candidates(
    case: LongDocumentCase,
    provider: CandidateProvider,
) -> tuple[str, ...]:
    valid = frozenset(case.build.source_index.source_unit_ids)
    return tuple(
        dict.fromkeys(
            unit_id
            for query in case.must_hit_queries
            for unit_id in provider(case, query)
            if unit_id in valid
        )
    )


def fit_candidate_packet(
    case: LongDocumentCase,
    candidates: Sequence[str],
    *,
    targets: Mapping[str, tuple[str, ...]],
    token_budget: int,
    hard_serialized_token_budget: int,
) -> tuple[tuple[str, ...], int]:
    """Fit ranked locating fragments against content and final-envelope budgets."""

    by_id = {unit.unit_id: unit for unit in case.build.unitization.units}
    ranked = tuple(
        dict.fromkeys(unit_id for unit_id in candidates if unit_id in by_id)
    )
    for count in range(len(ranked), 0, -1):
        selected = ranked[:count]
        envelope = candidate_packet_envelope(
            case,
            selected,
            targets=targets,
            token_budget=token_budget,
        )
        if envelope is None:
            continue
        measured = DEFAULT_TOKEN_COUNTER.count_json(envelope).tokens
        if measured <= hard_serialized_token_budget:
            return selected, measured
    return (), 0


def estimated_unit_tokens(
    case: LongDocumentCase,
    unit_ids: Sequence[str],
) -> int:
    by_id = {unit.unit_id: unit for unit in case.build.unitization.units}
    return sum(
        (len(by_id[unit_id].exact_text.encode()) + 3) // 4
        for unit_id in unit_ids
        if unit_id in by_id
    )


def candidate_packet_envelope(
    case: LongDocumentCase,
    unit_ids: Sequence[str],
    *,
    targets: Mapping[str, tuple[str, ...]],
    token_budget: int,
) -> dict[str, object] | None:
    by_id = {unit.unit_id: unit for unit in case.build.unitization.units}
    base_spans = {
        unit_id: locating_spans(
            by_id[unit_id].exact_text,
            tuple(
                query
                for query, target_ids in targets.items()
                if unit_id in target_ids
            ),
        )
        for unit_id in unit_ids
        if unit_id in by_id
    }
    if not base_spans:
        return None
    maximum_radius = max(
        len(by_id[unit_id].exact_text)
        for unit_id in base_spans
    )
    low = 0
    high = maximum_radius
    best: dict[str, object] | None = None
    while low <= high:
        radius = (low + high) // 2
        selected_units: list[dict[str, object]] = []
        content_parts: list[str] = []
        for unit_id in base_spans:
            fragments: list[dict[str, object]] = []
            for start, end in expanded_spans(
                base_spans[unit_id],
                radius,
                len(by_id[unit_id].exact_text),
            ):
                fragment_text = by_id[unit_id].exact_text[start:end]
                fragments.append(
                    {
                        "start_offset": start,
                        "end_offset": end,
                        "text": fragment_text,
                    }
                )
                content_parts.append(fragment_text)
            selected_units.append(
                {
                    "unit_id": unit_id,
                    "fragments": fragments,
                }
            )
        content = "".join(content_parts)
        if DEFAULT_TOKEN_COUNTER.count_text(content).tokens <= token_budget:
            best = {
                "schema_version": "articlegraph-retrieval-control.v2",
                "case_id": case.case_id,
                "selected_units": selected_units,
            }
            low = radius + 1
        else:
            high = radius - 1
    return best


def locating_spans(
    text: str,
    queries: Sequence[str],
) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    folded = text.casefold()
    for query in queries:
        start = text.find(query)
        if start < 0:
            start = folded.find(query.casefold())
        if start >= 0:
            spans.append((start, start + len(query)))
    if not spans and text:
        spans.append((0, 1))
    return merge_spans(spans)


def expanded_spans(
    spans: Sequence[tuple[int, int]],
    radius: int,
    text_length: int,
) -> tuple[tuple[int, int], ...]:
    return merge_spans(
        (
            max(0, start - radius),
            min(text_length, end + radius),
        )
        for start, end in spans
    )


def merge_spans(
    spans: Iterable[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    ordered = sorted(spans)
    if not ordered:
        return ()
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def strategy_input_tokens(
    case: LongDocumentCase,
    unit_ids: Sequence[str],
) -> int:
    """Historical helper retained for report compatibility tests."""

    by_id = {unit.unit_id: unit for unit in case.build.unitization.units}
    envelope = {
        "schema_version": "articlegraph-retrieval-control.v1",
        "case_id": case.case_id,
        "selected_units": [
            {
                "unit_id": unit_id,
                "text": by_id[unit_id].exact_text,
            }
            for unit_id in unit_ids
            if unit_id in by_id
        ],
    }
    return DEFAULT_TOKEN_COUNTER.count_json(envelope).tokens


def recall(
    targets: Mapping[str, tuple[str, ...]],
    selected: Sequence[str],
) -> tuple[float, float]:
    selected_ids = frozenset(selected)
    hits = sum(bool(selected_ids.intersection(unit_ids)) for unit_ids in targets.values())
    total = len(targets)
    value = hits / total if total else 1.0
    return value, 1.0 - value

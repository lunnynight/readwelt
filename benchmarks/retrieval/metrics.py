"""Pure retrieval metrics with explicit, deterministic definitions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


def evaluate_ranking(
    ranked_ids: Sequence[str],
    qrels: Mapping[str, int],
    *,
    k: int,
) -> CaseMetrics:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant = {anchor_id for anchor_id, grade in qrels.items() if grade > 0}
    if not relevant:
        raise ValueError("qrels must contain at least one relevant anchor")
    top_k = tuple(ranked_ids[:k])
    recalled = len(relevant.intersection(top_k)) / len(relevant)
    first_relevant_rank = next(
        (rank for rank, anchor_id in enumerate(ranked_ids, 1) if anchor_id in relevant),
        None,
    )
    reciprocal_rank = 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank
    actual_gains = [qrels.get(anchor_id, 0) for anchor_id in top_k]
    ideal_gains = sorted(qrels.values(), reverse=True)[:k]
    ideal_dcg = _dcg(ideal_gains)
    ndcg = 0.0 if ideal_dcg == 0.0 else _dcg(actual_gains) / ideal_dcg
    return CaseMetrics(recalled, reciprocal_rank, ndcg)


def percentile(values: Sequence[float], percentile_value: float) -> float:
    """Return a linearly interpolated percentile, matching common latency reports."""

    if not values:
        raise ValueError("cannot calculate percentile of an empty sequence")
    if not 0.0 <= percentile_value <= 100.0:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _dcg(grades: Sequence[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))

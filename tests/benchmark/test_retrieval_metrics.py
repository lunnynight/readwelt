from __future__ import annotations

import math

import pytest

from benchmarks.retrieval.metrics import evaluate_ranking, percentile


def test_metrics_use_binary_relevance_for_recall_and_mrr_but_graded_ndcg() -> None:
    qrels = {"best": 3, "useful": 1, "noise": 0, "other": 0}
    metrics = evaluate_ranking(("noise", "useful", "best", "other"), qrels, k=3)

    ideal = 7 / math.log2(2) + 1 / math.log2(3)
    actual = 1 / math.log2(3) + 7 / math.log2(4)
    assert metrics.recall_at_k == 1.0
    assert metrics.reciprocal_rank == 0.5
    assert metrics.ndcg_at_k == pytest.approx(actual / ideal)


def test_metrics_respect_cutoff_and_missing_relevant_results() -> None:
    metrics = evaluate_ranking(("noise-a", "noise-b", "relevant"), {"relevant": 2}, k=2)

    assert metrics.recall_at_k == 0.0
    assert metrics.reciprocal_rank == pytest.approx(1 / 3)
    assert metrics.ndcg_at_k == 0.0


def test_percentile_uses_linear_interpolation() -> None:
    values = (1.0, 2.0, 3.0, 4.0)

    assert percentile(values, 50) == 2.5
    assert percentile(values, 95) == pytest.approx(3.85)


@pytest.mark.parametrize("k", [0, -1])
def test_metrics_reject_non_positive_cutoff(k: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        evaluate_ranking(("relevant",), {"relevant": 1}, k=k)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.retrieval.backends import CurrentBM25Backend
from benchmarks.retrieval.contracts import load_dataset, validate_ranking
from benchmarks.retrieval.run import run_benchmark

_DATASET = Path(__file__).parents[2] / "benchmarks" / "retrieval" / "zh_seed_v1.json"


def test_seed_dataset_is_explicitly_synthetic_and_covers_required_categories() -> None:
    dataset = load_dataset(_DATASET)

    assert dataset.corpus_kind == "synthetic_seed"
    assert {case.category for case in dataset.cases} == {
        "exact_term",
        "length_normalization",
        "negative_distractor",
        "number",
        "paraphrase",
        "section_title",
    }
    assert all(any(anchor.relevance > 0 for anchor in case.anchors) for case in dataset.cases)


def test_ranking_contract_requires_every_candidate_exactly_once() -> None:
    case = load_dataset(_DATASET).cases[0]

    with pytest.raises(ValueError, match="complete corpus"):
        validate_ranking(case, ((case.anchors[0].anchor_id, 1.0),))
    duplicate = tuple((case.anchors[0].anchor_id, 1.0) for _ in case.anchors)
    with pytest.raises(ValueError, match="duplicate"):
        validate_ranking(case, duplicate)


def test_current_bm25_benchmark_has_stable_machine_readable_shape() -> None:
    result = run_benchmark(
        CurrentBM25Backend(),
        _DATASET,
        k=3,
        warmup=0,
        repetitions=1,
    )

    assert result["schema_version"] == "1"
    assert result["dataset"]["corpus_kind"] == "synthetic_seed"
    assert result["backend"] == "current-bm25"
    assert set(result["aggregate"]) == {
        "metrics",
        "latency_ms",
        "throughput_queries_per_second",
    }
    assert list(result["by_category"]) == sorted(result["by_category"])
    assert len(result["cases"]) == result["dataset"]["case_count"]
    json.dumps(result, ensure_ascii=False, sort_keys=True)

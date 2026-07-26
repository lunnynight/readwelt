"""Run the deterministic Chinese retrieval seed benchmark."""

from __future__ import annotations

import argparse
import importlib
import json
import time
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from benchmarks.retrieval.backends import (
    BM25LBackend,
    BM25PlusBackend,
    CurrentBM25Backend,
    NativeBM25Backend,
)
from benchmarks.retrieval.contracts import (
    RetrievalBackend,
    load_dataset,
    validate_ranking,
)
from benchmarks.retrieval.metrics import CaseMetrics, evaluate_ranking, percentile

_DEFAULT_DATASET = Path(__file__).with_name("zh_seed_v1.json")


def run_benchmark(
    backend: RetrievalBackend,
    dataset_path: Path = _DEFAULT_DATASET,
    *,
    k: int = 3,
    warmup: int = 2,
    repetitions: int = 20,
) -> dict[str, Any]:
    if warmup < 0 or repetitions <= 0:
        raise ValueError("warmup must be non-negative and repetitions must be positive")
    dataset = load_dataset(dataset_path)
    case_rows: list[dict[str, Any]] = []
    category_metrics: dict[str, list[CaseMetrics]] = defaultdict(list)
    latencies_ms: list[float] = []

    for case in dataset.cases:
        for _ in range(warmup):
            validate_ranking(case, backend.rank(case))
        first_ranking: tuple[tuple[str, float], ...] | None = None
        case_latencies: list[float] = []
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            ranking = validate_ranking(case, backend.rank(case))
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            case_latencies.append(elapsed_ms)
            if first_ranking is None:
                first_ranking = ranking
            elif tuple(item[0] for item in ranking) != tuple(item[0] for item in first_ranking):
                raise ValueError(f"{case.case_id}: backend ranking is not deterministic")
        assert first_ranking is not None
        metrics = evaluate_ranking(
            [anchor_id for anchor_id, _ in first_ranking],
            case.qrels,
            k=k,
        )
        category_metrics[case.category].append(metrics)
        latencies_ms.extend(case_latencies)
        case_rows.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "metrics": _metrics_mapping(metrics),
                "top_k": [
                    {"anchor_id": anchor_id, "score": round(score, 8)}
                    for anchor_id, score in first_ranking[:k]
                ],
                "latency_ms": {
                    "p50": round(percentile(case_latencies, 50), 6),
                    "p95": round(percentile(case_latencies, 95), 6),
                },
            }
        )

    all_metrics = [
        metric
        for metrics_for_category in category_metrics.values()
        for metric in metrics_for_category
    ]
    total_seconds = sum(latencies_ms) / 1_000
    return {
        "schema_version": "1",
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "corpus_kind": dataset.corpus_kind,
            "case_count": len(dataset.cases),
            "description": dataset.description,
        },
        "backend": backend.name,
        "parameters": {"k": k, "warmup": warmup, "repetitions": repetitions},
        "aggregate": {
            "metrics": _mean_metrics(all_metrics),
            "latency_ms": {
                "p50": round(percentile(latencies_ms, 50), 6),
                "p95": round(percentile(latencies_ms, 95), 6),
            },
            "throughput_queries_per_second": (
                0.0 if total_seconds == 0.0 else round(len(latencies_ms) / total_seconds, 3)
            ),
        },
        "by_category": {
            category: _mean_metrics(category_metrics[category])
            for category in sorted(category_metrics)
        },
        "cases": case_rows,
    }


def _metrics_mapping(metrics: CaseMetrics) -> dict[str, float]:
    return {
        "recall_at_k": round(metrics.recall_at_k, 8),
        "mrr": round(metrics.reciprocal_rank, 8),
        "ndcg_at_k": round(metrics.ndcg_at_k, 8),
    }


def _mean_metrics(metrics: Sequence[CaseMetrics]) -> dict[str, float]:
    if not metrics:
        raise ValueError("cannot aggregate empty metrics")
    count = len(metrics)
    return {
        "recall_at_k": round(sum(item.recall_at_k for item in metrics) / count, 8),
        "mrr": round(sum(item.reciprocal_rank for item in metrics) / count, 8),
        "ndcg_at_k": round(sum(item.ndcg_at_k for item in metrics) / count, 8),
    }


def _load_backend(spec: str) -> RetrievalBackend:
    builtins: dict[str, type[RetrievalBackend]] = {
        "current-bm25": CurrentBM25Backend,
        "native-bm25": NativeBM25Backend,
        "bm25-plus": BM25PlusBackend,
        "bm25-l": BM25LBackend,
    }
    if spec in builtins:
        return builtins[spec]()
    if ":" not in spec:
        raise ValueError("custom backend must use module:attribute syntax")
    module_name, attribute_name = spec.split(":", 1)
    candidate = getattr(importlib.import_module(module_name), attribute_name)
    backend = candidate() if callable(candidate) else candidate
    if not isinstance(getattr(backend, "name", None), str) or not callable(
        getattr(backend, "rank", None)
    ):
        raise TypeError("custom backend must expose string name and rank(case)")
    return cast(RetrievalBackend, backend)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", action="append", default=None)
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    backend_specs = args.backend or ["current-bm25"]
    results = [
        run_benchmark(
            _load_backend(spec),
            args.dataset,
            k=args.k,
            warmup=args.warmup,
            repetitions=args.repetitions,
        )
        for spec in backend_specs
    ]
    payload = {
        "schema_version": "1",
        "benchmark": "readwelt-retrieval",
        "results": results,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()

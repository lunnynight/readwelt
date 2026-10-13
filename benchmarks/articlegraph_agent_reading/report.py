"""Separate product-quality, runtime, token, failure, and infrastructure reporting."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .validity import validate_pair


def build_report(
    pairs: list[dict[str, dict[str, Any]]], *, artifact_root: Path
) -> dict[str, Any]:
    valid_pairs: list[dict[str, dict[str, Any]]] = []
    invalid_reasons: Counter[str] = Counter()
    for pair in pairs:
        failures = validate_pair(
            pair["baseline"], pair["treatment"], artifact_root=artifact_root
        )
        if failures["baseline"] or failures["treatment"]:
            invalid_reasons.update(failures["baseline"] + failures["treatment"])
            continue
        valid_pairs.append(pair)

    return {
        "pair_validity": {
            "total": len(pairs),
            "valid": len(valid_pairs),
            "rate": len(valid_pairs) / len(pairs) if pairs else 0.0,
            "failure_reasons": dict(sorted(invalid_reasons.items())),
        },
        "quality": _quality(valid_pairs),
        "latency_ms": _condition_metric(valid_pairs, "wall_ms"),
        "tokens": _tokens(valid_pairs),
        "failures": _reported_failures(pairs),
        "infrastructure": _infrastructure(valid_pairs),
    }


def _quality(pairs: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in ("location", "citation", "comprehension"):
        by_condition = {
            condition: [float(pair[condition]["scores"][metric]) for pair in pairs]
            for condition in ("baseline", "treatment")
        }
        result[metric] = {
            **{key: _mean(values) for key, values in by_condition.items()},
            "absolute_gain": _mean(by_condition["treatment"])
            - _mean(by_condition["baseline"]),
        }
    return result


def _condition_metric(
    pairs: list[dict[str, dict[str, Any]]], key: str
) -> dict[str, float]:
    return {
        condition: _mean([float(pair[condition][key]) for pair in pairs])
        for condition in ("baseline", "treatment")
    }


def _tokens(pairs: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for condition in ("baseline", "treatment"):
        by_key: defaultdict[str, list[float]] = defaultdict(list)
        for pair in pairs:
            for key, value in pair[condition]["usage"].items():
                by_key[key].append(float(value))
        result[condition] = {key: _mean(values) for key, values in by_key.items()}
    return result


def _reported_failures(pairs: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    return {
        condition: dict(
            Counter(
                failure
                for pair in pairs
                for failure in pair[condition].get("reported_failures", [])
            )
        )
        for condition in ("baseline", "treatment")
    }


def _infrastructure(pairs: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    treatment = [pair["treatment"].get("infrastructure_costs", {}) for pair in pairs]
    keys = ("cold_build_ms", "warm_query_ms", "amortized_ms")
    return {key: _mean([float(item[key]) for item in treatment if key in item]) for key in keys}


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


__all__ = ["build_report"]

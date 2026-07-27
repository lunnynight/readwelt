"""Deterministic confidence aggregation with candidate-level lineage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import ConfidenceSource


def confidence_lineage(
    candidates: Sequence[Mapping[str, Any]],
    mention_ids: Mapping[str, str] | None = None,
) -> tuple[float | None, str, tuple[ConfidenceSource, ...]]:
    if any(
        item["confidence"] is None or item["confidence_method"] == "unresolved"
        for item in candidates
    ):
        return None, "unresolved", ()
    sources = tuple(
        ConfidenceSource(
            candidate_id=item["candidate_id"],
            score=item["confidence"],
            method=item["confidence_method"],
            mention_id=(mention_ids.get(item["candidate_id"]) if mention_ids is not None else None),
        )
        for item in sorted(candidates, key=lambda value: value["candidate_id"])
    )
    method = "single_candidate.v1" if len(sources) == 1 else "minimum_candidate_score.v1"
    return min(item.score for item in sources), method, sources


def decision_confidence(candidates: Sequence[Mapping[str, Any]]) -> float:
    scores = tuple(item["confidence"] for item in candidates if item["confidence"] is not None)
    return min(scores) if len(scores) == len(candidates) else 0.0

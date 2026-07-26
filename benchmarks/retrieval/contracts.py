"""Strict fixture and backend contracts for retrieval benchmarks."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class CorpusAnchor:
    anchor_id: str
    section_id: str
    section_title: str
    text: str
    relevance: int


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    category: str
    query: str
    anchors: tuple[CorpusAnchor, ...]

    @property
    def qrels(self) -> dict[str, int]:
        return {anchor.anchor_id: anchor.relevance for anchor in self.anchors}


@dataclass(frozen=True, slots=True)
class RetrievalDataset:
    schema_version: str
    dataset_id: str
    corpus_kind: str
    description: str
    cases: tuple[BenchmarkCase, ...]


class RetrievalBackend(Protocol):
    """The only surface a lexical implementation must expose to the harness."""

    name: str

    def rank(self, case: BenchmarkCase) -> Sequence[tuple[str, float]]:
        """Return every candidate once, ordered best-first with a numeric score."""


def load_dataset(path: Path) -> RetrievalDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("dataset root must be an object")
    schema_version = _required_string(raw, "schema_version")
    if schema_version != "1":
        raise ValueError(f"unsupported dataset schema: {schema_version}")
    corpus_kind = _required_string(raw, "corpus_kind")
    if corpus_kind not in {"synthetic_seed", "real_corpus"}:
        raise ValueError("corpus_kind must be synthetic_seed or real_corpus")
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("cases must be a non-empty array")
    cases = tuple(_parse_case(item) for item in raw_cases)
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case ids must be unique")
    return RetrievalDataset(
        schema_version=schema_version,
        dataset_id=_required_string(raw, "dataset_id"),
        corpus_kind=corpus_kind,
        description=_required_string(raw, "description"),
        cases=cases,
    )


def validate_ranking(
    case: BenchmarkCase,
    ranking: Sequence[tuple[str, float]],
) -> tuple[tuple[str, float], ...]:
    materialized = tuple(ranking)
    expected = {anchor.anchor_id for anchor in case.anchors}
    returned = [anchor_id for anchor_id, _ in materialized]
    if len(returned) != len(set(returned)):
        raise ValueError(f"{case.case_id}: backend returned duplicate anchor ids")
    unknown = set(returned) - expected
    missing = expected - set(returned)
    if unknown or missing:
        raise ValueError(
            f"{case.case_id}: ranking must contain the complete corpus; "
            f"unknown={sorted(unknown)}, missing={sorted(missing)}"
        )
    return materialized


def _parse_case(raw: Any) -> BenchmarkCase:
    if not isinstance(raw, dict):
        raise ValueError("each case must be an object")
    raw_anchors = raw.get("anchors")
    if not isinstance(raw_anchors, list) or len(raw_anchors) < 2:
        raise ValueError("each case must have at least two anchors")
    anchors = tuple(_parse_anchor(item) for item in raw_anchors)
    anchor_ids = [anchor.anchor_id for anchor in anchors]
    if len(anchor_ids) != len(set(anchor_ids)):
        raise ValueError("anchor ids must be unique within a case")
    if not any(anchor.relevance > 0 for anchor in anchors):
        raise ValueError("each case must have at least one relevant anchor")
    return BenchmarkCase(
        case_id=_required_string(raw, "case_id"),
        category=_required_string(raw, "category"),
        query=_required_string(raw, "query"),
        anchors=anchors,
    )


def _parse_anchor(raw: Any) -> CorpusAnchor:
    if not isinstance(raw, dict):
        raise ValueError("each anchor must be an object")
    relevance = raw.get("relevance")
    if not isinstance(relevance, int) or isinstance(relevance, bool) or not 0 <= relevance <= 3:
        raise ValueError("anchor relevance must be an integer from 0 to 3")
    return CorpusAnchor(
        anchor_id=_required_string(raw, "anchor_id"),
        section_id=_required_string(raw, "section_id"),
        section_title=_required_string(raw, "section_title"),
        text=_required_string(raw, "text"),
        relevance=relevance,
    )


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value

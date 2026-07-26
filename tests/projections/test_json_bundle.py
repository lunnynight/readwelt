from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pytest

from readwelt.projections import (
    BUNDLE_SCHEMA,
    canonical_bundle_bytes,
    canonical_bundle_document,
    canonical_bundle_json,
)


class State(StrEnum):
    COMPLETE = "complete"


@dataclass(frozen=True)
class DuckBundle:
    run_id: str
    tags: frozenset[str]
    state: State
    title: str


def test_canonical_bundle_is_utf8_stable_and_chinese_friendly() -> None:
    first = DuckBundle(
        run_id="run-1",
        tags=frozenset({"结构", "主线"}),
        state=State.COMPLETE,
        title="实践论",
    )
    second = DuckBundle(
        run_id="run-1",
        tags=frozenset({"主线", "结构"}),
        state=State.COMPLETE,
        title="实践论",
    )

    assert canonical_bundle_bytes(first) == canonical_bundle_bytes(second)
    assert canonical_bundle_json(first) == canonical_bundle_json(second)
    assert "实践论" in canonical_bundle_json(first)
    assert "\\u5b9e" not in canonical_bundle_json(first)
    assert canonical_bundle_document(first)["schema_version"] == BUNDLE_SCHEMA


def test_existing_schema_version_is_not_rewritten() -> None:
    document = canonical_bundle_document({"schema_version": "custom.v2", "run_id": "r"})
    assert document["schema_version"] == "custom.v2"


def test_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_bundle_bytes({"score": float("nan")})

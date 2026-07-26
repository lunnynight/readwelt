"""Canonical JSON projection for ReadingBundle-like values."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from ._normalize import normalize

BUNDLE_SCHEMA = "readwelt.reading-bundle.v1"


class BundleLike(Protocol):
    """Structural marker; concrete bundle contracts remain owned by the domain."""

    run_id: str


def canonical_bundle_document(bundle: BundleLike | Mapping[str, Any] | Any) -> dict[str, Any]:
    projected = normalize(bundle)
    if not isinstance(projected, dict):
        raise TypeError("ReadingBundle projection must be a JSON object")
    document = dict(projected)
    document.setdefault("schema_version", BUNDLE_SCHEMA)
    return document


def canonical_bundle_bytes(bundle: BundleLike | Mapping[str, Any] | Any) -> bytes:
    return json.dumps(
        canonical_bundle_document(bundle),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_bundle_json(bundle: BundleLike | Mapping[str, Any] | Any) -> str:
    return canonical_bundle_bytes(bundle).decode("utf-8")

"""Deterministic identifiers for immutable domain values."""

from __future__ import annotations

import hashlib


def stable_id(prefix: str, *parts: str) -> str:
    """Build a compact, deterministic id from already-canonical string parts."""
    if not prefix or not prefix.replace("_", "").isalnum():
        raise ValueError("prefix must contain only letters, numbers, and underscores")
    payload = "\0".join(parts).encode()
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"

"""Deterministic, dependency-free normalization for public projections."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

_MISSING = object()


def read_field(value: Any, name: str, default: Any = None) -> Any:
    """Read a field from mappings, dataclasses, or Pydantic-like objects."""

    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def first_field(value: Any, names: Sequence[str], default: Any = None) -> Any:
    for name in names:
        found = read_field(value, name, _MISSING)
        if found is not _MISSING and found is not None:
            return found
    return default


def as_items(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return tuple(value.values())
    if isinstance(value, (str, bytes, bytearray)):
        return (value,)
    if isinstance(value, (Sequence, set, frozenset)):
        return tuple(value)
    return (value,)


def _sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("canonical JSON cannot contain non-finite floats")
        return value
    if isinstance(value, Enum):
        return normalize(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    return _MISSING


def _normalize_object(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return normalize(dataclasses.asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return normalize(model_dump(mode="json"))
        except TypeError:
            return normalize(model_dump())
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return normalize(to_dict())
    slots = getattr(type(value), "__slots__", ())
    if slots:
        return normalize(
            {
                name: getattr(value, name)
                for name in slots
                if isinstance(name, str) and hasattr(value, name)
            }
        )
    if hasattr(value, "__dict__"):
        return normalize(vars(value))
    raise TypeError(f"unsupported projection value: {type(value).__name__}")


def normalize(value: Any) -> Any:
    """Convert a bundle to stable JSON primitives without importing domain types."""

    scalar = _normalize_scalar(value)
    if scalar is not _MISSING:
        return scalar
    if isinstance(value, Mapping):
        return {
            str(key): normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        normalized = [normalize(item) for item in value]
        return sorted(normalized, key=_sort_key)
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return _normalize_object(value)


def stable_identifier(value: Any, *names: str) -> str:
    identifier = first_field(value, names)
    return "" if identifier is None else str(identifier)

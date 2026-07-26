"""Small JSON and resource projections for public adapters."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any, cast

MAX_INLINE_BYTES = 64 * 1024


class ProjectRootViolation(ValueError):
    code = "project_root_violation"


def resolve_project_root(value: str | Path | None) -> Path:
    root = Path(value or ".readwelt")
    if root.is_absolute():
        return root.resolve()
    return (Path.cwd() / root).resolve()


def ensure_within_project(project_root: Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ProjectRootViolation(
            f"path is outside the Readwelt project root: {candidate}"
        ) from exc
    return resolved


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if dataclasses.is_dataclass(value):
        return to_jsonable(dataclasses.asdict(cast(Any, value)))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return to_jsonable(dump(mode="json"))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_jsonable(to_dict())
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return str(value)


def compact_result(value: Any, *, resource_uri: str | None = None) -> Any:
    projected = to_jsonable(value)
    encoded = json.dumps(projected, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) <= MAX_INLINE_BYTES:
        return projected
    if not resource_uri:
        raise ValueError("large result requires a resource URI")
    return {
        "resource_uri": resource_uri,
        "size_bytes": len(encoded),
        "inline": False,
    }

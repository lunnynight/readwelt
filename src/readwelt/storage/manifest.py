"""Atomic JSON manifests and append-only JSONL events."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from readwelt.storage.serialization import canonical_json_bytes, to_primitive


class ManifestStore:
    def write(self, path: Path, value: Any) -> None:
        content = canonical_json_bytes(value) + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".manifest-")
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"manifest must contain an object: {path}")
        return value


class EventLog:
    def append(self, path: Path, event: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            to_primitive(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def read(self, path: Path) -> tuple[dict[str, Any], ...]:
        if not path.exists():
            return ()
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"event must contain an object: {path}")
            events.append(value)
        return tuple(events)

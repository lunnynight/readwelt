"""Portable project-directory layout."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectLayout:
    root: Path

    @classmethod
    def resolve(
        cls,
        project: str | Path = ".readwelt",
        *,
        base_directory: Path | None = None,
    ) -> ProjectLayout:
        candidate = Path(project)
        base = Path.cwd() if base_directory is None else base_directory
        root = candidate if candidate.is_absolute() else base / candidate
        return cls(root=root.resolve())

    def initialize(self) -> None:
        for name in ("objects", "documents", "runs", "batches", "indexes", "reports"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        project_file = self.root / "project.json"
        if not project_file.exists():
            payload = {
                "schema_version": "1",
                "created_at": datetime.now(UTC).isoformat(),
                "storage": "local",
            }
            project_file.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def document_manifest(self, document_id: str) -> Path:
        return self.root / "documents" / document_id / "manifest.json"

    def run_manifest(self, run_id: str) -> Path:
        return self.root / "runs" / run_id / "manifest.json"

    def run_events(self, run_id: str) -> Path:
        return self.root / "runs" / run_id / "events.jsonl"

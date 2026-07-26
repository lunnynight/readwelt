"""Deterministic TXT ingestion used until the Xberg adapter lands."""

from __future__ import annotations

from pathlib import Path

from readwelt.domain import SourceDocumentSnapshot
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.storage import ArtifactStore


class PlainTextAdapter:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts

    async def ingest(self, source: Path) -> SourceDocumentSnapshot:
        if source.suffix.lower() != ".txt":
            raise ValueError("PlainTextAdapter accepts only .txt files")
        raw = source.read_text(encoding="utf-8-sig")
        text = raw.replace("\r\n", "\n").replace("\r", "\n")
        return snapshot_from_text(
            source=source,
            text=text,
            source_kind="text/plain",
            artifacts=self._artifacts,
            adapter_finding="ingested_by_plain_text_fallback",
        )

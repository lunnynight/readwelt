"""Narrow ingestion seam implemented by Xberg and deterministic test adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from readwelt.domain import SourceDocumentSnapshot


class DocumentAdapter(Protocol):
    async def ingest(self, source: Path) -> SourceDocumentSnapshot: ...

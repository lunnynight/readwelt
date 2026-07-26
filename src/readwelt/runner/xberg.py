"""Xberg rc38 adapter with an explicit, narrow projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from readwelt.domain import SourceDocumentSnapshot
from readwelt.runner.epub_outline import load_epub_outline
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.storage import ArtifactStore


class XbergUnavailableError(RuntimeError):
    """Raised when the precisely pinned Xberg runtime cannot be loaded."""


class XbergDocumentAdapter:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts

    async def ingest(self, source: Path) -> SourceDocumentSnapshot:
        try:
            from xberg import ExtractInput, extract
        except ImportError as error:
            raise XbergUnavailableError(
                "Xberg ingestion requires the pinned dependency xberg==1.0.0rc38"
            ) from error

        output = await extract(ExtractInput(kind="uri", uri=str(source.resolve())))
        if not output.results:
            raise ValueError(f"Xberg returned no document for {source}")
        document = output.results[0]
        content = getattr(document, "content", None)
        if not isinstance(content, str):
            raise ValueError("Xberg document content is missing or not text")
        mime_type_value = getattr(document, "mime_type", None)
        mime_type = (
            mime_type_value if isinstance(mime_type_value, str) else "application/octet-stream"
        )
        metadata = getattr(document, "metadata", None)
        outline = load_epub_outline(source) if source.suffix.casefold() == ".epub" else ()
        return snapshot_from_text(
            source=source,
            text=content,
            source_kind=mime_type,
            artifacts=self._artifacts,
            adapter_finding="ingested_by_xberg_1.0.0rc38",
            title=self._metadata_text(metadata, "title"),
            author=self._metadata_text(metadata, "author"),
            language=self._metadata_text(metadata, "language") or "und",
            outline=outline,
            snapshot_policy_version=("xberg-epub-ncx-v4" if outline else "1"),
        )

    @staticmethod
    def _metadata_text(metadata: Any, field: str) -> str | None:
        if metadata is None:
            return None
        value = getattr(metadata, field, None)
        if value is None and isinstance(metadata, dict):
            value = metadata.get(field)
        return value if isinstance(value, str) and value else None

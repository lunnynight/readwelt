"""Xberg rc38 adapter with an explicit, narrow projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from readwelt.domain import SourceDocumentSnapshot
from readwelt.runner.epub_outline import load_epub_outline
from readwelt.runner.snapshot import SectionStructure, snapshot_from_text
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
        structure, structure_findings = self._available_structure(document)
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
            structure=structure,
            structure_findings=structure_findings,
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

    @classmethod
    def _available_structure(
        cls, document: Any
    ) -> tuple[tuple[SectionStructure, ...], tuple[str, ...]]:
        """Read rc38 structure fields without synthesizing absent layout."""

        nodes = getattr(getattr(document, "document", None), "nodes", None)
        if isinstance(nodes, list) and nodes:
            records = tuple(
                record for node in nodes if (record := cls._node_structure(node)) is not None
            )
            return records, (
                f"xberg_document_nodes_available:{len(nodes)}",
                *(
                    (f"xberg_document_nodes_unsupported:{len(nodes) - len(records)}",)
                    if len(records) != len(nodes)
                    else ()
                ),
            )
        elements = getattr(document, "elements", None)
        if isinstance(elements, list) and elements:
            records = tuple(
                record
                for element in elements
                if (record := cls._element_structure(element)) is not None
            )
            return records, (
                f"xberg_elements_available:{len(elements)}",
                *(
                    (f"xberg_elements_unsupported:{len(elements) - len(records)}",)
                    if len(records) != len(elements)
                    else ()
                ),
            )
        return (), ("xberg_structure_unsupported:not_exposed_for_document",)

    @staticmethod
    def _node_structure(node: Any) -> SectionStructure | None:
        content = getattr(node, "content", None)
        try:
            payload = json.loads(str(content))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        text = payload.get("text")
        if not isinstance(text, str) or not text:
            return None
        page = getattr(node, "page", None)
        valid_page = page if isinstance(page, int) and page >= 1 else None
        return SectionStructure(
            exact_text=text,
            kind=str(payload.get("node_type")) if payload.get("node_type") is not None else None,
            parent_element_id=_optional_text(getattr(node, "parent", None)),
            element_id=_optional_text(getattr(node, "id", None)),
            page=valid_page,
            bounding_box=(
                _bbox(getattr(node, "bbox", None)) if valid_page is not None else None
            ),
        )

    @staticmethod
    def _element_structure(element: Any) -> SectionStructure | None:
        text = getattr(element, "text", None)
        if not isinstance(text, str) or not text:
            return None
        metadata = getattr(element, "metadata", None)
        page = getattr(metadata, "page_number", None)
        element_index = getattr(metadata, "element_index", None)
        valid_page = page if isinstance(page, int) and page >= 1 else None
        return SectionStructure(
            exact_text=text,
            kind=_optional_text(getattr(element, "element_type", None)),
            element_id=str(element_index) if isinstance(element_index, int) else None,
            page=valid_page,
            bounding_box=(
                _bbox(getattr(metadata, "coordinates", None))
                if valid_page is not None
                else None
            ),
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _bbox(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    coordinates: list[float] = []
    for names in (("x0", "y0", "x1", "y1"), ("x1", "y1", "x2", "y2")):
        raw = [getattr(value, name, None) for name in names]
        first, second, third, fourth = raw
        if (
            isinstance(first, (int, float))
            and isinstance(second, (int, float))
            and isinstance(third, (int, float))
            and isinstance(fourth, (int, float))
        ):
            coordinates = [
                float(first),
                float(second),
                float(third),
                float(fourth),
            ]
            break
    if len(coordinates) != 4:
        return None
    return coordinates[0], coordinates[1], coordinates[2], coordinates[3]

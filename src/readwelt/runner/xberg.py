"""Xberg rc38 adapter with an explicit, narrow projection."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from readwelt.domain import SourceDocumentSnapshot
from readwelt.runner.docling import DoclingStructuralFallback, StructuralFallback
from readwelt.runner.epub_outline import load_epub_outline
from readwelt.runner.snapshot import SectionStructure, snapshot_from_text
from readwelt.storage import ArtifactStore


class XbergUnavailableError(RuntimeError):
    """Raised when the precisely pinned Xberg runtime cannot be loaded."""


class XbergDocumentAdapter:
    def __init__(
        self,
        artifacts: ArtifactStore,
        *,
        structural_fallback: StructuralFallback | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._structural_fallback = structural_fallback or DoclingStructuralFallback()

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
        fallback_invoked = False
        if source.suffix.casefold() == ".pdf" and (not structure or not content):
            fallback_invoked = True
            trigger = (
                "empty_pdf_text_and_structure_unavailable"
                if not content and not structure
                else "empty_pdf_text"
                if not content
                else "xberg_structure_unavailable"
            )
            fallback = self._structural_fallback.project(source, trigger=trigger)
            structure_findings = (*structure_findings, *fallback.findings)
            if fallback.structure:
                structure, conflicts = _merge_structure_records([*structure, *fallback.structure])
                structure_findings = (
                    *structure_findings,
                    f"docling_fallback_structure_adopted:{len(fallback.structure)}",
                    *((f"docling_fallback_identity_conflicts:{conflicts}",) if conflicts else ()),
                )
            if not content and fallback.text:
                content = fallback.text
                structure_findings = (
                    *structure_findings,
                    "docling_fallback_text_adopted:xberg_text_empty",
                )
        if not content:
            structure_findings = (
                *structure_findings,
                "xberg_text_unsupported:empty_extraction",
            )
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
            snapshot_policy_version=(
                "xberg-epub-ncx-v4"
                if outline
                else "xberg-rc38+docling-2.114.0-v1"
                if fallback_invoked
                else "1"
            ),
            raw_source_content=source.read_bytes(),
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

        records: list[SectionStructure] = []
        findings: list[str] = []
        nodes = getattr(getattr(document, "document", None), "nodes", None)
        if isinstance(nodes, list) and nodes:
            node_records = tuple(
                record for node in nodes if (record := cls._node_structure(node)) is not None
            )
            records.extend(node_records)
            findings.append(f"xberg_document_nodes_available:{len(nodes)}")
            if len(node_records) != len(nodes):
                findings.append(
                    f"xberg_document_nodes_unsupported:{len(nodes) - len(node_records)}"
                )
        elements = getattr(document, "elements", None)
        if isinstance(elements, list) and elements:
            element_records = tuple(
                record
                for element in elements
                if (record := cls._element_structure(element)) is not None
            )
            records.extend(element_records)
            findings.append(f"xberg_elements_available:{len(elements)}")
            if len(element_records) != len(elements):
                findings.append(
                    f"xberg_elements_unsupported:{len(elements) - len(element_records)}"
                )
        if records:
            deduplicated, identity_conflicts = _merge_structure_records(records)
            if len(deduplicated) != len(records):
                findings.append(
                    f"xberg_structure_duplicates_collapsed:{len(records) - len(deduplicated)}"
                )
            if identity_conflicts:
                findings.append(f"xberg_structure_identity_conflicts:{identity_conflicts}")
            return deduplicated, tuple(findings)
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
        valid_text = text if isinstance(text, str) and text else None
        kind = str(payload.get("node_type")) if payload.get("node_type") is not None else None
        if valid_text is None and kind is None:
            return None
        page = getattr(node, "page", None)
        valid_page = page if isinstance(page, int) and page >= 1 else None
        return SectionStructure(
            exact_text=valid_text,
            kind=_normalized_kind(kind),
            parent_element_id=_reference_id(payload.get("parent") or getattr(node, "parent", None)),
            child_element_ids=_reference_ids(
                payload.get("children") or getattr(node, "children", None)
            ),
            structural_relations=_structural_relations(
                payload.get("relationships") or getattr(node, "relationships", None),
                payload,
            ),
            heading_trail=_text_tuple(payload.get("heading_trail") or payload.get("headings")),
            element_id=_optional_text(getattr(node, "id", None)),
            reading_order=_first_int(payload, "reading_order", "order", "ordinal"),
            page=valid_page,
            bounding_box=(_bbox(getattr(node, "bbox", None)) if valid_page is not None else None),
            start_offset=_optional_int(payload.get("start_offset")),
            end_offset=_optional_int(payload.get("end_offset")),
            native_reference=_optional_text(getattr(node, "id", None)),
            raw_payload=str(content) if content is not None else None,
        )

    @staticmethod
    def _element_structure(element: Any) -> SectionStructure | None:
        text = getattr(element, "text", None)
        valid_text = text if isinstance(text, str) and text else None
        kind = _optional_text(getattr(element, "element_type", None))
        if valid_text is None and kind is None:
            return None
        metadata = getattr(element, "metadata", None)
        page = getattr(metadata, "page_number", None)
        element_index = getattr(metadata, "element_index", None)
        valid_page = page if isinstance(page, int) and page >= 1 else None
        return SectionStructure(
            exact_text=valid_text,
            kind=_normalized_kind(kind),
            parent_element_id=_reference_id(
                _first_value(
                    metadata,
                    "parent_element_id",
                    "parent_id",
                    "parent",
                )
            ),
            child_element_ids=_reference_ids(
                _first_value(metadata, "child_element_ids", "children")
            ),
            structural_relations=_structural_relations(
                _first_value(metadata, "relationships", "relations"),
                metadata,
            ),
            heading_trail=_text_tuple(_first_value(metadata, "heading_trail", "headings")),
            element_id=str(element_index) if isinstance(element_index, int) else None,
            reading_order=_first_int(
                metadata,
                "reading_order",
                "order",
                "ordinal",
                "element_index",
            ),
            page=valid_page,
            bounding_box=(
                _bbox(getattr(metadata, "coordinates", None)) if valid_page is not None else None
            ),
            start_offset=_first_int(
                metadata,
                "start_offset",
                "start_char",
                "text_start",
            ),
            end_offset=_first_int(
                metadata,
                "end_offset",
                "end_char",
                "text_end",
            ),
            native_reference=(str(element_index) if isinstance(element_index, int) else None),
            raw_payload=_model_payload(element),
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _first_value(value: Any, *names: str) -> Any:
    if value is None:
        return None
    for name in names:
        found = _value(value, name)
        if found is not None:
            return found
    return None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _first_int(value: Any, *names: str) -> int | None:
    if value is None:
        return None
    for name in names:
        found = _optional_int(_value(value, name))
        if found is not None:
            return found
    return None


def _reference_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int)):
        return str(value)
    return _optional_text(_first_value(value, "id", "element_id", "ref", "$ref"))


def _reference_ids(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(reference for item in value if (reference := _reference_id(item)) is not None)
    reference = _reference_id(value)
    return (reference,) if reference is not None else ()


def _structural_relations(
    relationships: Any,
    owner: Any,
) -> tuple[tuple[str, str], ...]:
    relations: list[tuple[str, str]] = []
    if isinstance(relationships, dict):
        for relation, targets in relationships.items():
            relations.extend((str(relation), target_id) for target_id in _reference_ids(targets))
    elif isinstance(relationships, (list, tuple)):
        for item in relationships:
            relation = _optional_text(_first_value(item, "type", "relation", "name"))
            target = _reference_id(_first_value(item, "target", "to", "object"))
            if relation is not None and target is not None:
                relations.append((relation, target))
    for role in ("caption", "table", "figure"):
        relations.extend(
            (role, target_id)
            for target_id in _reference_ids(_first_value(owner, f"{role}_id", f"{role}_ref", role))
        )
    return tuple(dict.fromkeys(relations))


def _text_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _normalized_kind(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "tableitem": "table",
        "table_item": "table",
        "picture": "figure",
        "image": "figure",
        "figureitem": "figure",
        "figure_item": "figure",
        "captionitem": "caption",
        "caption_item": "caption",
        "tablecaption": "caption",
        "figurecaption": "caption",
    }
    return aliases.get(normalized, normalized)


def _model_payload(value: Any) -> str | None:
    for method_name in ("model_dump_json", "json"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                payload = method()
            except (TypeError, ValueError):
                continue
            if isinstance(payload, str):
                return payload
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return None


def _merge_structure_records(
    records: list[SectionStructure],
) -> tuple[tuple[SectionStructure, ...], int]:
    merged: list[SectionStructure] = []
    index_by_identity: dict[str, int] = {}
    conflicts = 0
    for record in records:
        identity = record.element_id or record.native_reference
        if identity is None or identity not in index_by_identity:
            if identity is not None:
                index_by_identity[identity] = len(merged)
            merged.append(record)
            continue
        index = index_by_identity[identity]
        existing = merged[index]
        exact_text, count = _merge_scalar(existing.exact_text, record.exact_text)
        conflicts += count
        kind, count = _merge_scalar(existing.kind, record.kind)
        conflicts += count
        content_layer, count = _merge_scalar(
            existing.content_layer,
            record.content_layer,
        )
        conflicts += count
        parent_element_id, count = _merge_scalar(
            existing.parent_element_id,
            record.parent_element_id,
        )
        conflicts += count
        reading_order, count = _merge_scalar(
            existing.reading_order,
            record.reading_order,
        )
        conflicts += count
        page, count = _merge_scalar(existing.page, record.page)
        conflicts += count
        bounding_box, count = _merge_scalar(
            existing.bounding_box,
            record.bounding_box,
        )
        conflicts += count
        start_offset, count = _merge_scalar(
            existing.start_offset,
            record.start_offset,
        )
        conflicts += count
        end_offset, count = _merge_scalar(existing.end_offset, record.end_offset)
        conflicts += count
        native_reference, count = _merge_scalar(
            existing.native_reference,
            record.native_reference,
        )
        conflicts += count
        payloads = tuple(
            payload for payload in (existing.raw_payload, record.raw_payload) if payload is not None
        )
        merged[index] = replace(
            existing,
            exact_text=exact_text,
            kind=kind,
            content_layer=content_layer,
            parent_element_id=parent_element_id,
            reading_order=reading_order,
            page=page,
            bounding_box=bounding_box,
            start_offset=start_offset,
            end_offset=end_offset,
            native_reference=native_reference,
            child_element_ids=tuple(
                dict.fromkeys((*existing.child_element_ids, *record.child_element_ids))
            ),
            structural_relations=tuple(
                dict.fromkeys((*existing.structural_relations, *record.structural_relations))
            ),
            heading_trail=(
                existing.heading_trail
                if existing.heading_trail == record.heading_trail or not record.heading_trail
                else record.heading_trail
                if not existing.heading_trail
                else ()
            ),
            raw_payload=(
                payloads[0]
                if len(payloads) == 1
                else json.dumps(payloads, ensure_ascii=False)
                if payloads
                else None
            ),
        )
    return tuple(merged), conflicts


def _merge_scalar[T](first: T | None, second: T | None) -> tuple[T | None, int]:
    if first is not None and second is not None and first != second:
        return None, 1
    return (first if first is not None else second), 0


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

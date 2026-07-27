"""Map extracted canonical text into Readwelt's immutable snapshot contract."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from readwelt import _core
from readwelt.domain import (
    DocumentSection,
    SourceDocumentSnapshot,
    SourceElement,
    SpanAnchor,
    stable_id,
)
from readwelt.runner.outline import OutlineItem, align_outline
from readwelt.storage import ArtifactStore


@dataclass(frozen=True, slots=True)
class SectionStructure:
    """Structure explicitly emitted by an extraction adapter."""

    exact_text: str | None
    kind: str | None = None
    content_layer: str | None = None
    parent_element_id: str | None = None
    child_element_ids: tuple[str, ...] = ()
    structural_relations: tuple[tuple[str, str], ...] = ()
    heading_trail: tuple[str, ...] = ()
    element_id: str | None = None
    reading_order: int | None = None
    page: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    native_reference: str | None = None
    raw_payload: str | None = None


def snapshot_from_text(
    *,
    source: Path,
    text: str,
    source_kind: str,
    artifacts: ArtifactStore,
    adapter_finding: str,
    title: str | None = None,
    author: str | None = None,
    language: str = "und",
    outline: Sequence[OutlineItem] = (),
    structure: Sequence[SectionStructure] = (),
    structure_findings: Sequence[str] = (),
    snapshot_policy_version: str = "1",
    raw_source_content: bytes | None = None,
) -> SourceDocumentSnapshot:
    prepared = _core.prepare(text)
    normalized_text = prepared.text
    text_ref = artifacts.put_text(normalized_text, artifact_type="normalized_text")
    digest = prepared.digest
    source_ref = (
        artifacts.put_bytes(
            raw_source_content,
            artifact_type="source_document",
            schema_version="source-document.v1",
        )
        if raw_source_content is not None
        else None
    )
    document_id = stable_id(
        "document",
        source_ref.content_digest if source_ref is not None else digest,
    )
    snapshot_id = stable_id("snapshot", document_id, digest, snapshot_policy_version)
    outline_boundaries = align_outline(prepared.paragraphs, outline)
    boundary_offsets = [boundary[0] for boundary in outline_boundaries]
    sections = tuple(
        _section_from_paragraph(
            snapshot_id=snapshot_id,
            normalized_text=normalized_text,
            paragraph=paragraph,
            outline_present=bool(outline),
            outline_boundary=(
                outline_boundaries[bisect_right(boundary_offsets, paragraph.start_char) - 1]
                if boundary_offsets and bisect_right(boundary_offsets, paragraph.start_char) > 0
                else None
            ),
        )
        for paragraph in prepared.paragraphs
    )
    if not sections and normalized_text:
        sections = (
            _whole_document_section(
                snapshot_id=snapshot_id,
                normalized_text=normalized_text,
            ),
        )
    sections, projection_findings = _project_structure(sections, structure)
    source_elements, element_findings = _source_elements(
        snapshot_id=snapshot_id,
        normalized_text=normalized_text,
        structure=structure,
        artifacts=artifacts,
    )
    if source_ref is not None:
        source_elements = _with_source_root(
            snapshot_id=snapshot_id,
            source=source,
            raw_payload_ref=source_ref.path,
            source_digest=source_ref.content_digest,
            elements=source_elements,
        )
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=document_id,
        schema_version="1",
        source_kind=source_kind,
        source_locator=source.name,
        content_digest=f"sha256:{digest}",
        captured_at=datetime.now(UTC),
        language=language,
        normalized_text_ref=text_ref.path,
        sections=sections,
        source_elements=source_elements,
        attachments=((source_ref.path,) if source_ref is not None else ()),
        title=title or source.stem,
        author=author,
        parse_findings=(
            adapter_finding,
            *structure_findings,
            *projection_findings,
            *element_findings,
            *(
                (f"epub_outline_aligned:{len(outline_boundaries)}/{len(outline)}",)
                if outline
                else ()
            ),
            "reading_pipeline_not_run_during_ingestion",
        ),
    )


def _with_source_root(
    *,
    snapshot_id: str,
    source: Path,
    raw_payload_ref: str,
    source_digest: str,
    elements: tuple[SourceElement, ...],
) -> tuple[SourceElement, ...]:
    """Preserve the original file even when normalized extraction is empty."""

    root_id = stable_id(
        "source_element",
        snapshot_id,
        "source_document",
        source_digest,
    )
    top_level_ids = tuple(
        element.element_id for element in elements if element.parent_element_id is None
    )
    first_id = (
        min(
            elements,
            key=lambda element: (
                element.reading_order,
                element.ordinal,
                element.element_id,
            ),
        ).element_id
        if elements
        else None
    )
    adjusted = tuple(
        replace(
            element,
            ordinal=element.ordinal + 1,
            reading_order=element.reading_order + 1,
            parent_element_id=(
                root_id if element.parent_element_id is None else element.parent_element_id
            ),
            previous_element_id=(
                root_id
                if element.element_id == first_id and element.previous_element_id is None
                else element.previous_element_id
            ),
        )
        for element in elements
    )
    root = SourceElement(
        element_id=root_id,
        snapshot_id=snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="preserved",
        kind="source_document",
        child_element_ids=top_level_ids,
        next_element_id=first_id,
        structural_relations=tuple(("contains", element_id) for element_id in top_level_ids),
        native_reference=source.name,
        raw_payload_ref=raw_payload_ref,
    )
    return (root, *adjusted)


def _project_structure(
    sections: tuple[DocumentSection, ...],
    structure: Sequence[SectionStructure],
) -> tuple[tuple[DocumentSection, ...], tuple[str, ...]]:
    """Attach occurrence-aligned exact structure without guessing mismatched groups."""

    if not structure:
        return sections, ()
    sections_by_text: dict[str, list[DocumentSection]] = {}
    structure_by_text: dict[str, list[SectionStructure]] = {}
    for section in sections:
        sections_by_text.setdefault(section.anchor.exact_text, []).append(section)
    for structure_item in structure:
        if structure_item.exact_text is None:
            continue
        structure_by_text.setdefault(structure_item.exact_text, []).append(structure_item)

    assignments: dict[str, SectionStructure] = {}
    for text, matching_sections in sections_by_text.items():
        matching_structure = structure_by_text.get(text, [])
        if len(matching_sections) != len(matching_structure):
            continue
        assignments.update(
            {
                section.section_id: structure_item
                for section, structure_item in zip(
                    matching_sections, matching_structure, strict=True
                )
            }
        )

    projected: list[DocumentSection] = []
    matched = 0
    for section in sections:
        projected_item = assignments.get(section.section_id)
        if projected_item is None:
            projected.append(section)
            continue
        projected.append(
            DocumentSection(
                section_id=section.section_id,
                title=section.title,
                start_offset=section.start_offset,
                end_offset=section.end_offset,
                anchor=section.anchor,
                kind=projected_item.kind,
                parent_element_id=projected_item.parent_element_id,
                heading_trail=projected_item.heading_trail,
                element_id=projected_item.element_id,
                page=projected_item.page,
                bounding_box=projected_item.bounding_box,
            )
        )
        matched += 1
    unmatched = len(structure) - matched
    return tuple(projected), (
        f"xberg_structure_projected:{matched}/{len(structure)}",
        *(
            (f"xberg_structure_unsupported_unaligned_or_ambiguous:{unmatched}",)
            if unmatched
            else ()
        ),
    )


def _source_elements(
    *,
    snapshot_id: str,
    normalized_text: str,
    structure: Sequence[SectionStructure],
    artifacts: ArtifactStore,
) -> tuple[tuple[SourceElement, ...], tuple[str, ...]]:
    """Preserve every adapter element, including partial and non-text elements."""

    staged: list[tuple[SectionStructure, SourceElement]] = []
    search_offsets: dict[str, int] = {}
    seen_ids: set[str] = set()
    native_ids: dict[str, list[str]] = {}
    for ordinal, item in enumerate(structure):
        start, end = _structure_range(item, normalized_text, search_offsets)
        projected = start is not None and end is not None
        raw_payload_ref = (
            artifacts.put_text(item.raw_payload, artifact_type="source_element_payload").path
            if item.raw_payload is not None
            else None
        )
        base_id = item.element_id or stable_id(
            "source_element",
            snapshot_id,
            str(ordinal),
            item.kind or "",
            item.exact_text or "",
            item.native_reference or "",
        )
        element_id = base_id
        if element_id in seen_ids:
            element_id = stable_id("source_element_collision", snapshot_id, base_id, str(ordinal))
        seen_ids.add(element_id)
        if item.element_id is not None:
            native_ids.setdefault(item.element_id, []).append(element_id)
        staged.append(
            (
                item,
                SourceElement(
                    element_id=element_id,
                    snapshot_id=snapshot_id,
                    schema_version="source-element.v1",
                    ordinal=ordinal,
                    reading_order=(
                        item.reading_order if item.reading_order is not None else ordinal
                    ),
                    projection_status=(
                        "projected"
                        if projected
                        else "preserved"
                        if item.exact_text is None
                        else "unresolved"
                    ),
                    kind=item.kind,
                    content_layer=item.content_layer,
                    exact_text=item.exact_text,
                    start_offset=start,
                    end_offset=end,
                    parent_element_id=item.parent_element_id,
                    heading_trail=item.heading_trail,
                    page=item.page,
                    bounding_box=item.bounding_box,
                    native_reference=item.native_reference,
                    raw_payload_ref=raw_payload_ref,
                ),
            )
        )

    element_ids = {element.element_id for _, element in staged}

    def resolve(reference: str | None) -> str | None:
        if reference is None:
            return None
        if reference in element_ids:
            return reference
        candidates = native_ids.get(reference, [])
        return candidates[0] if len(candidates) == 1 else None

    children: dict[str, list[str]] = {element_id: [] for element_id in element_ids}
    parent_by_id: dict[str, str | None] = {
        element.element_id: resolve(item.parent_element_id) for item, element in staged
    }
    unresolved_parent = 0
    unresolved_children = 0
    unresolved_relations = 0
    for item, element in staged:
        parent_id = parent_by_id[element.element_id]
        if item.parent_element_id is not None and parent_id is None:
            unresolved_parent += 1
        if parent_id is not None:
            children[parent_id].append(element.element_id)
    for item, element in staged:
        for native_child_id in item.child_element_ids:
            child_id = resolve(native_child_id)
            if child_id is None:
                unresolved_children += 1
                continue
            existing_parent = parent_by_id.get(child_id)
            if existing_parent not in {None, element.element_id}:
                unresolved_children += 1
                continue
            parent_by_id[child_id] = element.element_id
            if child_id not in children[element.element_id]:
                children[element.element_id].append(child_id)

    normalized_relations: dict[str, list[tuple[str, str]]] = {
        element_id: [] for element_id in element_ids
    }
    for item, element in staged:
        for relation, native_target_id in item.structural_relations:
            target_id = resolve(native_target_id)
            if target_id is None:
                unresolved_relations += 1
                continue
            normalized_relations[element.element_id].append((relation, target_id))

    ordered = sorted(
        (element for _, element in staged),
        key=lambda element: (element.reading_order, element.ordinal, element.element_id),
    )
    order_by_id = {element.element_id: order for order, element in enumerate(ordered)}
    previous_by_id = {
        element.element_id: ordered[index - 1].element_id if index else None
        for index, element in enumerate(ordered)
    }
    next_by_id = {
        element.element_id: (ordered[index + 1].element_id if index + 1 < len(ordered) else None)
        for index, element in enumerate(ordered)
    }
    normalized_elements = tuple(
        replace(
            element,
            reading_order=order_by_id[element.element_id],
            parent_element_id=parent_by_id[element.element_id],
            child_element_ids=tuple(
                sorted(children[element.element_id], key=order_by_id.__getitem__)
            ),
            previous_element_id=previous_by_id[element.element_id],
            next_element_id=next_by_id[element.element_id],
            structural_relations=tuple(normalized_relations[element.element_id]),
        )
        for _, element in sorted(
            staged,
            key=lambda pair: order_by_id[pair[1].element_id],
        )
    )
    unresolved = sum(element.projection_status == "unresolved" for element in normalized_elements)
    findings = (
        (
            f"source_elements_preserved:{len(normalized_elements)}",
            "source_elements_reading_order:explicit",
            *((f"source_elements_unresolved:{unresolved}",) if unresolved else ()),
            *(
                (f"source_element_parent_unresolved:{unresolved_parent}",)
                if unresolved_parent
                else ()
            ),
            *(
                (f"source_element_children_unresolved:{unresolved_children}",)
                if unresolved_children
                else ()
            ),
            *(
                (f"source_element_relations_unresolved:{unresolved_relations}",)
                if unresolved_relations
                else ()
            ),
        )
        if normalized_elements
        else ()
    )
    return normalized_elements, findings


def _structure_range(
    item: SectionStructure,
    normalized_text: str,
    search_offsets: dict[str, int],
) -> tuple[int | None, int | None]:
    if item.start_offset is not None and item.end_offset is not None:
        if 0 <= item.start_offset <= item.end_offset <= len(normalized_text) and (
            item.exact_text is None
            or normalized_text[item.start_offset : item.end_offset] == item.exact_text
        ):
            return item.start_offset, item.end_offset
        return None, None
    if not item.exact_text:
        return None, None
    start = normalized_text.find(item.exact_text, search_offsets.get(item.exact_text, 0))
    if start < 0:
        return None, None
    end = start + len(item.exact_text)
    search_offsets[item.exact_text] = end
    return start, end


def _section_from_paragraph(
    *,
    snapshot_id: str,
    normalized_text: str,
    paragraph: _core.ParagraphAnchor,
    outline_present: bool = False,
    outline_boundary: tuple[int, int, str] | None = None,
) -> DocumentSection:
    if outline_boundary is None:
        section_id = stable_id(
            "section",
            snapshot_id,
            "frontmatter" if outline_present else "paragraph",
            "" if outline_present else str(paragraph.ordinal),
        )
        title = None
    else:
        _, outline_ordinal, title = outline_boundary
        section_id = stable_id("section", snapshot_id, "outline", str(outline_ordinal), title)
    start = paragraph.start_char
    end = paragraph.end_char
    anchor = SpanAnchor(
        anchor_id=paragraph.anchor_id,
        snapshot_id=snapshot_id,
        section_id=section_id,
        start_offset=start,
        end_offset=end,
        exact_text=paragraph.text,
        prefix=normalized_text[max(0, start - 32) : start],
        suffix=normalized_text[end : end + 32],
    )
    return DocumentSection(
        section_id=section_id,
        title=title,
        start_offset=start,
        end_offset=end,
        anchor=anchor,
    )


def _whole_document_section(
    *,
    snapshot_id: str,
    normalized_text: str,
) -> DocumentSection:
    section_id = stable_id("section", snapshot_id, "document")
    anchor = SpanAnchor.create(
        snapshot_id=snapshot_id,
        section_id=section_id,
        text=normalized_text,
        start_offset=0,
        end_offset=len(normalized_text),
    )
    return DocumentSection(
        section_id=section_id,
        title=None,
        start_offset=0,
        end_offset=len(normalized_text),
        anchor=anchor,
    )

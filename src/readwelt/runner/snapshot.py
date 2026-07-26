"""Map extracted canonical text into Readwelt's immutable snapshot contract."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from readwelt import _core
from readwelt.domain import DocumentSection, SourceDocumentSnapshot, SpanAnchor, stable_id
from readwelt.runner.outline import OutlineItem, align_outline
from readwelt.storage import ArtifactStore


@dataclass(frozen=True, slots=True)
class SectionStructure:
    """Structure explicitly emitted by an extraction adapter."""

    exact_text: str
    kind: str | None = None
    parent_element_id: str | None = None
    heading_trail: tuple[str, ...] = ()
    element_id: str | None = None
    page: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None


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
) -> SourceDocumentSnapshot:
    prepared = _core.prepare(text)
    normalized_text = prepared.text
    text_ref = artifacts.put_text(normalized_text, artifact_type="normalized_text")
    digest = prepared.digest
    document_id = stable_id("document", digest)
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
    if not sections:
        sections = (
            _whole_document_section(
                snapshot_id=snapshot_id,
                normalized_text=normalized_text,
            ),
        )
    sections, projection_findings = _project_structure(sections, structure)
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
        title=title or source.stem,
        author=author,
        parse_findings=(
            adapter_finding,
            *structure_findings,
            *projection_findings,
            *(
                (f"epub_outline_aligned:{len(outline_boundaries)}/{len(outline)}",)
                if outline
                else ()
            ),
            "reading_pipeline_not_run_during_ingestion",
        ),
    )


def _project_structure(
    sections: tuple[DocumentSection, ...],
    structure: Sequence[SectionStructure],
) -> tuple[tuple[DocumentSection, ...], tuple[str, ...]]:
    """Attach only unambiguous, exact-text structure records."""

    if not structure:
        return sections, ()
    section_counts: dict[str, int] = {}
    structure_counts: dict[str, int] = {}
    for section in sections:
        section_counts[section.anchor.exact_text] = (
            section_counts.get(section.anchor.exact_text, 0) + 1
        )
    by_text: dict[str, SectionStructure] = {}
    for structure_item in structure:
        structure_counts[structure_item.exact_text] = (
            structure_counts.get(structure_item.exact_text, 0) + 1
        )
        by_text[structure_item.exact_text] = structure_item

    projected: list[DocumentSection] = []
    matched = 0
    for section in sections:
        text = section.anchor.exact_text
        projected_item = by_text.get(text)
        if (
            projected_item is None
            or section_counts[text] != 1
            or structure_counts[text] != 1
        ):
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

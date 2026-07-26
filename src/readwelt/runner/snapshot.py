"""Map extracted canonical text into Readwelt's immutable snapshot contract."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from readwelt import _core
from readwelt.domain import DocumentSection, SourceDocumentSnapshot, SpanAnchor, stable_id
from readwelt.storage import ArtifactStore


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
) -> SourceDocumentSnapshot:
    prepared = _core.prepare(text)
    normalized_text = prepared.text
    text_ref = artifacts.put_text(normalized_text, artifact_type="normalized_text")
    digest = prepared.digest
    document_id = stable_id("document", digest)
    snapshot_id = stable_id("snapshot", document_id, digest, "1")
    sections = tuple(
        _section_from_paragraph(
            snapshot_id=snapshot_id,
            normalized_text=normalized_text,
            paragraph=paragraph,
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
        parse_findings=(adapter_finding, "reading_pipeline_not_run_during_ingestion"),
    )


def _section_from_paragraph(
    *,
    snapshot_id: str,
    normalized_text: str,
    paragraph: _core.ParagraphAnchor,
) -> DocumentSection:
    section_id = stable_id("section", snapshot_id, str(paragraph.ordinal))
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
        title=None,
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

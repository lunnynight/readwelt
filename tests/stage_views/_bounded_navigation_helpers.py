from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

from readwelt.article_graph import ArticleGraphBuilder, ArticleGraphBuildResult
from readwelt.domain import (
    DocumentSection,
    ReadingStage,
    SourceDocumentSnapshot,
    SourceElement,
    SpanAnchor,
    stable_id,
)
from readwelt.semantic import SemanticEvidencePacket


def _snapshot(paragraphs: tuple[str, ...]) -> tuple[SourceDocumentSnapshot, str]:
    text = "\n\n".join(paragraphs)
    snapshot_id = stable_id("snapshot", text)
    document_id = stable_id("document", text)
    sections: list[DocumentSection] = []
    cursor = 0
    for ordinal, paragraph in enumerate(paragraphs):
        start = text.index(paragraph, cursor)
        end = start + len(paragraph)
        cursor = end
        section_id = stable_id("section", snapshot_id, str(ordinal))
        sections.append(
            DocumentSection(
                section_id=section_id,
                title=f"Section {ordinal + 1}",
                start_offset=start,
                end_offset=end,
                anchor=SpanAnchor.create(
                    snapshot_id=snapshot_id,
                    section_id=section_id,
                    text=text,
                    start_offset=start,
                    end_offset=end,
                ),
            )
        )
    return (
        SourceDocumentSnapshot(
            snapshot_id=snapshot_id,
            document_id=document_id,
            schema_version="1",
            source_kind="text/plain",
            source_locator="bounded.txt",
            content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
            captured_at=datetime(2026, 7, 27, tzinfo=UTC),
            language="en",
            normalized_text_ref="objects/bounded",
            sections=tuple(sections),
        ),
        text,
    )


def _build(*paragraphs: str) -> ArticleGraphBuildResult:
    snapshot, text = _snapshot(tuple(paragraphs))
    return ArticleGraphBuilder().build(snapshot, text)


def _build_with_elements(
    text: str,
    elements: tuple[SourceElement, ...],
) -> ArticleGraphBuildResult:
    snapshot, normalized = _snapshot((text,) if text else ())
    return ArticleGraphBuilder().build(
        replace(snapshot, source_elements=elements),
        normalized,
    )


def _anchor_ids(build: ArticleGraphBuildResult) -> tuple[str, ...]:
    return tuple(
        reference.anchor_id
        for unit in build.unitization.units
        for reference in unit.source_references
        if reference.anchor_id is not None
    )


def _locator(
    build: ArticleGraphBuildResult,
    anchor: SpanAnchor,
) -> SemanticEvidencePacket:
    return SemanticEvidencePacket(
        schema_version="1",
        snapshot_id=build.snapshot_id,
        purpose="bounded navigation",
        anchors=(anchor,),
        retrieval_queries=("bounded",),
        omitted=(),
        covered_section_ids=(anchor.section_id,),
        omitted_section_ids=(),
        token_budget=256,
        estimated_tokens=8,
        coverage_complete=False,
        stage=ReadingStage.MAINLINE,
    )

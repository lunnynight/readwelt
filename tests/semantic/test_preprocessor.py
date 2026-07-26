from __future__ import annotations

from datetime import UTC, datetime

import pytest

from readwelt.domain import DocumentSection, SourceDocumentSnapshot, SpanAnchor, stable_id
from readwelt.semantic import SemanticPreprocessor, build_evidence_packet
from readwelt.semantic.lexical import BM25Index
from readwelt.semantic.tokenization import tokenize


def _snapshot(text: str, ranges: tuple[tuple[int, int], ...]) -> SourceDocumentSnapshot:
    snapshot_id = stable_id("snapshot", text)
    sections = []
    for ordinal, (start, end) in enumerate(ranges):
        section_id = stable_id("section", snapshot_id, str(ordinal))
        anchor = SpanAnchor.create(
            snapshot_id=snapshot_id,
            section_id=section_id,
            text=text,
            start_offset=start,
            end_offset=end,
        )
        sections.append(
            DocumentSection(
                section_id=section_id,
                title=None,
                start_offset=start,
                end_offset=end,
                anchor=anchor,
            )
        )
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=stable_id("document", text),
        schema_version="1",
        source_kind="text/plain",
        source_locator="article.txt",
        content_digest=f"sha256:{'1' * 64}",
        captured_at=datetime.now(UTC),
        language="zh",
        normalized_text_ref="objects/11/body",
        sections=tuple(sections),
    )


def test_prepare_reuses_anchors_and_is_deterministic() -> None:
    text = "机器学习改变检索。\n传统索引依然重要。"
    snapshot = _snapshot(text, ((0, 9), (10, len(text))))
    preprocessor = SemanticPreprocessor()

    first = preprocessor.prepare(snapshot, text)
    second = preprocessor.prepare(snapshot, text)

    assert tuple(segment.anchor for segment in first.segments) == tuple(
        section.anchor for section in snapshot.sections
    )
    assert first == second
    assert first.coverage.full_source_covered
    assert first.coverage.indexed_anchor_ids == tuple(
        section.anchor.anchor_id for section in snapshot.sections
    )


def test_prepare_rejects_normalized_text_drift() -> None:
    snapshot = _snapshot("不可漂移", ((0, 4),))

    with pytest.raises(ValueError, match="does not match"):
        SemanticPreprocessor().prepare(snapshot, "不可偏移")


def test_coverage_reports_unanchored_source_instead_of_claiming_full_read() -> None:
    text = "已锚定。关键遗漏。"
    snapshot = _snapshot(text, ((0, 4),))

    atlas = SemanticPreprocessor().prepare(snapshot, text)
    packet = build_evidence_packet(atlas, "关键", 100)

    assert not atlas.coverage.full_source_covered
    assert atlas.coverage.unanchored_non_whitespace_ranges[0].start_offset == 4
    assert not packet.coverage_complete


def test_budget_is_strict_and_omissions_are_explicit() -> None:
    text = "第一章节内容。\n第二章节包含更多内容。"
    snapshot = _snapshot(text, ((0, 7), (8, len(text))))
    atlas = SemanticPreprocessor().prepare(snapshot, text)

    packet = build_evidence_packet(atlas, "章节内容", 8)

    assert packet.estimated_tokens <= packet.token_budget
    assert packet.omitted
    assert all(item.reason == "token_budget" for item in packet.omitted)
    assert not packet.coverage_complete
    assert packet.omitted_section_ids
    assert len(packet.anchors) + len(packet.omitted) == len(atlas.segments)


def test_chinese_bigram_bm25_retrieves_relevant_anchor() -> None:
    documents = (
        tokenize("苹果香蕉水果"),
        tokenize("量子计算芯片"),
        tokenize("古典音乐旋律"),
    )
    ranking = BM25Index(documents).rank(tokenize("量子芯片"))

    assert ranking[0][0] == 1
    assert ranking[0][1] > ranking[1][1]


def test_exact_duplicate_and_near_duplicate_candidates_are_stable() -> None:
    text = "知识图谱用于检索。\n知识图谱用于检索。\n知识图谱可以用于检索。"
    first_end = text.index("\n")
    second_start = first_end + 1
    second_end = text.index("\n", second_start)
    snapshot = _snapshot(
        text,
        ((0, first_end), (second_start, second_end), (second_end + 1, len(text))),
    )

    atlas = SemanticPreprocessor(near_duplicate_threshold=0.5).prepare(snapshot, text)

    assert atlas.segments[1].exact_duplicate_of == atlas.segments[0].anchor.anchor_id
    assert atlas.segments[2].near_duplicate_candidate_ids

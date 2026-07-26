from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import (
    DocumentSection,
    ReadingStage,
    SourceDocumentSnapshot,
    SpanAnchor,
    stable_id,
)
from readwelt.stage_views import StageContext, StageViewProjector


def _snapshot(text: str) -> SourceDocumentSnapshot:
    snapshot_id = stable_id("snapshot", text)
    document_id = stable_id("document", text)
    sections: list[DocumentSection] = []
    cursor = 0
    for ordinal, paragraph in enumerate(text.split("\n\n")):
        start = text.index(paragraph, cursor)
        end = start + len(paragraph)
        cursor = end
        section_id = stable_id("section", snapshot_id, str(ordinal))
        sections.append(
            DocumentSection(
                section_id=section_id,
                title=None,
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
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=document_id,
        schema_version="1",
        source_kind="text/plain",
        source_locator="qa-article.txt",
        content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        language="en",
        normalized_text_ref="objects/qa/article",
        sections=tuple(sections),
    )


# Regression: ISSUE-003 — provider StageView serialized every token node and
# reported only source-text tokens for a much larger provider payload.
# Found by /qa on 2026-07-27
# Report: .gstack/qa-reports/qa-report-127-0-0-1-2026-07-27.md
def test_provider_stage_view_excludes_linguistic_scaffolding_and_counts_bytes() -> None:
    text = (
        "A cache keyed only by name can return stale analysis.\n\n"
        "Derived artifacts should include the source revision.\n\n"
        "A content digest is sufficient when normalization is recorded."
    )
    build = ArticleGraphBuilder().build(_snapshot(text), text)
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="recover the article mainline",
            token_budget=256,
        ),
    )

    mapping = view.to_mapping()
    encoded = json.dumps(
        mapping,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    measured_tokens = (len(encoded) + 3) // 4

    assert {node["kind"] for node in mapping["nodes"]}.isdisjoint(
        {"token", "sentence"}
    )
    assert "capability_outcomes" not in mapping
    assert "selection_reasons" not in mapping
    assert all("text" not in unit for unit in mapping["text_units"])
    assert abs(mapping["estimated_serialized_tokens"] - measured_tokens) <= 10
    assert len(encoded) < 10_000

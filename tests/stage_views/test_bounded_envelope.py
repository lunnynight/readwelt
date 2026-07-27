from __future__ import annotations

import json
from dataclasses import replace

import pytest

from readwelt.article_graph import CanonicalizationPhase, ConflictRecord
from readwelt.domain import ReadingStage
from readwelt.stage_views import StageContext, StageViewProjector
from readwelt.stage_views.serialization import conflict_id_page, coverage_omission_page
from tests.stage_views._bounded_navigation_helpers import (
    _anchor_ids,
    _build,
)


def test_complete_stage_view_mapping_honors_explicit_hard_budget() -> None:
    build = _build("Short bounded source.")
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="enforce complete mapping budget",
            token_budget=64,
            hard_serialized_token_budget=8_000,
            rescue_level="section",
        ),
    )

    mapping = view.to_mapping()
    assert mapping["budget_scope"] == "complete_stage_view_serialization"
    estimated = mapping["estimated_serialized_tokens"]
    assert isinstance(estimated, int)
    assert estimated <= 8_000
    encoded = json.dumps(
        mapping,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert estimated == len(encoded)


def test_long_source_never_requires_full_document_in_one_view() -> None:
    build = _build("".join(str(index % 10) for index in range(100_000)))
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="bounded long-document traversal",
        token_budget=128,
        rescue_level="section",
    )
    view = StageViewProjector().project(build, context)

    assert sum(len(unit.text) for unit in view.text_units) <= 512
    assert view.continuation is not None
    assert view.continuation.frontier[0].start_offset == 512
    assert view.coverage is not None
    assert not view.coverage.stage_input_complete or view.coverage.omitted


@pytest.mark.parametrize("hard_budget", (4_000, 8_000, 16_000))
def test_many_paragraph_coverage_envelope_always_honors_hard_budget(
    hard_budget: int,
) -> None:
    paragraphs = tuple(
        f"Paragraph {index:03d} contains bounded source evidence." for index in range(220)
    )
    build = _build(*paragraphs)
    critical_anchor = _anchor_ids(build)[-1]

    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="bound the complete provider envelope",
            token_budget=512,
            hard_serialized_token_budget=hard_budget,
            critical_anchor_ids=(critical_anchor,),
            rescue_level="section",
        ),
    )
    mapping = view.to_mapping()
    encoded = json.dumps(
        mapping,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    assert mapping["estimated_serialized_tokens"] == len(encoded)
    assert mapping["estimated_serialized_tokens"] <= hard_budget
    coverage = mapping["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["schema_version"] == "stage-view-coverage-envelope.v1"
    assert coverage["source"]["count"] == 220
    assert coverage["critical"]["omitted_count"] == 1
    omission_page = coverage["omission_page"]
    assert omission_page["total_count"] == len(view.coverage.omitted)
    if omission_page["items"]:
        assert omission_page["items"][0]["critical"]


def test_compact_omission_cursor_recovers_every_persisted_record() -> None:
    build = _build(*(f"Paragraph {index:03d} contains traceable evidence." for index in range(220)))
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="page every omission",
            token_budget=32,
            hard_serialized_token_budget=4_000,
            critical_anchor_ids=(_anchor_ids(build)[-1],),
            rescue_level="section",
        ),
    )
    assert view.coverage is not None

    provider_page = view.to_mapping()["coverage"]["omission_page"]
    recovered = [item["identity"] for item in provider_page["items"]]
    cursor: str | None = provider_page["next_cursor"]
    while True:
        if cursor is None:
            break
        page = coverage_omission_page(view.coverage, cursor=cursor, limit=17)
        recovered.extend(item["identity"] for item in page["items"])
        cursor = page["next_cursor"]

    assert set(recovered) == {item.identity for item in view.coverage.omitted}
    assert len(recovered) == len(view.coverage.omitted)


def test_hundred_thousand_character_document_keeps_complete_envelope_bounded() -> None:
    paragraph = "Long-document evidence remains source-grounded and resumable. " * 8
    paragraphs = tuple(f"{index:03d} {paragraph}" for index in range(230))
    assert len("\n\n".join(paragraphs)) >= 100_000
    build = _build(*paragraphs)

    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="bound a 100k document provider packet",
            token_budget=256,
            hard_serialized_token_budget=8_000,
            critical_anchor_ids=(_anchor_ids(build)[-1],),
            rescue_level="section",
        ),
    )
    mapping = view.to_mapping()

    assert mapping["estimated_serialized_tokens"] <= 8_000
    assert view.continuation is not None
    coverage = mapping["coverage"]
    assert coverage["source"]["count"] == len(build.unitization.units)
    assert coverage["critical"]["omitted_count"] == 1


def test_hard_envelope_shrink_never_skips_the_next_source_ordinal() -> None:
    build = _build(
        *(
            f"Paragraph {index:02d} carries one complete source unit for traversal."
            for index in range(43)
        )
    )
    base_context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="traverse every ordinal without page-boundary gaps",
        token_budget=64,
        hard_serialized_token_budget=8_000,
        rescue_level="section",
    )
    continuation = None
    presented_ordinals: list[int] = []
    presented_text: dict[int, list[str]] = {}
    cursor_digests: set[str] = set()

    while True:
        view = StageViewProjector().project(
            build,
            replace(base_context, continuation=continuation),
        )
        mapping = view.to_mapping()
        assert mapping["estimated_serialized_tokens"] <= 8_000
        presented_ordinals.extend(unit.ordinal for unit in view.text_units)
        for unit in view.text_units:
            presented_text.setdefault(unit.ordinal, []).append(unit.text)
        continuation = view.continuation
        if continuation is None:
            break
        assert continuation.content_digest not in cursor_digests
        cursor_digests.add(continuation.content_digest)
        assert len(cursor_digests) <= len(build.unitization.units)

    assert tuple(dict.fromkeys(presented_ordinals)) == tuple(range(43))
    for unit in build.unitization.units:
        assert "".join(presented_text[unit.ordinal]) == unit.exact_text


def test_large_conflict_diagnostics_are_bounded_recoverable_and_do_not_starve_text() -> None:
    build = _build(
        *(
            f"Corpus paragraph {index:02d} preserves grounded traversal evidence."
            for index in range(93)
        )
    )
    conflicts = tuple(
        ConflictRecord(
            conflict_id=f"conflict-{index:04d}",
            phase=CanonicalizationPhase.IDENTITY_RESOLUTION,
            candidate_ids=(f"candidate-{index:04d}",),
            reason="fixture ambiguity",
            evidence_refs=(build.unitization.units[index % 93].unit_id,),
            decision_id=f"decision-{index:04d}",
            content_digest=f"sha256:{index:064x}",
        )
        for index in range(464)
    )
    build = replace(
        build,
        merge_report=replace(build.merge_report, conflicts=conflicts),
    )
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="traverse with bounded conflict diagnostics",
        token_budget=64,
        hard_serialized_token_budget=16_384,
        rescue_level="section",
    )

    first = StageViewProjector().project(build, context)
    first_mapping = first.to_mapping()
    assert first.text_units
    assert first_mapping["estimated_serialized_tokens"] <= 16_384
    conflict_page = first_mapping["unresolved_conflicts"]
    assert conflict_page["total_count"] == 464
    assert conflict_page["returned_count"] > 0
    first_selected_ids = {unit.unit_id for unit in first.text_units}
    conflict_by_id = {item.conflict_id: item for item in conflicts}
    assert first_selected_ids.intersection(
        conflict_by_id[conflict_page["conflict_ids"][0]].evidence_refs
    )

    recovered_conflicts = list(conflict_page["conflict_ids"])
    conflict_cursor = conflict_page["next_cursor"]
    while conflict_cursor is not None:
        page = conflict_id_page(
            first.unresolved_conflict_ids,
            cursor=conflict_cursor,
            limit=37,
        )
        recovered_conflicts.extend(page["conflict_ids"])
        conflict_cursor = page["next_cursor"]
    assert recovered_conflicts == list(first.unresolved_conflict_ids)

    continuation = None
    cursor_digests: set[str] = set()
    presented_text: dict[int, list[str]] = {}
    while True:
        view = StageViewProjector().project(
            build,
            replace(context, continuation=continuation),
        )
        assert view.to_mapping()["estimated_serialized_tokens"] <= 16_384
        for unit in view.text_units:
            presented_text.setdefault(unit.ordinal, []).append(unit.text)
        continuation = view.continuation
        if continuation is None:
            break
        assert continuation.content_digest not in cursor_digests
        cursor_digests.add(continuation.content_digest)
        assert len(cursor_digests) <= len(build.unitization.units) * 2

    assert set(presented_text) == set(range(93))
    for unit in build.unitization.units:
        assert "".join(presented_text[unit.ordinal]) == unit.exact_text

from __future__ import annotations

from dataclasses import replace

import pytest

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import ReadingStage, SourceElement, stable_id
from readwelt.stage_views import StageContext, StageViewProjector
from readwelt.stage_views.models import StageViewContinuationCursor
from tests.stage_views._bounded_navigation_helpers import (
    _anchor_ids,
    _build,
    _locator,
    _snapshot,
)


def test_coverage_manifest_separates_source_presentation_and_critical() -> None:
    build = _build(
        "First bounded paragraph.",
        "Second critical paragraph.",
        "Third bounded paragraph.",
    )
    anchors = _anchor_ids(build)
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="recover bounded evidence",
            token_budget=6,
            critical_anchor_ids=(anchors[1],),
            rescue_level="section",
        ),
    )

    assert view.coverage is not None
    assert view.coverage.source_complete
    assert set(view.coverage.source_unit_ids) == {unit.unit_id for unit in build.unitization.units}
    assert view.coverage.selected_unit_ids
    assert view.coverage.serialized_identities
    assert not view.coverage.stage_input_complete
    assert view.coverage.critical_unit_ids == (build.unitization.units[1].unit_id,)
    assert {item.reason for item in view.coverage.omitted}.issuperset({"continuation_pending"})
    assert view.continuation is not None


def test_continuation_is_deterministic_and_bound_to_policy_and_index() -> None:
    paragraphs = tuple(f"Paragraph {index} has bounded content." for index in range(6))
    build = _build(*paragraphs)
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="page through the source",
        token_budget=8,
        rescue_level="section",
    )
    first = StageViewProjector().project(build, context)
    assert first.continuation is not None
    assert first.continuation.source_plane_schema_version == "article-source-plane.v1"

    resumed_context = replace(context, continuation=first.continuation)
    second = StageViewProjector().project(build, resumed_context)
    repeated = StageViewProjector().project(build, resumed_context)

    assert second == repeated
    assert {unit.serialized_identity for unit in first.text_units}.isdisjoint(
        unit.serialized_identity for unit in second.text_units
    )

    with pytest.raises(ValueError, match="stale or incompatible"):
        StageViewProjector().project(
            build,
            replace(
                resumed_context,
                task_intent="a different policy",
            ),
        )

    historical_cursor = StageViewContinuationCursor.create(
        snapshot_id=first.continuation.snapshot_id,
        source_plane_schema_version="anchored-text-unitization.v1",
        stage=first.continuation.stage,
        policy_digest=first.continuation.policy_digest,
        index_digest=first.continuation.index_digest,
        frontier=first.continuation.frontier,
        visited_unit_ids=first.continuation.visited_unit_ids,
    )
    with pytest.raises(ValueError, match="stale or incompatible"):
        StageViewProjector().project(
            build,
            replace(context, continuation=historical_cursor),
        )


def test_neighbor_and_parent_child_rescue_expand_from_locator_hit() -> None:
    build = _build("Root source.", "Child source.", "Unrelated source.")
    units = build.unitization.units
    structured_units = (
        replace(
            units[0],
            previous_unit_id=None,
            next_unit_id=None,
        ),
        replace(
            units[1],
            parent_unit_id=units[0].unit_id,
            previous_unit_id=None,
            next_unit_id=None,
        ),
        replace(
            units[2],
            previous_unit_id=None,
            next_unit_id=None,
        ),
    )
    build = replace(
        build,
        unitization=replace(build.unitization, units=structured_units),
    )
    root_anchor = next(
        section.anchor
        for section in _snapshot(("Root source.", "Child source.", "Unrelated source."))[0].sections
        if section.anchor.anchor_id
        == next(
            reference.anchor_id
            for reference in structured_units[0].source_references
            if reference.anchor_id is not None
        )
    )
    all_anchors = _anchor_ids(build)

    initial = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="initial locator only",
            token_budget=64,
            allowed_anchor_ids=all_anchors,
            rescue_level="initial",
        ),
        locator_packet=_locator(build, root_anchor),
    )
    rescued = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="expand structural family",
            token_budget=64,
            allowed_anchor_ids=all_anchors,
            rescue_level="structure",
        ),
        locator_packet=_locator(build, root_anchor),
    )

    assert tuple(unit.unit_id for unit in initial.text_units) == (units[0].unit_id,)
    assert tuple(unit.unit_id for unit in rescued.text_units) == (
        units[0].unit_id,
        units[1].unit_id,
    )


def test_oversized_unit_is_sliced_with_stable_provenance_and_resumed() -> None:
    build = _build("A" * 200)
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="slice oversized source",
        token_budget=10,
        rescue_level="section",
    )

    first = StageViewProjector().project(build, context)
    repeated = StageViewProjector().project(build, context)

    assert first == repeated
    assert len(first.text_units) == 1
    assert first.text_units[0].slice_id is not None
    assert first.text_units[0].slice_start == 0
    assert first.text_units[0].slice_end == 40
    assert first.continuation is not None
    assert first.continuation.frontier[0].start_offset == 40
    assert first.coverage is not None
    assert first.coverage.omitted[0].reason == "oversized_unit_remainder"

    second = StageViewProjector().project(
        build,
        replace(context, continuation=first.continuation),
    )
    assert second.text_units[0].slice_start == 40
    assert second.text_units[0].slice_end == 80


def test_unsplittable_oversized_unit_returns_explicit_blocking_record() -> None:
    build = _build("B" * 200)
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="block unsplittable source",
            token_budget=10,
            rescue_level="section",
            split_oversized_units=False,
        ),
    )

    assert not view.text_units
    assert view.blocking_records
    assert view.blocking_records[0].reason == "oversized_source_item_requires_split"
    assert view.coverage is not None
    assert view.coverage.omitted[0].reason == "oversized_unit_blocked"


def test_complete_source_plane_cursor_pages_ranges_and_slices_large_element() -> None:
    text = "T" * 240
    snapshot, _ = _snapshot((text,))
    table = SourceElement(
        element_id=stable_id("element", snapshot.snapshot_id, "table"),
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="projected",
        kind="table",
        exact_text=text,
        start_offset=0,
        end_offset=len(text),
        native_reference="table:0",
        raw_payload_ref="objects/table-0",
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(table,)),
        text,
    )
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="traverse complete Source Plane",
        token_budget=64,
        hard_serialized_token_budget=16_000,
        rescue_level="section",
    )
    element_slices = []
    last = None
    for _ in range(20):
        view = StageViewProjector().project(build, context)
        element_slices.extend(view.source_elements)
        last = view
        if view.continuation is None:
            break
        context = replace(context, continuation=view.continuation)

    assert last is not None
    assert last.continuation is None
    assert len(element_slices) > 1
    assert element_slices[0].slice_start == 0
    assert element_slices[-1].slice_end == len(text)
    assert all(item.raw_payload_ref == "objects/table-0" for item in element_slices)
    assert last.coverage is not None
    assert last.coverage.completed_range_ids == build.source_index.source_range_ids
    assert last.coverage.completed_element_ids == build.source_index.source_element_ids


def test_image_only_source_root_is_presented_by_raw_handle() -> None:
    snapshot, _ = _snapshot(())
    source_root = SourceElement(
        element_id=stable_id("element", snapshot.snapshot_id, "source-root"),
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="preserved",
        kind="source_document",
        native_reference="scan.pdf",
        raw_payload_ref="objects/scan-pdf",
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(source_root,)),
        "",
    )
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="locate image-only source",
            token_budget=64,
            hard_serialized_token_budget=8_000,
            rescue_level="section",
        ),
    )

    assert not view.text_units
    assert len(view.source_elements) == 1
    assert view.source_elements[0].raw_payload_ref == "objects/scan-pdf"
    assert view.coverage is not None
    assert view.coverage.completed_element_ids == (source_root.element_id,)
    mapping = view.to_mapping()
    assert mapping["source_elements"][0]["raw_payload_ref"] == "objects/scan-pdf"


def test_unsplittable_large_source_element_is_explicitly_blocked() -> None:
    text = "E" * 240
    snapshot, _ = _snapshot((text,))
    table = SourceElement(
        element_id=stable_id("element", snapshot.snapshot_id, "blocked-table"),
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="projected",
        kind="table",
        exact_text=text,
        start_offset=0,
        end_offset=len(text),
        raw_payload_ref="objects/blocked-table",
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(table,)),
        text,
    )
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="block unsplittable table",
        token_budget=32,
        rescue_level="section",
        split_oversized_units=False,
    )
    element_block = None
    for _ in range(10):
        view = StageViewProjector().project(build, context)
        element_block = next(
            (item for item in view.blocking_records if item.source_element_id == table.element_id),
            None,
        )
        if element_block is not None or view.continuation is None:
            break
        context = replace(context, continuation=view.continuation)

    assert element_block is not None
    assert element_block.reason == "oversized_source_element_requires_split"

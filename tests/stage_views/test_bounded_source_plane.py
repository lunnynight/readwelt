from __future__ import annotations

from dataclasses import replace

import pytest

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.article_graph.digest import content_digest
from readwelt.domain import ReadingStage, SourceElement, stable_id
from readwelt.stage_views import StageContext, StageViewProjector
from readwelt.stage_views.serialization import coverage_omission_page
from tests.stage_views._bounded_navigation_helpers import (
    _build,
    _snapshot,
)


def test_range_and_element_omissions_are_complete_typed_and_stably_ordered() -> None:
    text = "Bounded source keeps its range and element reachable."
    snapshot, _ = _snapshot((text,))
    element = SourceElement(
        element_id=stable_id("element", snapshot.snapshot_id, "paragraph"),
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="projected",
        kind="paragraph",
        exact_text=text,
        start_offset=0,
        end_offset=len(text),
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(element,)),
        text,
    )

    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="account for every omitted Source Plane identity",
            token_budget=1,
            rescue_level="section",
        ),
    )

    assert view.coverage is not None
    omissions = view.coverage.omitted
    assert {item.object_type for item in omissions}.issuperset({"range", "element"})
    assert {item.identity for item in omissions if item.object_type == "range"} == set(
        build.source_index.source_range_ids
    )
    assert {item.identity for item in omissions if item.object_type == "element"} == set(
        build.source_index.source_element_ids
    )
    assert [item.object_type for item in omissions] == sorted(
        (item.object_type for item in omissions),
        key={"unit": 0, "range": 1, "element": 2}.__getitem__,
    )
    assert all(item.reason for item in omissions)


def test_element_only_critical_input_cannot_complete_before_element_is_presented() -> None:
    text = "Critical figure metadata follows bounded source text."
    snapshot, _ = _snapshot((text,))
    figure = SourceElement(
        element_id=stable_id("element", snapshot.snapshot_id, "critical-figure"),
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="preserved",
        kind="figure",
        raw_payload_ref="objects/critical-figure",
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(figure,)),
        text,
    )
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="require the critical figure",
            token_budget=1,
            critical_element_ids=(figure.element_id,),
            rescue_level="section",
        ),
    )

    assert view.coverage is not None
    assert not view.coverage.stage_input_complete
    omission = next(item for item in view.coverage.omitted if item.identity == figure.element_id)
    assert omission.object_type == "element"
    omission_page = coverage_omission_page(view.coverage)
    figure_record = next(
        item for item in omission_page["items"] if item["identity"] == figure.element_id
    )
    assert figure_record["critical"]


@pytest.mark.parametrize(
    ("field", "unknown_id", "message"),
    (
        ("critical_range_ids", "range-missing", "critical_range_ids"),
        ("critical_element_ids", "element-missing", "critical_element_ids"),
        ("cited_range_ids", "cited-range-missing", "cited_range_ids"),
        ("cited_element_ids", "cited-element-missing", "cited_element_ids"),
    ),
)
def test_critical_source_plane_identities_must_resolve(
    field: str,
    unknown_id: str,
    message: str,
) -> None:
    build = _build("Known source.")
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="reject unknown critical identity",
        token_budget=64,
        rescue_level="section",
    )

    with pytest.raises(ValueError, match=message):
        StageViewProjector().project(
            build,
            replace(context, **{field: (unknown_id,)}),
        )


def test_figure_caption_structure_is_visible_with_integrity_metadata() -> None:
    text = "Figure\n\nCaption"
    snapshot, _ = _snapshot((text,))
    figure_id = stable_id("element", snapshot.snapshot_id, "figure")
    caption_id = stable_id("element", snapshot.snapshot_id, "caption")
    figure = SourceElement(
        element_id=figure_id,
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="projected",
        kind="figure",
        child_element_ids=(caption_id,),
        structural_relations=(("caption", caption_id),),
    )
    caption = SourceElement(
        element_id=caption_id,
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=1,
        reading_order=1,
        projection_status="projected",
        kind="caption",
        parent_element_id=figure_id,
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(figure, caption)),
        text,
    )
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="expose figure-caption structure",
            token_budget=256,
            critical_range_ids=build.source_index.source_range_ids,
            critical_element_ids=(figure_id, caption_id),
            cited_range_ids=build.source_index.source_range_ids,
            cited_element_ids=(figure_id, caption_id),
            rescue_level="section",
        ),
    )

    projected_figure = next(item for item in view.source_elements if item.element_id == figure_id)
    assert projected_figure.child_element_ids == (caption_id,)
    assert projected_figure.structural_relations == (("caption", caption_id),)
    assert projected_figure.child_count == len(projected_figure.child_element_ids)
    assert projected_figure.structural_relation_count == len(projected_figure.structural_relations)
    mapping = view.to_mapping()
    mapped_figure = next(
        item for item in mapping["source_elements"] if item["element_id"] == figure_id
    )
    assert mapped_figure["child_element_ids"] == [caption_id]
    assert mapped_figure["structural_relations"] == [
        {"kind": "caption", "target_element_id": caption_id}
    ]
    assert view.coverage is not None
    assert view.coverage.stage_input_complete
    assert view.coverage.cited_range_ids == build.source_index.source_range_ids
    assert view.coverage.cited_element_ids == (figure_id, caption_id)
    assert mapping["coverage"]["cited_range_ids"] == list(build.source_index.source_range_ids)
    assert mapping["coverage"]["cited_element_ids"] == [figure_id, caption_id]


def test_compact_mapping_omits_empty_defaults_but_keeps_nonempty_structure() -> None:
    text = "Figure\n\nCaption"
    snapshot, _ = _snapshot((text,))
    figure_id = stable_id("element", snapshot.snapshot_id, "compact-figure")
    caption_id = stable_id("element", snapshot.snapshot_id, "compact-caption")
    elements = (
        SourceElement(
            element_id=figure_id,
            snapshot_id=snapshot.snapshot_id,
            schema_version="source-element.v1",
            ordinal=0,
            reading_order=0,
            projection_status="projected",
            kind="figure",
            child_element_ids=(caption_id,),
            structural_relations=(("caption", caption_id),),
        ),
        SourceElement(
            element_id=caption_id,
            snapshot_id=snapshot.snapshot_id,
            schema_version="source-element.v1",
            ordinal=1,
            reading_order=1,
            projection_status="projected",
            kind="caption",
            parent_element_id=figure_id,
        ),
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=elements),
        text,
    )
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="compact only absent optional values",
            token_budget=256,
            hard_serialized_token_budget=16_000,
            rescue_level="section",
        ),
    )

    mapping = view.to_mapping()
    mapped_figure = next(
        item for item in mapping["source_elements"] if item["element_id"] == figure_id
    )
    mapped_caption = next(
        item for item in mapping["source_elements"] if item["element_id"] == caption_id
    )
    assert mapped_figure["child_element_ids"] == [caption_id]
    assert mapped_figure["structural_relations"] == [
        {"kind": "caption", "target_element_id": caption_id}
    ]
    assert "child_element_ids" not in mapped_caption
    assert "structural_relations" not in mapped_caption
    assert "native_reference" not in mapped_caption
    assert all("slice_id" not in item for item in mapping["text_units"])
    assert view.coverage is not None
    compact_coverage = mapping["coverage"]
    assert compact_coverage["manifest_digest"] == content_digest(view.coverage)
    assert compact_coverage["selected"] == {
        "count": len(view.coverage.selected_unit_ids),
        "digest": content_digest(view.coverage.selected_unit_ids),
    }
    full_coverage = replace(
        view,
        hard_serialized_token_budget=None,
    ).to_mapping()["coverage"]
    assert full_coverage["selected_unit_ids"] == list(view.coverage.selected_unit_ids)
    assert full_coverage["serialized_identities"] == list(view.coverage.serialized_identities)


def test_partial_critical_element_remainder_is_not_complete_or_presented() -> None:
    text = "E" * 800
    snapshot, _ = _snapshot((text,))
    element = SourceElement(
        element_id=stable_id("element", snapshot.snapshot_id, "partial-critical"),
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="projected",
        kind="figure",
        exact_text=text,
        start_offset=0,
        end_offset=len(text),
        raw_payload_ref="objects/partial-critical",
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(element,)),
        text,
    )
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="do not settle a partial critical element",
        token_budget=120,
        critical_element_ids=(element.element_id,),
        rescue_level="section",
    )
    view = StageViewProjector().project(build, context)
    for _ in range(10):
        if view.source_elements:
            break
        assert view.continuation is not None
        view = StageViewProjector().project(
            build,
            replace(context, continuation=view.continuation),
        )

    assert view.source_elements
    assert view.continuation is not None
    assert view.continuation.element_frontier[0].element_id == element.element_id
    assert view.coverage is not None
    assert element.element_id in view.coverage.selected_element_ids
    assert element.element_id not in view.coverage.presented_element_ids
    assert not view.coverage.stage_input_complete
    omission = next(item for item in view.coverage.omitted if item.identity == element.element_id)
    assert omission.reason == "oversized_element_remainder"


def test_critical_source_plane_policy_change_rejects_stale_cursor() -> None:
    text = "A" * 240
    snapshot, _ = _snapshot((text,))
    element = SourceElement(
        element_id=stable_id("element", snapshot.snapshot_id, "cursor-element"),
        snapshot_id=snapshot.snapshot_id,
        schema_version="source-element.v1",
        ordinal=0,
        reading_order=0,
        projection_status="preserved",
        kind="figure",
        raw_payload_ref="objects/cursor-element",
    )
    build = ArticleGraphBuilder().build(
        replace(snapshot, source_elements=(element,)),
        text,
    )
    context = StageContext(
        stage=ReadingStage.MAINLINE,
        task_intent="bind cursor to critical Source Plane policy",
        token_budget=8,
        rescue_level="section",
    )
    first = StageViewProjector().project(build, context)
    assert first.continuation is not None

    with pytest.raises(ValueError, match="stale or incompatible"):
        StageViewProjector().project(
            build,
            replace(
                context,
                critical_element_ids=(element.element_id,),
                continuation=first.continuation,
            ),
        )
    with pytest.raises(ValueError, match="stale or incompatible"):
        StageViewProjector().project(
            build,
            replace(
                context,
                cited_element_ids=(element.element_id,),
                continuation=first.continuation,
            ),
        )

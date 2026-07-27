"""Complete persisted coverage accounting for a bounded StageView page."""

from __future__ import annotations

from collections.abc import Collection

from readwelt.article_graph import ArticleGraphBuildResult

from .models import (
    CoverageOmission,
    OmissionReason,
    StageContext,
    StageViewBlockingRecord,
    StageViewCoverageManifest,
)
from .paging import SelectedPage


def coverage_manifest(
    build: ArticleGraphBuildResult,
    context: StageContext,
    page: SelectedPage,
    eligible_unit_ids: frozenset[str],
    visited_unit_ids: tuple[str, ...],
    visited_range_ids: tuple[str, ...],
    visited_element_ids: tuple[str, ...],
    blocking_records: tuple[StageViewBlockingRecord, ...],
    completed_unit_ids: tuple[str, ...] = (),
    completed_range_ids: tuple[str, ...] = (),
    completed_element_ids: tuple[str, ...] = (),
) -> StageViewCoverageManifest:
    units = tuple(sorted(build.unitization.units, key=lambda item: (item.ordinal, item.unit_id)))
    source_ids = tuple(unit.unit_id for unit in units)
    selected_ids = tuple(dict.fromkeys(unit.unit_id for unit in page.selected))
    serialized_ids = tuple(unit.serialized_identity for unit in page.selected)
    ranges = tuple(
        sorted(
            build.unitization.source_ranges,
            key=lambda item: (item.start_offset, item.end_offset, item.range_id),
        )
    )
    elements = tuple(
        sorted(
            build.unitization.source_elements,
            key=lambda item: (item.reading_order, item.ordinal, item.element_id),
        )
    )
    source_range_ids = tuple(item.range_id for item in ranges)
    source_element_ids = tuple(item.element_id for item in elements)
    unknown_critical_ranges = set(context.critical_range_ids).difference(source_range_ids)
    if unknown_critical_ranges:
        raise ValueError(
            "critical_range_ids must resolve to Source Plane ranges: "
            + ", ".join(sorted(unknown_critical_ranges))
        )
    unknown_critical_elements = set(context.critical_element_ids).difference(source_element_ids)
    if unknown_critical_elements:
        raise ValueError(
            "critical_element_ids must resolve to Source Plane elements: "
            + ", ".join(sorted(unknown_critical_elements))
        )
    unknown_cited_ranges = set(context.cited_range_ids).difference(source_range_ids)
    if unknown_cited_ranges:
        raise ValueError(
            "cited_range_ids must resolve to Source Plane ranges: "
            + ", ".join(sorted(unknown_cited_ranges))
        )
    unknown_cited_elements = set(context.cited_element_ids).difference(source_element_ids)
    if unknown_cited_elements:
        raise ValueError(
            "cited_element_ids must resolve to Source Plane elements: "
            + ", ".join(sorted(unknown_cited_elements))
        )
    selected_range_ids = tuple(item.range_id for item in page.source_ranges)
    selected_element_ids = tuple(item.element_id for item in page.source_elements)
    anchors = anchor_to_unit(build)
    critical_ids = units_for_anchors(anchors, context.critical_anchor_ids)
    cited_ids = units_for_anchors(anchors, context.cited_anchor_ids)
    admitted = None if context.allowed_anchor_ids is None else frozenset(context.allowed_anchor_ids)
    presented: list[str] = []
    for unit in page.selected:
        if admitted is None or admitted.intersection(unit.anchor_ids):
            presented.append(unit.unit_id if unit.slice_id is None else unit.slice_id)
    remaining_by_id = {item.unit_id: item for item in page.remaining}
    remaining_range_ids = frozenset(page.remaining_range_ids)
    remaining_element_by_id = {item.element_id: item for item in page.remaining_elements}
    selected_by_id = {item.unit_id: item for item in page.selected}
    omission_by_id: dict[str, CoverageOmission] = {}
    for source_unit in units:
        selected = selected_by_id.get(source_unit.unit_id)
        if source_unit.unit_id in visited_unit_ids and selected is None:
            omission_by_id[source_unit.unit_id] = CoverageOmission(
                source_unit.unit_id,
                "visited_previous_page",
                object_type="unit",
            )
        elif source_unit.unit_id not in eligible_unit_ids:
            reason: OmissionReason = (
                "anchor_not_admitted"
                if context.allowed_anchor_ids is not None
                else "stage_policy_not_selected"
            )
            omission_by_id[source_unit.unit_id] = CoverageOmission(
                source_unit.unit_id,
                reason,
                object_type="unit",
            )
        elif source_unit.unit_id in remaining_by_id:
            position = remaining_by_id[source_unit.unit_id]
            remaining_reason: OmissionReason = (
                "oversized_unit_remainder" if position.start_offset > 0 else "continuation_pending"
            )
            omission_by_id[source_unit.unit_id] = CoverageOmission(
                source_unit.unit_id,
                remaining_reason,
                f"resume_at:{position.start_offset}" if position.start_offset > 0 else None,
                "unit",
            )
        elif selected is not None and selected.serialized_identity not in presented:
            omission_by_id[source_unit.unit_id] = CoverageOmission(
                source_unit.unit_id,
                "not_presented_to_provider",
                object_type="unit",
            )
        elif source_unit.unit_id not in selected_ids:
            omission_by_id[source_unit.unit_id] = CoverageOmission(
                source_unit.unit_id,
                "stage_policy_not_selected",
                object_type="unit",
            )
    for source_range in ranges:
        if source_range.range_id in visited_range_ids and (
            source_range.range_id not in selected_range_ids
        ):
            omission_by_id[source_range.range_id] = CoverageOmission(
                source_range.range_id,
                "visited_previous_page",
                object_type="range",
            )
        elif source_range.range_id in remaining_range_ids:
            omission_by_id[source_range.range_id] = CoverageOmission(
                source_range.range_id,
                "continuation_pending",
                object_type="range",
            )
        elif source_range.range_id not in selected_range_ids:
            omission_by_id[source_range.range_id] = CoverageOmission(
                source_range.range_id,
                "stage_policy_not_selected",
                object_type="range",
            )
    selected_element_by_id = {item.element_id: item for item in page.source_elements}
    for source_element in elements:
        selected_element = selected_element_by_id.get(source_element.element_id)
        if source_element.element_id in visited_element_ids and selected_element is None:
            omission_by_id[source_element.element_id] = CoverageOmission(
                source_element.element_id,
                "visited_previous_page",
                object_type="element",
            )
        elif source_element.element_id in remaining_element_by_id:
            element_position = remaining_element_by_id[source_element.element_id]
            omission_by_id[source_element.element_id] = CoverageOmission(
                source_element.element_id,
                (
                    "oversized_element_remainder"
                    if element_position.start_offset > 0
                    else "continuation_pending"
                ),
                (
                    f"resume_at:{element_position.start_offset}"
                    if element_position.start_offset > 0
                    else None
                ),
                "element",
            )
        elif selected_element is None:
            omission_by_id[source_element.element_id] = CoverageOmission(
                source_element.element_id,
                "stage_policy_not_selected",
                object_type="element",
            )
    for record in blocking_records:
        identity = record.source_unit_id or record.source_range_id or record.source_element_id
        if identity is not None:
            omission_by_id[identity] = CoverageOmission(
                identity,
                (
                    "hard_serialized_budget"
                    if record.reason.startswith("hard_serialized")
                    else (
                        "oversized_element_blocked"
                        if record.source_element_id is not None
                        else "oversized_unit_blocked"
                    )
                ),
                record.detail,
                (
                    "element"
                    if record.source_element_id is not None
                    else "range"
                    if record.source_range_id is not None
                    else "unit"
                ),
            )
    presented_set = set(presented)
    presented_range_ids = tuple(
        range_id for range_id in selected_range_ids if range_id not in remaining_range_ids
    )
    presented_element_ids = tuple(
        element_id
        for element_id in selected_element_ids
        if element_id not in remaining_element_by_id
    )
    stage_input_complete = (
        not blocking_records
        and set(critical_ids).issubset(presented_set)
        and set(context.critical_range_ids).issubset(presented_range_ids)
        and set(context.critical_element_ids).issubset(presented_element_ids)
    )
    source_complete = (
        build.unitization.coverage.has_complete_text_coverage
        and not build.unitization.coverage.uncovered
        and (
            build.unitization.coverage_manifest is None
            or build.unitization.coverage_manifest.has_complete_source_reachability
        )
    )
    return StageViewCoverageManifest(
        schema_version="stage-view-coverage.v2",
        source_unit_ids=source_ids,
        visited_unit_ids=visited_unit_ids,
        selected_unit_ids=selected_ids,
        serialized_identities=serialized_ids,
        presented_identities=tuple(presented),
        cited_unit_ids=cited_ids,
        critical_unit_ids=critical_ids,
        omitted=tuple(
            omission_by_id[identity]
            for identity in (*source_ids, *source_range_ids, *source_element_ids)
            if identity in omission_by_id
        ),
        source_complete=source_complete,
        stage_input_complete=stage_input_complete,
        critical_range_ids=context.critical_range_ids,
        critical_element_ids=context.critical_element_ids,
        cited_range_ids=context.cited_range_ids,
        cited_element_ids=context.cited_element_ids,
        source_range_ids=source_range_ids,
        visited_range_ids=visited_range_ids,
        selected_range_ids=selected_range_ids,
        source_element_ids=source_element_ids,
        visited_element_ids=visited_element_ids,
        selected_element_ids=selected_element_ids,
        presented_range_ids=presented_range_ids,
        presented_element_ids=presented_element_ids,
        completed_unit_ids=completed_unit_ids,
        completed_range_ids=completed_range_ids,
        completed_element_ids=completed_element_ids,
    )


def anchor_to_unit(build: ArticleGraphBuildResult) -> dict[str, str]:
    return {
        reference.anchor_id: unit.unit_id
        for unit in build.unitization.units
        for reference in unit.source_references
        if reference.anchor_id is not None
    }


def units_for_anchors(
    anchors: dict[str, str],
    anchor_ids: Collection[str],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            unit_id for anchor_id in anchor_ids if (unit_id := anchors.get(anchor_id)) is not None
        )
    )

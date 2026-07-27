"""Deterministic full-Source-Plane paging for bounded StageViews."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil

from readwelt.article_graph.digest import content_digest
from readwelt.article_ir import AnchoredTextUnit, SourceRangeRecord
from readwelt.domain.documents import SourceElement

from .models import (
    ElementTraversalPosition,
    StageView,
    StageViewBlockingRecord,
    StageViewSourceElement,
    StageViewSourceRange,
    StageViewTextUnit,
    TraversalPosition,
)


@dataclass(frozen=True, slots=True)
class SelectedPage:
    selected: tuple[StageViewTextUnit, ...]
    remaining: tuple[TraversalPosition, ...]
    considered_unit_ids: tuple[str, ...]
    completed_unit_ids: tuple[str, ...]
    used_tokens: int
    blocking_records: tuple[StageViewBlockingRecord, ...] = ()
    source_ranges: tuple[StageViewSourceRange, ...] = ()
    source_elements: tuple[StageViewSourceElement, ...] = ()
    remaining_range_ids: tuple[str, ...] = ()
    remaining_elements: tuple[ElementTraversalPosition, ...] = ()
    considered_range_ids: tuple[str, ...] = ()
    completed_range_ids: tuple[str, ...] = ()
    considered_element_ids: tuple[str, ...] = ()
    completed_element_ids: tuple[str, ...] = ()


def select_page(
    positions: tuple[TraversalPosition, ...],
    unit_by_id: dict[str, AnchoredTextUnit],
    token_budget: int,
    *,
    split_oversized_units: bool,
    range_ids: tuple[str, ...] = (),
    range_by_id: dict[str, SourceRangeRecord] | None = None,
    element_positions: tuple[ElementTraversalPosition, ...] = (),
    element_by_id: dict[str, SourceElement] | None = None,
    element_unit_ids: dict[str, tuple[str, ...]] | None = None,
) -> SelectedPage:
    selected: list[StageViewTextUnit] = []
    considered: list[str] = []
    completed: list[str] = []
    used_tokens = 0
    remaining: tuple[TraversalPosition, ...] = ()
    blocked: list[StageViewBlockingRecord] = []
    for index, position in enumerate(positions):
        unit = unit_by_id.get(position.unit_id)
        if unit is None:
            continue
        if position.start_offset >= len(unit.exact_text):
            completed.append(unit.unit_id)
            continue
        text = unit.exact_text[position.start_offset :]
        tokens = estimated_tokens(text)
        available = token_budget - used_tokens
        if tokens <= available:
            considered.append(unit.unit_id)
            selected.append(_view_unit(unit, text, position.start_offset))
            used_tokens += tokens
            completed.append(unit.unit_id)
            continue
        if available > 0 and split_oversized_units:
            considered.append(unit.unit_id)
            slice_length = min(len(text), available * 4)
            sliced = text[:slice_length]
            selected.append(_view_unit(unit, sliced, position.start_offset))
            used_tokens += estimated_tokens(sliced)
            remaining = (
                TraversalPosition(unit.unit_id, position.start_offset + slice_length),
                *positions[index + 1 :],
            )
            break
        if available <= 0 and used_tokens > 0:
            # The current unit has not been presented or settled.  Preserve it
            # as the first continuation position; skipping to index + 1 would
            # create a permanent ordinal gap at every page boundary.
            remaining = positions[index:]
            break
        considered.append(unit.unit_id)
        blocked.append(
            StageViewBlockingRecord(
                source_unit_id=unit.unit_id,
                reason="oversized_source_item_requires_split",
                estimated_tokens=tokens,
                budget=token_budget,
                detail=(
                    "splitting is disabled"
                    if not split_oversized_units
                    else "source text budget cannot admit a deterministic slice"
                ),
            )
        )
        remaining = positions[index + 1 :]
        break
    else:
        remaining = ()

    selected_ranges: list[StageViewSourceRange] = []
    considered_ranges: list[str] = []
    completed_ranges: list[str] = []
    remaining_ranges = range_ids
    if not remaining:
        (
            selected_ranges,
            considered_ranges,
            completed_ranges,
            remaining_ranges,
            used_tokens,
            range_blocks,
        ) = _select_ranges(
            range_ids,
            range_by_id or {},
            token_budget,
            used_tokens,
        )
        blocked.extend(range_blocks)

    selected_elements: list[StageViewSourceElement] = []
    considered_elements: list[str] = []
    completed_elements: list[str] = []
    remaining_elements = element_positions
    if not remaining and not remaining_ranges:
        (
            selected_elements,
            considered_elements,
            completed_elements,
            remaining_elements,
            used_tokens,
            element_blocks,
        ) = _select_elements(
            element_positions,
            element_by_id or {},
            element_unit_ids or {},
            token_budget,
            used_tokens,
            split_oversized=split_oversized_units,
        )
        blocked.extend(element_blocks)
    return SelectedPage(
        tuple(selected),
        remaining,
        tuple(dict.fromkeys(considered)),
        tuple(dict.fromkeys(completed)),
        used_tokens,
        tuple(blocked),
        tuple(selected_ranges),
        tuple(selected_elements),
        remaining_ranges,
        remaining_elements,
        tuple(dict.fromkeys(considered_ranges)),
        tuple(dict.fromkeys(completed_ranges)),
        tuple(dict.fromkeys(considered_elements)),
        tuple(dict.fromkeys(completed_elements)),
    )


def estimated_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4))


def unbounded_serialized_estimate(view: StageView) -> int:
    unbounded = replace(view, hard_serialized_token_budget=None)
    mapping = unbounded.to_mapping()
    value = mapping["estimated_serialized_tokens"]
    assert isinstance(value, int)
    return value


def _view_unit(
    unit: AnchoredTextUnit,
    text: str,
    start_offset: int,
) -> StageViewTextUnit:
    end_offset = start_offset + len(text)
    is_slice = start_offset != 0 or end_offset != len(unit.exact_text)
    slice_id = (
        content_digest(
            {
                "unit_id": unit.unit_id,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "text": text,
            }
        )
        if is_slice
        else None
    )
    return StageViewTextUnit(
        unit.unit_id,
        unit.kind,
        text,
        tuple(
            reference.anchor_id
            for reference in unit.source_references
            if reference.anchor_id is not None
        ),
        unit.ordinal,
        estimated_tokens(text),
        slice_id,
        start_offset,
        end_offset,
    )


def _select_ranges(
    range_ids: tuple[str, ...],
    range_by_id: dict[str, SourceRangeRecord],
    token_budget: int,
    used_tokens: int,
) -> tuple[
    list[StageViewSourceRange],
    list[str],
    list[str],
    tuple[str, ...],
    int,
    list[StageViewBlockingRecord],
]:
    selected: list[StageViewSourceRange] = []
    considered: list[str] = []
    completed: list[str] = []
    blocked: list[StageViewBlockingRecord] = []
    remaining: tuple[str, ...] = ()
    for index, range_id in enumerate(range_ids):
        source_range = range_by_id.get(range_id)
        if source_range is None:
            continue
        available = token_budget - used_tokens
        if available <= 0 and selected:
            remaining = range_ids[index:]
            break
        considered.append(range_id)
        if available <= 0:
            blocked.append(
                StageViewBlockingRecord(
                    source_unit_id=None,
                    source_range_id=range_id,
                    reason="source_range_metadata_exceeds_page_budget",
                    estimated_tokens=1,
                    budget=token_budget,
                    detail="compact reachability metadata could not be admitted",
                )
            )
            completed.append(range_id)
            remaining = range_ids[index + 1 :]
            break
        selected.append(_view_range(source_range))
        used_tokens += 1
        completed.append(range_id)
    return selected, considered, completed, remaining, used_tokens, blocked


def _select_elements(
    positions: tuple[ElementTraversalPosition, ...],
    element_by_id: dict[str, SourceElement],
    element_unit_ids: dict[str, tuple[str, ...]],
    token_budget: int,
    used_tokens: int,
    *,
    split_oversized: bool,
) -> tuple[
    list[StageViewSourceElement],
    list[str],
    list[str],
    tuple[ElementTraversalPosition, ...],
    int,
    list[StageViewBlockingRecord],
]:
    selected: list[StageViewSourceElement] = []
    considered: list[str] = []
    completed: list[str] = []
    blocked: list[StageViewBlockingRecord] = []
    remaining: tuple[ElementTraversalPosition, ...] = ()
    for index, position in enumerate(positions):
        element = element_by_id.get(position.element_id)
        if element is None:
            continue
        available = token_budget - used_tokens
        text = (element.exact_text or "")[position.start_offset :]
        metadata_tokens = _element_metadata_tokens(element)
        required = metadata_tokens + (estimated_tokens(text) if text else 0)
        if required <= available:
            considered.append(element.element_id)
            selected.append(
                _view_element(
                    element,
                    text or None,
                    position.start_offset,
                    element_unit_ids.get(element.element_id, ()),
                )
            )
            used_tokens += required
            completed.append(element.element_id)
            continue
        if used_tokens > 0 and (
            required <= token_budget
            or (bool(text) and split_oversized and token_budget > metadata_tokens)
        ):
            remaining = positions[index:]
            break
        if available > metadata_tokens and text and split_oversized:
            considered.append(element.element_id)
            slice_length = min(
                len(text),
                max(1, available - metadata_tokens) * 4,
            )
            sliced = text[:slice_length]
            selected.append(
                _view_element(
                    element,
                    sliced,
                    position.start_offset,
                    element_unit_ids.get(element.element_id, ()),
                )
            )
            used_tokens += metadata_tokens + estimated_tokens(sliced)
            remaining = (
                ElementTraversalPosition(
                    element.element_id,
                    position.start_offset + slice_length,
                ),
                *positions[index + 1 :],
            )
            break
        if available <= 0 and used_tokens > 0:
            remaining = positions[index:]
            break
        considered.append(element.element_id)
        blocked.append(
            StageViewBlockingRecord(
                source_unit_id=None,
                source_element_id=element.element_id,
                reason="oversized_source_element_requires_split",
                estimated_tokens=required,
                budget=token_budget,
                detail=(
                    "splitting is disabled"
                    if text and not split_oversized
                    else "element metadata cannot fit the current source budget"
                ),
            )
        )
        completed.append(element.element_id)
        remaining = positions[index + 1 :]
        break
    return selected, considered, completed, remaining, used_tokens, blocked


def _view_range(source_range: SourceRangeRecord) -> StageViewSourceRange:
    return StageViewSourceRange(
        range_id=source_range.range_id,
        kind=source_range.kind,
        start_offset=source_range.start_offset,
        end_offset=source_range.end_offset,
        content_hash=source_range.content_hash,
        unit_ids=source_range.unit_ids,
        unit_ids_digest=content_digest(source_range.unit_ids),
        reason=source_range.reason,
        estimated_tokens=1,
    )


def _view_element(
    element: SourceElement,
    text: str | None,
    start_offset: int,
    source_unit_ids: tuple[str, ...],
) -> StageViewSourceElement:
    source_text = element.exact_text or ""
    end_offset = start_offset + len(text or "")
    is_slice = bool(source_text) and (start_offset != 0 or end_offset != len(source_text))
    slice_id = (
        content_digest(
            {
                "element_id": element.element_id,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "text": text,
            }
        )
        if is_slice
        else None
    )
    return StageViewSourceElement(
        element_id=element.element_id,
        kind=element.kind,
        content_layer=element.content_layer,
        projection_status=element.projection_status,
        ordinal=element.ordinal,
        reading_order=element.reading_order,
        page=element.page,
        bounding_box=element.bounding_box,
        native_reference=element.native_reference,
        raw_payload_ref=element.raw_payload_ref,
        parent_element_id=element.parent_element_id,
        previous_element_id=element.previous_element_id,
        next_element_id=element.next_element_id,
        child_count=len(element.child_element_ids),
        child_ids_digest=content_digest(element.child_element_ids),
        structural_relation_count=len(element.structural_relations),
        structural_relations_digest=content_digest(element.structural_relations),
        heading_trail=element.heading_trail,
        text=text,
        estimated_tokens=_element_metadata_tokens(element)
        + (estimated_tokens(text) if text else 0),
        child_element_ids=element.child_element_ids,
        structural_relations=element.structural_relations,
        source_unit_ids=source_unit_ids,
        slice_id=slice_id,
        slice_start=start_offset,
        slice_end=end_offset if text is not None else None,
    )


def _element_metadata_tokens(element: SourceElement) -> int:
    """A stable admission estimate; final serialized settlement remains authoritative."""

    variable = sum(
        len(value)
        for value in (
            element.element_id,
            element.kind or "",
            element.content_layer or "",
            element.projection_status,
            element.native_reference or "",
            element.raw_payload_ref or "",
            element.parent_element_id or "",
            element.previous_element_id or "",
            element.next_element_id or "",
            *element.child_element_ids,
            *(value for relation in element.structural_relations for value in relation),
            *element.heading_trail,
        )
    )
    return max(8, ceil(variable / 4))

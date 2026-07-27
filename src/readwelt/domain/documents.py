"""Immutable source-document snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from readwelt.domain.spans import SpanAnchor

SourceElementProjectionStatus = Literal["projected", "preserved", "unresolved"]


@dataclass(frozen=True, slots=True)
class DocumentSection:
    section_id: str
    title: str | None
    start_offset: int
    end_offset: int
    anchor: SpanAnchor
    kind: str | None = None
    parent_element_id: str | None = None
    heading_trail: tuple[str, ...] = ()
    element_id: str | None = None
    page: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        if self.start_offset < 0 or self.end_offset < self.start_offset:
            raise ValueError("invalid section offsets")
        if self.page is not None and self.page < 1:
            raise ValueError("section page must be positive")
        if self.bounding_box is not None and self.page is None:
            raise ValueError("section bounding_box requires a page")


@dataclass(frozen=True, slots=True)
class SourceElement:
    """One backend-exposed source element preserved independently of paragraphs."""

    element_id: str
    snapshot_id: str
    schema_version: str
    ordinal: int
    reading_order: int
    projection_status: SourceElementProjectionStatus
    kind: str | None = None
    content_layer: str | None = None
    exact_text: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    parent_element_id: str | None = None
    child_element_ids: tuple[str, ...] = ()
    previous_element_id: str | None = None
    next_element_id: str | None = None
    structural_relations: tuple[tuple[str, str], ...] = ()
    heading_trail: tuple[str, ...] = ()
    page: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    native_reference: str | None = None
    raw_payload_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.element_id or not self.snapshot_id:
            raise ValueError("source element identity fields are required")
        if self.schema_version != "source-element.v1":
            raise ValueError(f"unsupported source element schema: {self.schema_version}")
        if self.ordinal < 0:
            raise ValueError("source element ordinal cannot be negative")
        if self.reading_order < 0:
            raise ValueError("source element reading_order cannot be negative")
        has_start = self.start_offset is not None
        has_end = self.end_offset is not None
        if has_start != has_end:
            raise ValueError("source element range requires both offsets")
        if has_start:
            assert self.start_offset is not None
            assert self.end_offset is not None
            if self.start_offset < 0 or self.end_offset < self.start_offset:
                raise ValueError("invalid source element range")
            if self.exact_text is not None and (
                self.end_offset - self.start_offset != len(self.exact_text)
            ):
                raise ValueError("source element range must span exact_text")
        if self.page is not None and self.page < 1:
            raise ValueError("source element page must be positive")
        if self.bounding_box is not None and self.page is None:
            raise ValueError("source element bounding_box requires a page")
        if self.raw_payload_ref is not None and not self.raw_payload_ref.startswith("objects/"):
            raise ValueError("source element raw_payload_ref must be project-relative")
        if any(
            not relation.strip() or not target_id
            for relation, target_id in self.structural_relations
        ):
            raise ValueError("source element structural relations require type and target")


@dataclass(frozen=True, slots=True)
class SourceDocumentSnapshot:
    snapshot_id: str
    document_id: str
    schema_version: str
    source_kind: str
    source_locator: str
    content_digest: str
    captured_at: datetime
    language: str
    normalized_text_ref: str
    sections: tuple[DocumentSection, ...]
    source_elements: tuple[SourceElement, ...] = ()
    attachments: tuple[str, ...] = ()
    parse_findings: tuple[str, ...] = ()
    published_at: datetime | None = None
    author: str | None = None
    title: str | None = None
    parent_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "1":
            raise ValueError(f"unsupported snapshot schema: {self.schema_version}")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")
        if not self.normalized_text_ref.startswith("objects/"):
            raise ValueError("normalized_text_ref must be project-relative")
        if any(section.anchor.snapshot_id != self.snapshot_id for section in self.sections):
            raise ValueError("every section anchor must refer to this snapshot")
        if any(element.snapshot_id != self.snapshot_id for element in self.source_elements):
            raise ValueError("every source element must refer to this snapshot")
        element_ids = {element.element_id for element in self.source_elements}
        if len(element_ids) != len(self.source_elements):
            raise ValueError("source element ids must be unique")
        if any(
            element.parent_element_id is not None and element.parent_element_id not in element_ids
            for element in self.source_elements
        ):
            raise ValueError("source element parent must resolve within the snapshot")
        if any(
            child_id not in element_ids
            for element in self.source_elements
            for child_id in element.child_element_ids
        ):
            raise ValueError("source element children must resolve within the snapshot")
        if any(
            neighbor_id is not None and neighbor_id not in element_ids
            for element in self.source_elements
            for neighbor_id in (element.previous_element_id, element.next_element_id)
        ):
            raise ValueError("source element neighbors must resolve within the snapshot")
        if any(
            target_id not in element_ids
            for element in self.source_elements
            for _, target_id in element.structural_relations
        ):
            raise ValueError("source element structural relations must resolve within the snapshot")
        by_id = {element.element_id: element for element in self.source_elements}
        for element in self.source_elements:
            if element.parent_element_id is not None:
                parent = by_id[element.parent_element_id]
                if element.element_id not in parent.child_element_ids:
                    raise ValueError("source element parent/children links disagree")
            for child_id in element.child_element_ids:
                if by_id[child_id].parent_element_id != element.element_id:
                    raise ValueError("source element children/parent links disagree")
            if element.previous_element_id is not None:
                previous = by_id[element.previous_element_id]
                if previous.next_element_id != element.element_id:
                    raise ValueError("source element previous/next links disagree")
            if element.next_element_id is not None:
                following = by_id[element.next_element_id]
                if following.previous_element_id != element.element_id:
                    raise ValueError("source element next/previous links disagree")
        reading_orders = [element.reading_order for element in self.source_elements]
        if len(reading_orders) != len(set(reading_orders)):
            raise ValueError("source element reading order must be unique")
        _validate_source_element_topology(self.source_elements, by_id)


def _validate_source_element_topology(
    elements: tuple[SourceElement, ...],
    by_id: dict[str, SourceElement],
) -> None:
    """Reject closed-but-untraversable Source Plane structures."""

    _validate_acyclic_parent_hierarchy(elements, by_id)
    _validate_acyclic_neighbor_links(elements, by_id)
    roots = tuple(element for element in elements if element.kind == "source_document")
    if not roots:
        return
    if len(roots) != 1:
        raise ValueError("Source Plane requires exactly one source_document root")
    root = roots[0]
    if root.parent_element_id is not None:
        raise ValueError("source_document root cannot have a parent")
    reachable = _hierarchy_reachable(root.element_id, by_id)
    if reachable != set(by_id):
        raise ValueError("every source element must be reachable from source_document root")
    ordered = tuple(sorted(elements, key=lambda item: (item.reading_order, item.element_id)))
    if ordered and ordered[0].element_id != root.element_id:
        raise ValueError("source_document root must begin the reading-order chain")
    for index, element in enumerate(ordered):
        expected_previous = ordered[index - 1].element_id if index else None
        expected_next = ordered[index + 1].element_id if index + 1 < len(ordered) else None
        if (
            element.previous_element_id != expected_previous
            or element.next_element_id != expected_next
        ):
            raise ValueError("source element neighbor chain must cover reading order exactly")


def _validate_acyclic_parent_hierarchy(
    elements: tuple[SourceElement, ...],
    by_id: dict[str, SourceElement],
) -> None:
    for element in elements:
        seen: set[str] = set()
        current: SourceElement | None = element
        while current is not None:
            if current.element_id in seen:
                raise ValueError("source element parent hierarchy cannot contain cycles")
            seen.add(current.element_id)
            current = (
                by_id[current.parent_element_id] if current.parent_element_id is not None else None
            )


def _validate_acyclic_neighbor_links(
    elements: tuple[SourceElement, ...],
    by_id: dict[str, SourceElement],
) -> None:
    for element in elements:
        seen: set[str] = set()
        current: SourceElement | None = element
        while current is not None:
            if current.element_id in seen:
                raise ValueError("source element neighbor chain cannot contain cycles")
            seen.add(current.element_id)
            current = (
                by_id[current.next_element_id] if current.next_element_id is not None else None
            )


def _hierarchy_reachable(
    root_id: str,
    by_id: dict[str, SourceElement],
) -> set[str]:
    reachable: set[str] = set()
    frontier = [root_id]
    while frontier:
        element_id = frontier.pop()
        if element_id in reachable:
            continue
        reachable.add(element_id)
        frontier.extend(by_id[element_id].child_element_ids)
    return reachable

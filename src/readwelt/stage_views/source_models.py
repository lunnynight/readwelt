"""Budgeted Source Plane records presented through a StageView."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.article_graph.digest import content_digest


@dataclass(frozen=True, slots=True)
class StageViewTextUnit:
    unit_id: str
    kind: str
    text: str
    anchor_ids: tuple[str, ...]
    ordinal: int
    estimated_tokens: int
    slice_id: str | None = None
    slice_start: int = 0
    slice_end: int | None = None

    def __post_init__(self) -> None:
        end = len(self.text) if self.slice_end is None else self.slice_end
        if self.slice_start < 0 or end < self.slice_start:
            raise ValueError("invalid StageView text-unit slice")
        if end - self.slice_start != len(self.text):
            raise ValueError("StageView slice range must span its exact text")
        if self.slice_id is None and (self.slice_start != 0 or end != len(self.text)):
            raise ValueError("partial source unit requires a slice_id")

    @property
    def serialized_identity(self) -> str:
        return self.slice_id or self.unit_id


@dataclass(frozen=True, slots=True)
class StageViewSourceRange:
    """Compact provider-visible reachability record for one normalized range."""

    range_id: str
    kind: str
    start_offset: int
    end_offset: int
    content_hash: str
    unit_ids: tuple[str, ...]
    unit_ids_digest: str
    reason: str | None
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class StageViewSourceElement:
    """Budgeted Source Plane element metadata and optional exact-text slice."""

    element_id: str
    kind: str | None
    content_layer: str | None
    projection_status: str
    ordinal: int
    reading_order: int
    page: int | None
    bounding_box: tuple[float, float, float, float] | None
    native_reference: str | None
    raw_payload_ref: str | None
    parent_element_id: str | None
    previous_element_id: str | None
    next_element_id: str | None
    child_count: int
    child_ids_digest: str
    structural_relation_count: int
    structural_relations_digest: str
    heading_trail: tuple[str, ...]
    text: str | None
    estimated_tokens: int
    child_element_ids: tuple[str, ...] = ()
    structural_relations: tuple[tuple[str, str], ...] = ()
    source_unit_ids: tuple[str, ...] = ()
    slice_id: str | None = None
    slice_start: int = 0
    slice_end: int | None = None

    def __post_init__(self) -> None:
        text = self.text or ""
        end = len(text) if self.slice_end is None else self.slice_end
        if self.slice_start < 0 or end < self.slice_start:
            raise ValueError("invalid StageView source-element slice")
        if self.text is not None and end - self.slice_start != len(text):
            raise ValueError("source-element slice range must span its exact text")
        if self.child_count != len(self.child_element_ids):
            raise ValueError("source-element child count does not match exposed ids")
        if self.child_ids_digest != content_digest(self.child_element_ids):
            raise ValueError("source-element child ids digest mismatch")
        if self.structural_relation_count != len(self.structural_relations):
            raise ValueError(
                "source-element structural relation count does not match exposed relations"
            )
        if self.structural_relations_digest != content_digest(self.structural_relations):
            raise ValueError("source-element structural relations digest mismatch")

    @property
    def serialized_identity(self) -> str:
        return self.slice_id or self.element_id

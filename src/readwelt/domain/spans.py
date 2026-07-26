"""Anchors that preserve both source offsets and nearby text."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.domain.ids import stable_id


@dataclass(frozen=True, slots=True)
class SpanAnchor:
    anchor_id: str
    snapshot_id: str
    section_id: str
    start_offset: int
    end_offset: int
    exact_text: str
    prefix: str = ""
    suffix: str = ""
    page: int | None = None

    def __post_init__(self) -> None:
        if self.start_offset < 0:
            raise ValueError("start_offset cannot be negative")
        if self.end_offset < self.start_offset:
            raise ValueError("end_offset cannot precede start_offset")
        if self.end_offset - self.start_offset != len(self.exact_text):
            raise ValueError("anchor offsets must span exact_text")
        if self.page is not None and self.page < 1:
            raise ValueError("page must be positive")

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        section_id: str,
        text: str,
        start_offset: int,
        end_offset: int,
        context_chars: int = 32,
        page: int | None = None,
    ) -> SpanAnchor:
        if end_offset > len(text):
            raise ValueError("end_offset exceeds source text")
        exact_text = text[start_offset:end_offset]
        prefix = text[max(0, start_offset - context_chars) : start_offset]
        suffix = text[end_offset : end_offset + context_chars]
        anchor_id = stable_id(
            "anchor",
            snapshot_id,
            section_id,
            str(start_offset),
            str(end_offset),
            exact_text,
        )
        return cls(
            anchor_id=anchor_id,
            snapshot_id=snapshot_id,
            section_id=section_id,
            start_offset=start_offset,
            end_offset=end_offset,
            exact_text=exact_text,
            prefix=prefix,
            suffix=suffix,
            page=page,
        )

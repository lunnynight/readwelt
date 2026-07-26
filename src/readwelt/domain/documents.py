"""Immutable source-document snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from readwelt.domain.spans import SpanAnchor


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

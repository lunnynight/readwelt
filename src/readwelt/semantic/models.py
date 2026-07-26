"""Immutable artifacts produced by deterministic semantic preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from readwelt.domain.spans import SpanAnchor


@dataclass(frozen=True, slots=True)
class SegmentStatistics:
    character_count: int
    non_whitespace_character_count: int
    token_count: int
    sentence_boundary_count: int
    digit_count: int


@dataclass(frozen=True, slots=True)
class SemanticSegment:
    segment_id: str
    anchor: SpanAnchor
    tokens: tuple[str, ...]
    statistics: SegmentStatistics
    exact_digest: str
    exact_duplicate_of: str | None
    near_duplicate_candidate_ids: tuple[str, ...]
    embedding_artifact: str | None = None


@dataclass(frozen=True, slots=True)
class UncoveredRange:
    start_offset: int
    end_offset: int
    reason: str


@dataclass(frozen=True, slots=True)
class CoverageManifest:
    indexed_anchor_ids: tuple[str, ...]
    orientation_anchor_ids: tuple[str, ...]
    section_anchor_ids: tuple[tuple[str, tuple[str, ...]], ...]
    unanchored_non_whitespace_ranges: tuple[UncoveredRange, ...]
    source_character_count: int
    anchored_character_count: int

    @property
    def full_source_covered(self) -> bool:
        return not self.unanchored_non_whitespace_ranges


@dataclass(frozen=True, slots=True)
class EmbeddingDescriptor:
    provider: str
    model: str
    revision: str
    dimensions: int
    artifact_ref: str


@dataclass(frozen=True, slots=True)
class SemanticAtlas:
    schema_version: str
    snapshot_id: str
    tokenizer_version: str
    lexical_backend: str
    segments: tuple[SemanticSegment, ...]
    coverage: CoverageManifest
    embedding: EmbeddingDescriptor | None
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "1":
            raise ValueError(f"unsupported semantic atlas schema: {self.schema_version}")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")


@dataclass(frozen=True, slots=True)
class OmittedEvidence:
    anchor_id: str
    section_id: str
    reason: str
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class SemanticEvidencePacket:
    schema_version: str
    snapshot_id: str
    purpose: str
    anchors: tuple[SpanAnchor, ...]
    retrieval_queries: tuple[str, ...]
    omitted: tuple[OmittedEvidence, ...]
    covered_section_ids: tuple[str, ...]
    omitted_section_ids: tuple[str, ...]
    token_budget: int
    estimated_tokens: int
    coverage_complete: bool

    def to_mapping(self) -> dict[str, Any]:
        """Return a stable primitive mapping suitable for stage/provider boundaries."""
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "purpose": self.purpose,
            "anchor_ids": [anchor.anchor_id for anchor in self.anchors],
            "anchors": [
                {
                    "anchor_id": anchor.anchor_id,
                    "snapshot_id": anchor.snapshot_id,
                    "section_id": anchor.section_id,
                    "start_offset": anchor.start_offset,
                    "end_offset": anchor.end_offset,
                    "exact_text": anchor.exact_text,
                    "prefix": anchor.prefix,
                    "suffix": anchor.suffix,
                    "page": anchor.page,
                }
                for anchor in self.anchors
            ],
            "retrieval_queries": list(self.retrieval_queries),
            "omitted": [
                {
                    "anchor_id": item.anchor_id,
                    "section_id": item.section_id,
                    "reason": item.reason,
                    "estimated_tokens": item.estimated_tokens,
                }
                for item in self.omitted
            ],
            "covered_section_ids": list(self.covered_section_ids),
            "omitted_section_ids": list(self.omitted_section_ids),
            "token_budget": self.token_budget,
            "estimated_tokens": self.estimated_tokens,
            "coverage_complete": self.coverage_complete,
        }

    def to_stage_packet(self, run_id: str) -> object:
        """Convert to the six-stage domain packet without making it a semantic dependency."""
        from readwelt.domain.reading import EvidencePacket

        return EvidencePacket(
            run_id=run_id,
            anchors=self.anchors,
            retrieval_queries=self.retrieval_queries,
            omitted_sections=self.omitted_section_ids,
            omitted_anchor_ids=tuple(item.anchor_id for item in self.omitted),
            coverage_complete=self.coverage_complete,
            token_budget=self.token_budget,
        )

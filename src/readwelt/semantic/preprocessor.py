"""Deterministic semantic atlas construction over existing snapshot anchors."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from readwelt import _core
from readwelt.domain.documents import SourceDocumentSnapshot
from readwelt.domain.ids import stable_id
from readwelt.domain.spans import SpanAnchor
from readwelt.semantic.lexical import BM25Index
from readwelt.semantic.models import (
    CoverageManifest,
    SegmentStatistics,
    SemanticAtlas,
    SemanticSegment,
    UncoveredRange,
)
from readwelt.semantic.protocol import EmbeddingAdapter
from readwelt.semantic.tokenization import TOKENIZER_VERSION


class SemanticPreprocessor:
    def __init__(
        self,
        *,
        embedding_adapter: EmbeddingAdapter | None = None,
        near_duplicate_threshold: float = 0.82,
    ) -> None:
        if not 0.0 <= near_duplicate_threshold <= 1.0:
            raise ValueError("near_duplicate_threshold must be between zero and one")
        self._embedding_adapter = embedding_adapter
        self._near_duplicate_threshold = near_duplicate_threshold

    def prepare(
        self,
        snapshot: SourceDocumentSnapshot,
        normalized_text: str,
    ) -> SemanticAtlas:
        """Reuse snapshot/Rust anchors exactly; reject text or offset drift."""
        anchors = tuple(section.anchor for section in snapshot.sections)
        self._validate_anchors(snapshot.snapshot_id, anchors, normalized_text)
        analyses = _core.semantic_analyze(
            [anchor.exact_text for anchor in anchors],
            self._near_duplicate_threshold,
        )
        segments: list[SemanticSegment] = []
        for anchor, analysis in zip(anchors, analyses, strict=True):
            (
                tokens,
                character_count,
                non_whitespace_character_count,
                token_count,
                sentence_boundary_count,
                digest,
                exact_duplicate_ordinal,
                near_duplicate_ordinals,
            ) = analysis
            exact_duplicate_of = (
                anchors[exact_duplicate_ordinal].anchor_id
                if exact_duplicate_ordinal is not None
                else None
            )
            near_ids = tuple(anchors[prior].anchor_id for prior in near_duplicate_ordinals)
            segments.append(
                SemanticSegment(
                    segment_id=stable_id("segment", snapshot.snapshot_id, anchor.anchor_id),
                    anchor=anchor,
                    tokens=tuple(tokens),
                    statistics=SegmentStatistics(
                        character_count=character_count,
                        non_whitespace_character_count=non_whitespace_character_count,
                        token_count=token_count,
                        sentence_boundary_count=sentence_boundary_count,
                        digit_count=sum(char.isdigit() for char in anchor.exact_text),
                    ),
                    exact_digest=f"sha256:{digest}",
                    exact_duplicate_of=exact_duplicate_of,
                    near_duplicate_candidate_ids=near_ids,
                )
            )
        segment_tuple = tuple(segments)
        embedding = (
            self._embedding_adapter.encode(segment_tuple) if self._embedding_adapter else None
        )
        coverage = _coverage(snapshot, normalized_text)
        payload = {
            "snapshot_id": snapshot.snapshot_id,
            "tokenizer": TOKENIZER_VERSION,
            "lexical": BM25Index.backend,
            "segments": [
                {
                    "id": segment.segment_id,
                    "anchor": segment.anchor.anchor_id,
                    "digest": segment.exact_digest,
                    "tokens": segment.tokens,
                    "duplicate": segment.exact_duplicate_of,
                    "near": segment.near_duplicate_candidate_ids,
                }
                for segment in segment_tuple
            ],
            "coverage": [
                (item.start_offset, item.end_offset, item.reason)
                for item in coverage.unanchored_non_whitespace_ranges
            ],
            "embedding": embedding,
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()
        return SemanticAtlas(
            schema_version="1",
            snapshot_id=snapshot.snapshot_id,
            tokenizer_version=TOKENIZER_VERSION,
            lexical_backend=BM25Index.backend,
            segments=segment_tuple,
            coverage=coverage,
            embedding=embedding,
            content_digest=f"sha256:{digest}",
        )

    @staticmethod
    def _validate_anchors(
        snapshot_id: str,
        anchors: tuple[SpanAnchor, ...],
        normalized_text: str,
    ) -> None:
        for anchor in anchors:
            if anchor.snapshot_id != snapshot_id:
                raise ValueError("anchor belongs to another snapshot")
            start = anchor.start_offset
            end = anchor.end_offset
            if end > len(normalized_text):
                raise ValueError("anchor exceeds normalized text")
            if normalized_text[start:end] != anchor.exact_text:
                raise ValueError("normalized text does not match snapshot anchors")


def _coverage(
    snapshot: SourceDocumentSnapshot,
    normalized_text: str,
) -> CoverageManifest:
    by_section: dict[str, list[str]] = defaultdict(list)
    ranges: list[tuple[int, int]] = []
    for section in snapshot.sections:
        anchor = section.anchor
        ranges.append((anchor.start_offset, anchor.end_offset))
        by_section[section.section_id].append(anchor.anchor_id)
    uncovered_ranges, anchored_character_count = _core.coverage_intervals(normalized_text, ranges)
    uncovered = tuple(
        UncoveredRange(start, end, "no_snapshot_anchor") for start, end in uncovered_ranges
    )
    indexed = tuple(section.anchor.anchor_id for section in snapshot.sections)
    return CoverageManifest(
        indexed_anchor_ids=indexed,
        orientation_anchor_ids=tuple(ids[0] for ids in by_section.values() if ids),
        section_anchor_ids=tuple(
            (section_id, tuple(ids)) for section_id, ids in by_section.items()
        ),
        unanchored_non_whitespace_ranges=uncovered,
        source_character_count=len(normalized_text),
        anchored_character_count=anchored_character_count,
    )

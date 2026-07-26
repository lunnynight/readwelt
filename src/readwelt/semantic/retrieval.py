"""Stage-aware hybrid retrieval with no database requirement."""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from readwelt.domain.reading import LedgerDecision, ReadingClaim, ReadingStage, RetrievalHit
from readwelt.semantic.lexical import BM25Index
from readwelt.semantic.models import (
    OmittedEvidence,
    SemanticAtlas,
    SemanticEvidencePacket,
)
from readwelt.semantic.protocol import DenseEncoder
from readwelt.semantic.tokenization import tokenize

_STAGE_QUERIES: dict[ReadingStage, str] = {
    ReadingStage.MAINLINE: "核心问题 主要主张 推理链 内部证据 结论",
    ReadingStage.STRUCTURE: "论证结构 前提 证据 例子 反驳 限定 结论",
    ReadingStage.DECOMPRESSION: "前置知识 压缩概念 外部条件 验证目标",
    ReadingStage.AUTHOR_MODEL: "作者假设 问题意识 方法选择 竞争解释",
    ReadingStage.BOUNDARIES: "适用边界 隐含假设 反例 替代解释 缺失证据",
    ReadingStage.TRANSFER: "不变机制 迁移条件 不可迁移因素 失败测试",
}


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    """The retrieval equivalent of a StageRequest: frozen, bounded and attributable."""

    stage: ReadingStage
    queries: tuple[str, ...]
    token_budget: int
    source_claim_ids: tuple[str, ...] = ()
    required_anchor_ids: tuple[str, ...] = ()
    policy_version: str = "stage-retrieval-v1"

    def __post_init__(self) -> None:
        if self.token_budget < 0:
            raise ValueError("token_budget cannot be negative")
        if not tuple(query for query in self.queries if query.strip()):
            raise ValueError("retrieval plan requires at least one non-empty query")
        if len(set(self.source_claim_ids)) != len(self.source_claim_ids):
            raise ValueError("source claim ids must be unique")
        if len(set(self.required_anchor_ids)) != len(self.required_anchor_ids):
            raise ValueError("required anchor ids must be unique")


def build_stage_retrieval_plan(
    stage: ReadingStage,
    *,
    purpose: str,
    token_budget: int,
    upstream_claims: Sequence[ReadingClaim] = (),
    max_claim_queries: int = 8,
) -> RetrievalPlan:
    """Build deterministic stage queries from user intent and settled upstream claims."""
    accepted = tuple(
        claim
        for claim in upstream_claims
        if claim.decision in {LedgerDecision.ACCEPTED, LedgerDecision.QUALIFIED}
    )
    claim_queries = tuple(claim.text.strip() for claim in accepted[:max_claim_queries])
    queries = tuple(
        dict.fromkeys(
            query for query in (purpose.strip(), _STAGE_QUERIES[stage], *claim_queries) if query
        )
    )
    return RetrievalPlan(
        stage=stage,
        queries=queries,
        token_budget=token_budget,
        source_claim_ids=tuple(claim.claim_id for claim in accepted[:max_claim_queries]),
        required_anchor_ids=tuple(
            dict.fromkeys(
                anchor_id
                for claim in accepted[:max_claim_queries]
                for anchor_id in claim.anchor_ids
            )
        ),
    )


class HybridRetriever:
    """Fuse Rust BM25 and optional dense similarity, then enforce section coverage."""

    def __init__(
        self,
        *,
        dense_encoder: DenseEncoder | None = None,
        lexical_weight: float = 1.0,
        dense_weight: float = 1.0,
        rrf_k: int = 60,
        cache_dir: str | Path | None = None,
    ) -> None:
        if lexical_weight <= 0 or dense_weight <= 0:
            raise ValueError("retrieval weights must be positive")
        if rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        self._dense_encoder = dense_encoder
        self._lexical_weight = lexical_weight
        self._dense_weight = dense_weight
        self._rrf_k = rrf_k
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._document_cache: dict[str, tuple[tuple[float, ...], ...]] = {}

    def retrieve(
        self,
        atlas: SemanticAtlas,
        plan: RetrievalPlan,
    ) -> SemanticEvidencePacket:
        indexed_anchor_ids = set(atlas.coverage.indexed_anchor_ids)
        unknown_required = set(plan.required_anchor_ids) - indexed_anchor_ids
        if unknown_required:
            raise ValueError(
                f"retrieval plan requires unknown anchor ids: {sorted(unknown_required)}"
            )
        queries = tuple(query for query in plan.queries if query.strip())
        lexical_ranking = BM25Index(tuple(segment.tokens for segment in atlas.segments)).rank(
            tokenize(" ".join(queries))
        )
        lexical_rank = {ordinal: rank for rank, (ordinal, _) in enumerate(lexical_ranking, 1)}
        lexical_score = dict(lexical_ranking)

        dense_ranking: tuple[tuple[int, float], ...] = ()
        if self._dense_encoder is not None and atlas.segments:
            dense_ranking = self._dense_ranking(atlas, queries)
        dense_rank = {ordinal: rank for rank, (ordinal, _) in enumerate(dense_ranking, 1)}
        dense_score = dict(dense_ranking)

        fused: dict[int, float] = {}
        for ordinal in range(len(atlas.segments)):
            score = self._lexical_weight / (self._rrf_k + lexical_rank[ordinal])
            if ordinal in dense_rank:
                score += self._dense_weight / (self._rrf_k + dense_rank[ordinal])
            fused[ordinal] = score

        ordered = _section_balanced_order(atlas, fused, plan.required_anchor_ids)
        selected, omitted, consumed = _apply_budget(atlas, ordered, plan.token_budget)
        anchors = tuple(atlas.segments[ordinal].anchor for ordinal in selected)
        covered_sections = tuple(dict.fromkeys(anchor.section_id for anchor in anchors))
        all_sections = tuple(section_id for section_id, _ in atlas.coverage.section_anchor_ids)
        omitted_sections = tuple(
            section_id for section_id in all_sections if section_id not in covered_sections
        )
        hits = tuple(
            RetrievalHit(
                anchor_id=atlas.segments[ordinal].anchor.anchor_id,
                section_id=atlas.segments[ordinal].anchor.section_id,
                lexical_rank=lexical_rank[ordinal],
                lexical_score=lexical_score[ordinal],
                dense_rank=dense_rank.get(ordinal),
                dense_score=dense_score.get(ordinal),
                fused_score=fused[ordinal],
            )
            for ordinal in selected
        )
        backend = "hybrid-rrf-v1" if self._dense_encoder is not None else atlas.lexical_backend
        return SemanticEvidencePacket(
            schema_version="1",
            snapshot_id=atlas.snapshot_id,
            purpose=queries[0],
            anchors=anchors,
            retrieval_queries=queries,
            omitted=omitted,
            covered_section_ids=covered_sections,
            omitted_section_ids=omitted_sections,
            token_budget=plan.token_budget,
            estimated_tokens=consumed,
            coverage_complete=(
                not omitted
                and atlas.coverage.full_source_covered
                and len(anchors) == len(atlas.segments)
            ),
            stage=plan.stage,
            retrieval_backend=backend,
            hits=hits,
        )

    def _dense_ranking(
        self,
        atlas: SemanticAtlas,
        queries: tuple[str, ...],
    ) -> tuple[tuple[int, float], ...]:
        assert self._dense_encoder is not None
        documents = self._document_cache.get(atlas.content_digest)
        if documents is None:
            documents = self._load_cached_vectors(atlas)
        if documents is None:
            documents = self._dense_encoder.encode_documents(
                tuple(segment.anchor.exact_text for segment in atlas.segments)
            )
            _validate_vectors(documents, len(atlas.segments), self._dense_encoder.dimensions)
            self._store_cached_vectors(atlas, documents)
            self._document_cache[atlas.content_digest] = documents
        query_vectors = self._dense_encoder.encode_queries(queries)
        _validate_vectors(query_vectors, len(queries), self._dense_encoder.dimensions)
        scored = tuple(
            (
                ordinal,
                max(_cosine(query, document) for query in query_vectors),
            )
            for ordinal, document in enumerate(documents)
        )
        return tuple(sorted(scored, key=lambda item: (-item[1], item[0])))

    def _cache_key(self, atlas: SemanticAtlas) -> str:
        assert self._dense_encoder is not None
        identity = "\0".join(
            (
                atlas.content_digest,
                self._dense_encoder.provider,
                self._dense_encoder.model,
                self._dense_encoder.revision,
                str(self._dense_encoder.dimensions),
            )
        )
        return hashlib.sha256(identity.encode()).hexdigest()

    def _load_cached_vectors(
        self,
        atlas: SemanticAtlas,
    ) -> tuple[tuple[float, ...], ...] | None:
        if self._cache_dir is None or self._dense_encoder is None:
            return None
        key = self._cache_key(atlas)
        manifest_path = self._cache_dir / f"{key}.json"
        vector_path = self._cache_dir / f"{key}.f32"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            count = len(atlas.segments)
            dimensions = self._dense_encoder.dimensions
            if manifest != {
                "schema_version": "1",
                "atlas_digest": atlas.content_digest,
                "provider": self._dense_encoder.provider,
                "model": self._dense_encoder.model,
                "revision": self._dense_encoder.revision,
                "dimensions": dimensions,
                "count": count,
            }:
                return None
            payload = vector_path.read_bytes()
            if len(payload) != count * dimensions * 4:
                return None
            flat = struct.unpack(f"<{count * dimensions}f", payload)
            vectors = tuple(
                tuple(flat[start : start + dimensions]) for start in range(0, len(flat), dimensions)
            )
            _validate_vectors(vectors, count, dimensions)
            self._document_cache[atlas.content_digest] = vectors
            return vectors
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, struct.error):
            return None

    def _store_cached_vectors(
        self,
        atlas: SemanticAtlas,
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        if self._cache_dir is None or self._dense_encoder is None:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        key = self._cache_key(atlas)
        manifest_path = self._cache_dir / f"{key}.json"
        vector_path = self._cache_dir / f"{key}.f32"
        manifest = {
            "schema_version": "1",
            "atlas_digest": atlas.content_digest,
            "provider": self._dense_encoder.provider,
            "model": self._dense_encoder.model,
            "revision": self._dense_encoder.revision,
            "dimensions": self._dense_encoder.dimensions,
            "count": len(vectors),
        }
        flat = tuple(value for vector in vectors for value in vector)
        suffix = f".tmp-{os.getpid()}-{uuid4().hex}"
        vector_temp = vector_path.with_suffix(vector_path.suffix + suffix)
        manifest_temp = manifest_path.with_suffix(manifest_path.suffix + suffix)
        vector_temp.write_bytes(struct.pack(f"<{len(flat)}f", *flat))
        manifest_temp.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(vector_temp, vector_path)
        os.replace(manifest_temp, manifest_path)


def _validate_vectors(
    vectors: tuple[tuple[float, ...], ...],
    expected_count: int,
    dimensions: int,
) -> None:
    if len(vectors) != expected_count:
        raise ValueError("encoder returned an unexpected vector count")
    if dimensions <= 0:
        raise ValueError("encoder dimensions must be positive")
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("encoder returned an unexpected vector dimension")
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise ValueError("encoder returned a non-finite value")


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _section_balanced_order(
    atlas: SemanticAtlas,
    scores: dict[int, float],
    required_anchor_ids: tuple[str, ...],
) -> tuple[int, ...]:
    section_order: list[str] = []
    candidates: dict[str, list[int]] = {}
    for ordinal, segment in enumerate(atlas.segments):
        section_id = segment.anchor.section_id
        if section_id not in candidates:
            section_order.append(section_id)
            candidates[section_id] = []
        candidates[section_id].append(ordinal)
    for values in candidates.values():
        values.sort(key=lambda ordinal: (-scores[ordinal], ordinal))

    required = set(required_anchor_ids) | set(atlas.coverage.orientation_anchor_ids)
    leading = [
        ordinal
        for ordinal, segment in enumerate(atlas.segments)
        if segment.anchor.anchor_id in required
    ]
    leading.sort(key=lambda ordinal: (-scores[ordinal], ordinal))
    leading_set = set(leading)
    for values in candidates.values():
        values[:] = [ordinal for ordinal in values if ordinal not in leading_set]

    ordered = list(leading)
    while any(candidates.values()):
        active = [section_id for section_id in section_order if candidates[section_id]]
        active.sort(
            key=lambda section_id: (
                -scores[candidates[section_id][0]],
                section_order.index(section_id),
            )
        )
        for section_id in active:
            ordered.append(candidates[section_id].pop(0))
    return tuple(ordered)


def _apply_budget(
    atlas: SemanticAtlas,
    ordered: tuple[int, ...],
    token_budget: int,
) -> tuple[tuple[int, ...], tuple[OmittedEvidence, ...], int]:
    selected: list[int] = []
    omitted: list[OmittedEvidence] = []
    consumed = 0
    for ordinal in ordered:
        segment = atlas.segments[ordinal]
        cost = segment.statistics.token_count
        if consumed + cost <= token_budget:
            selected.append(ordinal)
            consumed += cost
        else:
            omitted.append(
                OmittedEvidence(
                    anchor_id=segment.anchor.anchor_id,
                    section_id=segment.anchor.section_id,
                    reason="token_budget",
                    estimated_tokens=cost,
                )
            )
    return tuple(selected), tuple(omitted), consumed

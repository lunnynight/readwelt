"""Budget settlement, receipts, and page assembly for ArticleGraph queries."""

from __future__ import annotations

from collections.abc import Mapping

from readwelt.article_ir import UnitizationResult
from readwelt.provenance import SourceIndex, SourceIndexCandidate

from .digest import content_digest
from .models import ArticleGraph
from .query_continuation import QueryContinuationCodec
from .query_errors import fail_query
from .query_evidence import QueryEvidenceProjector
from .query_filtering import QueryCandidateFilter
from .query_models import (
    ArticleGraphQueryRequest,
    QueryErrorCode,
    QueryHit,
    QueryPage,
    QueryReceipt,
    QueryTruncationReason,
    QueryUsage,
    RelationHop,
)


class QueryResultAssembler:
    def __init__(
        self,
        graph: ArticleGraph,
        source_index: SourceIndex,
        unitization: UnitizationResult,
    ) -> None:
        self._graph = graph
        self._evidence = QueryEvidenceProjector(graph, source_index, unitization)
        self._filter = QueryCandidateFilter(graph, source_index)
        self._continuation = QueryContinuationCodec(graph)

    @property
    def known_graph_ids(self) -> frozenset[str]:
        return self._evidence.known_graph_ids

    def page(
        self,
        request: ArticleGraphQueryRequest,
        candidates: tuple[SourceIndexCandidate, ...],
        *,
        relation_paths: Mapping[str, tuple[RelationHop, ...]] | None = None,
    ) -> QueryPage:
        candidates = self._filter.apply(candidates, request.filters)
        query_digest = self._continuation.normalized_query_digest(request)
        start = self._continuation.offset(request, candidates, query_digest)
        hits: list[QueryHit] = []
        evidence_characters = 0
        source_bytes = 0
        relation_path_count = 0
        reason: QueryTruncationReason | None = None
        for candidate in candidates[start:]:
            reason = self._count_reason(request, len(hits))
            if reason is not None:
                break
            hit = self._evidence.hit(
                candidate,
                rank=len(hits) + 1,
                relation_path=(relation_paths or {}).get(candidate.object_id, ()),
            )
            added_characters = sum(len(item.exact_text or "") for item in hit.evidence)
            added_bytes = sum(
                len((item.exact_text or "").encode("utf-8")) for item in hit.evidence
            )
            added_paths = len(hit.relation_path)
            potential_characters = evidence_characters + added_characters
            potential_bytes = source_bytes + added_bytes
            reason = self._resource_reason(
                request,
                relation_paths=relation_path_count + added_paths,
                evidence_characters=potential_characters,
                source_bytes=potential_bytes,
                estimated_tokens=(potential_characters + 3) // 4,
            )
            if reason is not None:
                break
            hits.append(hit)
            evidence_characters = potential_characters
            source_bytes = potential_bytes
            relation_path_count += added_paths

        end = start + len(hits)
        if reason is not None and not hits:
            fail_query(QueryErrorCode.BUDGET_EXHAUSTED, f"first result exceeds {reason.value}")
        next_token = None
        if end < len(candidates):
            reason = reason or QueryTruncationReason.MAX_HITS
            next_token = self._continuation.next_token(
                request,
                candidates,
                query_digest,
                end,
            )
        settled_hits = tuple(hits)
        usage = QueryUsage(
            returned_hits=len(settled_hits),
            visited_objects=len(settled_hits),
            traversed_edges=relation_path_count,
            relation_paths=relation_path_count,
            evidence_characters=evidence_characters,
            source_bytes=source_bytes,
            estimated_tokens=(evidence_characters + 3) // 4,
        )
        receipt = self._receipt(request, query_digest, settled_hits, usage, next_token)
        return QueryPage(
            snapshot_id=self._graph.snapshot_id,
            graph_digest=self._graph.content_digest,
            operation=request.operation,
            normalized_query_digest=query_digest,
            hits=settled_hits,
            budget=request.budget,
            usage=usage,
            truncation_reason=reason,
            continuation=next_token,
            receipt=receipt,
        )

    @staticmethod
    def _count_reason(
        request: ArticleGraphQueryRequest,
        hit_count: int,
    ) -> QueryTruncationReason | None:
        if hit_count >= request.budget.max_hits:
            return QueryTruncationReason.MAX_HITS
        if hit_count >= request.budget.max_visited_objects:
            return QueryTruncationReason.MAX_VISITED_OBJECTS
        return None

    @staticmethod
    def _resource_reason(
        request: ArticleGraphQueryRequest,
        *,
        relation_paths: int,
        evidence_characters: int,
        source_bytes: int,
        estimated_tokens: int,
    ) -> QueryTruncationReason | None:
        if relation_paths > request.budget.max_relation_paths:
            return QueryTruncationReason.MAX_RELATION_PATHS
        if evidence_characters > request.budget.max_evidence_characters:
            return QueryTruncationReason.MAX_EVIDENCE_CHARACTERS
        if source_bytes > request.budget.max_source_bytes:
            return QueryTruncationReason.MAX_SOURCE_BYTES
        if estimated_tokens > request.budget.max_estimated_tokens:
            return QueryTruncationReason.MAX_ESTIMATED_TOKENS
        return None

    def _receipt(
        self,
        request: ArticleGraphQueryRequest,
        query_digest: str,
        hits: tuple[QueryHit, ...],
        usage: QueryUsage,
        next_token: str | None,
    ) -> QueryReceipt:
        result_digest = content_digest(
            {
                "snapshot_id": self._graph.snapshot_id,
                "operation": request.operation.value,
                "normalized_query_digest": query_digest,
                "hits": tuple(hit.to_dict() for hit in hits),
                "usage": usage.to_dict(),
            }
        )
        returned_ids = tuple(hit.object_id for hit in hits)
        receipt_values = {
            "snapshot_id": self._graph.snapshot_id,
            "graph_digest": self._graph.content_digest,
            "operation": request.operation.value,
            "consumer_stage": request.consumer_stage,
            "normalized_query_digest": query_digest,
            "returned_object_ids": returned_ids,
            "budget": request.budget.to_dict(),
            "usage": usage.to_dict(),
            "retrieval_backend": "deterministic",
            "result_digest": result_digest,
        }
        return QueryReceipt(
            receipt_id=content_digest(receipt_values),
            snapshot_id=self._graph.snapshot_id,
            graph_digest=self._graph.content_digest,
            operation=request.operation,
            consumer_stage=request.consumer_stage,
            normalized_query_digest=query_digest,
            returned_object_ids=returned_ids,
            budget=request.budget,
            usage=usage,
            input_continuation_digest=(
                content_digest(request.continuation) if request.continuation is not None else None
            ),
            output_continuation_digest=(
                content_digest(next_token) if next_token is not None else None
            ),
            retrieval_backend="deterministic",
            result_digest=result_digest,
        )

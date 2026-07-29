"""Opaque snapshot-bound ArticleGraph query continuation codec."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json

from readwelt.provenance import SourceIndexCandidate

from .digest import content_digest
from .models import ArticleGraph
from .query_errors import ArticleGraphQueryFailure, fail_query
from .query_models import (
    ArticleGraphQueryRequest,
    QueryContinuation,
    QueryError,
    QueryErrorCode,
)


class QueryContinuationCodec:
    def __init__(self, graph: ArticleGraph) -> None:
        self._graph = graph

    @staticmethod
    def normalized_query_digest(request: ArticleGraphQueryRequest) -> str:
        return content_digest(request.model_copy(update={"continuation": None}).to_dict())

    def offset(
        self,
        request: ArticleGraphQueryRequest,
        candidates: tuple[SourceIndexCandidate, ...],
        query_digest: str,
    ) -> int:
        if request.continuation is None:
            return 0
        continuation = self.decode(request.continuation)
        expected = (
            self._graph.snapshot_id,
            self._graph.content_digest,
            request.operation,
            query_digest,
            content_digest(request.filters.to_dict()),
            content_digest(request.budget.to_dict()),
        )
        observed = (
            continuation.snapshot_id,
            continuation.graph_digest,
            continuation.operation,
            continuation.normalized_query_digest,
            continuation.filter_digest,
            continuation.budget_digest,
        )
        if observed != expected:
            fail_query(
                QueryErrorCode.RESTART_REQUIRED,
                "query continuation no longer matches the immutable request snapshot",
            )
        if continuation.next_offset > len(candidates):
            fail_query(QueryErrorCode.INVALID_CONTINUATION, "continuation offset is out of range")
        expected_ordering_key = (
            (candidates[continuation.next_offset - 1].object_id,)
            if continuation.next_offset
            else ()
        )
        if expected_ordering_key != continuation.ordering_key:
            fail_query(
                QueryErrorCode.RESTART_REQUIRED,
                "query candidate ordering changed; restart against the current snapshot",
            )
        return continuation.next_offset

    def next_token(
        self,
        request: ArticleGraphQueryRequest,
        candidates: tuple[SourceIndexCandidate, ...],
        query_digest: str,
        end: int,
    ) -> str:
        continuation = QueryContinuation(
            snapshot_id=self._graph.snapshot_id,
            graph_digest=self._graph.content_digest,
            operation=request.operation,
            normalized_query_digest=query_digest,
            filter_digest=content_digest(request.filters.to_dict()),
            budget_digest=content_digest(request.budget.to_dict()),
            next_offset=end,
            ordering_key=(candidates[end - 1].object_id,),
            # Candidate order is deterministically rebuilt from the snapshot and
            # request digests. Serializing the full frontier made a five-hit page
            # carry hundreds of kilobytes of continuation state.
            remaining_frontier=(),
            visited_object_ids=(),
        )
        return self.encode(continuation)

    @staticmethod
    def encode(continuation: QueryContinuation) -> str:
        payload = json.dumps(
            continuation.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        return f"{encoded}.{hashlib.sha256(payload).hexdigest()}"

    @staticmethod
    def decode(token: str) -> QueryContinuation:
        try:
            encoded, integrity = token.split(".", 1)
            padding = "=" * (-len(encoded) % 4)
            payload = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
            if hashlib.sha256(payload).hexdigest() != integrity:
                raise ValueError("integrity mismatch")
            decoded = json.loads(payload)
            if not isinstance(decoded, dict):
                raise ValueError("payload is not an object")
            return QueryContinuation.from_dict(decoded)
        except (binascii.Error, json.JSONDecodeError, UnicodeError, ValueError) as error:
            raise ArticleGraphQueryFailure(
                QueryError(
                    code=QueryErrorCode.INVALID_CONTINUATION,
                    message="invalid query continuation",
                )
            ) from error

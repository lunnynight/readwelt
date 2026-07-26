"""Small deterministic BM25 facade backed by the Rust CPU kernel."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from readwelt import _core


class LexicalScorer(StrEnum):
    BM25 = "bm25"
    BM25_PLUS = "bm25_plus"
    BM25_L = "bm25_l"


class RetrievalIndex:
    """Reusable native lexical index; callers only provide stage queries."""

    backend = "rust-retrieval-v2"

    def __init__(
        self,
        documents: Sequence[tuple[str, ...]],
        *,
        scorer: LexicalScorer = LexicalScorer.BM25_PLUS,
        k1: float = 1.5,
        b: float = 0.75,
        delta: float = 1.0,
    ) -> None:
        self._native = _core.RetrievalIndex(
            [list(document) for document in documents],
            str(scorer),
            k1,
            b,
            delta,
        )

    @property
    def document_count(self) -> int:
        return int(self._native.document_count)

    @property
    def vocabulary_size(self) -> int:
        return int(self._native.vocabulary_size)

    def rank(
        self,
        query: tuple[str, ...],
        *,
        top_k: int | None = None,
    ) -> tuple[tuple[int, float], ...]:
        return tuple(self._native.rank(list(query), top_k))


class BM25Index:
    """Compatibility facade with the original explicit backend identity.

    The identity remains stable because it is part of semantic-atlas digests.
    Callers never receive native objects.
    """

    backend = "rust-bm25-v1"

    def __init__(self, documents: Sequence[tuple[str, ...]], *, k1: float = 1.5, b: float = 0.75):
        self._index = RetrievalIndex(
            documents,
            scorer=LexicalScorer.BM25,
            k1=k1,
            b=b,
        )

    def rank(self, query: tuple[str, ...]) -> tuple[tuple[int, float], ...]:
        return self._index.rank(query)

"""Small deterministic BM25 facade backed by the Rust CPU kernel."""

from __future__ import annotations

from collections.abc import Sequence

from readwelt import _core


class BM25Index:
    """Compatibility facade with the original explicit backend identity.

    The identity remains stable because it is part of semantic-atlas digests.
    Callers never receive native objects.
    """

    backend = "rust-bm25-v1"

    def __init__(self, documents: Sequence[tuple[str, ...]], *, k1: float = 1.5, b: float = 0.75):
        self._documents = tuple(documents)
        self._k1 = k1
        self._b = b

    def rank(self, query: tuple[str, ...]) -> tuple[tuple[int, float], ...]:
        return tuple(
            _core.bm25_rank(
                [list(document) for document in self._documents],
                list(query),
                self._k1,
                self._b,
            )
        )

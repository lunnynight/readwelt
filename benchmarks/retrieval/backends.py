"""Built-in benchmark adapters.

Adapters belong to the benchmark, not production. Future BM25+, BM25L, or BM25F
implementations can be compared by exposing the same ``RetrievalBackend`` protocol.
"""

from __future__ import annotations

from benchmarks.retrieval.contracts import BenchmarkCase
from readwelt.semantic.lexical import BM25Index, LexicalScorer, RetrievalIndex
from readwelt.semantic.tokenization import tokenize


class CurrentBM25Backend:
    """Faithful adapter for the current body-only ``rust-bm25-v1`` path."""

    name = "current-bm25"

    def rank(self, case: BenchmarkCase) -> tuple[tuple[str, float], ...]:
        documents = tuple(tokenize(anchor.text) for anchor in case.anchors)
        ranked = BM25Index(documents).rank(tokenize(case.query))
        return tuple((case.anchors[ordinal].anchor_id, score) for ordinal, score in ranked)


class NativeLexicalBackend:
    """Reuse one native index per candidate corpus, matching production v2."""

    def __init__(self, scorer: LexicalScorer) -> None:
        self._scorer = scorer
        self.name = f"native-{scorer.value}"
        self._indexes: dict[str, RetrievalIndex] = {}

    def rank(self, case: BenchmarkCase) -> tuple[tuple[str, float], ...]:
        index = self._indexes.get(case.case_id)
        if index is None:
            documents = tuple(tokenize(anchor.text) for anchor in case.anchors)
            index = RetrievalIndex(documents, scorer=self._scorer)
            self._indexes[case.case_id] = index
        ranked = index.rank(tokenize(case.query))
        return tuple((case.anchors[ordinal].anchor_id, score) for ordinal, score in ranked)


class NativeBM25Backend(NativeLexicalBackend):
    def __init__(self) -> None:
        super().__init__(LexicalScorer.BM25)


class BM25PlusBackend(NativeLexicalBackend):
    def __init__(self) -> None:
        super().__init__(LexicalScorer.BM25_PLUS)


class BM25LBackend(NativeLexicalBackend):
    def __init__(self) -> None:
        super().__init__(LexicalScorer.BM25_L)

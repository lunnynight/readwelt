from __future__ import annotations

import pytest

from readwelt.semantic.lexical import LexicalScorer, RetrievalIndex


def test_retrieval_index_builds_vocabulary_from_supplied_tokens_and_is_reused() -> None:
    documents = tuple((f"document-{ordinal}", f"topic-{ordinal}") for ordinal in range(3))
    index = RetrievalIndex(
        documents,
        scorer=LexicalScorer.BM25_PLUS,
    )

    first = index.rank(("topic-0",), top_k=2)
    last = index.rank(("topic-2",), top_k=1)

    assert len(first) == 2
    assert first[0][0] == 0
    assert last == ((2, last[0][1]),)
    assert index.vocabulary_size == 6


def test_all_lexical_scorers_are_explicit_and_deterministic() -> None:
    documents = (
        ("target", "short"),
        ("target",) + ("background",) * 100,
        ("unrelated",),
    )

    rankings = {
        scorer: RetrievalIndex(documents, scorer=scorer).rank(("target",))
        for scorer in LexicalScorer
    }

    assert set(rankings) == {
        LexicalScorer.BM25,
        LexicalScorer.BM25_PLUS,
        LexicalScorer.BM25_L,
    }
    for scorer, ranking in rankings.items():
        assert len(ranking) == len(documents), scorer
        assert ranking == tuple(sorted(ranking, key=lambda item: (-item[1], item[0])))


def test_bm25_plus_preserves_a_positive_gap_for_long_matching_document() -> None:
    documents = (
        ("target",) + ("background",) * 500,
        ("background",),
    )
    ranking = RetrievalIndex(
        documents,
        scorer=LexicalScorer.BM25_PLUS,
        delta=1.0,
    ).rank(("target",))
    scores = dict(ranking)

    assert scores[0] > scores[1]


def test_retrieval_index_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="top_k"):
        RetrievalIndex((("token",),)).rank(("token",), top_k=0)

    with pytest.raises(ValueError, match="delta"):
        RetrievalIndex(
            (("token",),),
            scorer=LexicalScorer.BM25_PLUS,
            delta=-1.0,
        )

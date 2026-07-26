from __future__ import annotations

import hashlib
import math
from collections import Counter

import pytest

from readwelt import _core
from readwelt.semantic.tokenization import estimate_tokens, tokenize

_MINHASH_SEED = b"readwelt-minhash-v1\0"


def _reference_signature(tokens: tuple[str, ...]) -> tuple[int, ...]:
    shingles = set(tokens)
    if not shingles:
        return ()
    return tuple(
        min(
            int.from_bytes(
                hashlib.blake2b(
                    _MINHASH_SEED + permutation.to_bytes(2, "big") + token.encode(),
                    digest_size=8,
                ).digest(),
                "big",
            )
            for token in shingles
        )
        for permutation in range(32)
    )


def _reference_bm25(
    documents: tuple[tuple[str, ...], ...], query: tuple[str, ...]
) -> tuple[tuple[int, float], ...]:
    average_length = sum(map(len, documents)) / len(documents)
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(set(document))
    size = len(documents)
    idf = {
        token: math.log(1.0 + (size - frequency + 0.5) / (frequency + 0.5))
        for token, frequency in document_frequency.items()
    }
    scores = []
    for ordinal, document in enumerate(documents):
        counts = Counter(document)
        score = 0.0
        for token in set(query):
            frequency = counts[token]
            if frequency:
                denominator = frequency + 1.5 * (0.25 + 0.75 * len(document) / average_length)
                score += idf[token] * frequency * 2.5 / denominator
        scores.append((ordinal, score))
    return tuple(sorted(scores, key=lambda item: (-item[1], item[0])))


def test_native_batch_matches_reference_tokenization_statistics_and_minhash() -> None:
    texts = [
        "量子芯片 Café's 2026。",
        "量子芯片 Café's 2026。",
        "量子芯片与计算。",
        "",
    ]
    records = _core.semantic_analyze(texts, 0.5)
    signatures = [_reference_signature(tokenize(text)) for text in texts]
    digests = [hashlib.sha256(text.encode()).hexdigest() for text in texts]

    for ordinal, (text, record) in enumerate(zip(texts, records, strict=True)):
        tokens = tokenize(text)
        assert tuple(record[0]) == tokens
        assert record[1:5] == (
            len(text),
            sum(not char.isspace() for char in text),
            estimate_tokens(text),
            1 if text.endswith("。") else 0,
        )
        assert record[5] == hashlib.sha256(text.encode()).hexdigest()
        assert len(_reference_signature(tokens)) == (32 if tokens else 0)
        expected_near = [
            prior
            for prior in range(ordinal)
            if digests[ordinal] != digests[prior]
            and signatures[ordinal]
            and (
                sum(
                    left == right
                    for left, right in zip(signatures[ordinal], signatures[prior], strict=True)
                )
                / len(signatures[ordinal])
                >= 0.5
            )
        ]
        assert record[7] == expected_near
    assert records[1][6] == 0


def test_native_bm25_matches_reference_scores_and_order() -> None:
    documents = tuple(tokenize(text) for text in ("苹果香蕉水果", "量子计算芯片", "古典音乐旋律"))
    query = tokenize("量子芯片")

    actual = tuple(_core.bm25_rank([list(item) for item in documents], list(query)))
    expected = _reference_bm25(documents, query)

    assert tuple(item[0] for item in actual) == tuple(item[0] for item in expected)
    assert tuple(item[1] for item in actual) == pytest.approx(tuple(item[1] for item in expected))


def test_native_coverage_matches_union_and_non_whitespace_reference() -> None:
    text = "甲乙\n丙丁 戊"
    ranges = [(0, 2), (1, 4)]

    assert _core.coverage_intervals(text, ranges) == ([(4, 5), (6, 7)], 4)

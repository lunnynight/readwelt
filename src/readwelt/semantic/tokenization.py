"""Versioned dependency-free tokenization for Chinese and Latin text."""

from __future__ import annotations

import re

TOKENIZER_VERSION = "readwelt-zh-bigram-en-word-v1"
_UNIT_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:['’_-][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*|[\u3400-\u9fff]")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize English as lowercase words and Chinese as chars plus adjacent bigrams."""
    units = [match.group(0).casefold() for match in _UNIT_RE.finditer(text)]
    result = list(units)
    for left, right in zip(units, units[1:], strict=False):
        if _CJK_RE.fullmatch(left) and _CJK_RE.fullmatch(right):
            result.append(left + right)
    return tuple(result)


def estimate_tokens(text: str) -> int:
    """Conservative deterministic input-budget estimate, never zero for non-empty text."""
    if not text:
        return 0
    latin_units = sum(1 for token in tokenize(text) if len(token) > 1 and token.isascii())
    cjk_chars = sum(1 for char in text if _CJK_RE.fullmatch(char))
    other = len(text) - cjk_chars
    return max(1, cjk_chars + latin_units + (other + 11) // 12)

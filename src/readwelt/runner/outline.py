"""Align a document outline with normalized paragraph anchors."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class OutlineItem(Protocol):
    @property
    def title(self) -> str: ...


class ParagraphAnchor(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def start_char(self) -> int: ...


def align_outline(
    paragraphs: Sequence[ParagraphAnchor],
    outline: Sequence[OutlineItem],
) -> tuple[tuple[int, int, str], ...]:
    if not paragraphs or not outline:
        return ()
    paragraph_titles = [" ".join(paragraph.text.split()) for paragraph in paragraphs]
    toc_matches = _match_outline_sequence(
        paragraph_titles,
        outline,
        start_ordinal=0,
        allow_prefix=False,
    )
    toc_end = toc_matches[-1][0] + 1 if toc_matches else 0
    repeated_after_toc = sum(
        1
        for item in outline
        if any(
            paragraph == item.title or paragraph.startswith(f"{item.title} ")
            for paragraph in paragraph_titles[toc_end:]
        )
    )
    body_start = (
        toc_end
        if len(toc_matches) >= max(2, len(outline) // 2)
        and repeated_after_toc >= max(2, len(outline) // 2)
        else 0
    )
    body_matches = _match_outline_sequence(
        paragraph_titles,
        outline,
        start_ordinal=body_start,
        allow_prefix=True,
    )
    return tuple(
        (paragraphs[paragraph_ordinal].start_char, outline_ordinal, title)
        for paragraph_ordinal, outline_ordinal, title in body_matches
    )


def _match_outline_sequence(
    paragraph_titles: Sequence[str],
    outline: Sequence[OutlineItem],
    *,
    start_ordinal: int,
    allow_prefix: bool,
) -> tuple[tuple[int, int, str], ...]:
    cursor = start_ordinal
    matches: list[tuple[int, int, str]] = []
    for outline_ordinal, item in enumerate(outline):
        paragraph_ordinal = next(
            (
                ordinal
                for ordinal in range(cursor, len(paragraph_titles))
                if paragraph_titles[ordinal] == item.title
                or (allow_prefix and paragraph_titles[ordinal].startswith(f"{item.title} "))
            ),
            None,
        )
        if paragraph_ordinal is None:
            continue
        matches.append((paragraph_ordinal, outline_ordinal, item.title))
        cursor = paragraph_ordinal + 1
    return tuple(matches)

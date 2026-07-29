"""Deterministic exact and lexical candidate retrieval over SourceIndex."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from readwelt.semantic.tokenization import tokenize

from .source_index_projection import ordered_subset

if TYPE_CHECKING:
    from .source_index import SourceIndex


class SourceCandidateKind(StrEnum):
    SOURCE_UNIT = "source_unit"
    NODE = "node"
    RELATION = "relation"
    CLAIM = "claim"


class SourceCandidateMatch(StrEnum):
    EXACT_ID = "exact_id"
    LEXICAL = "lexical"


@dataclass(frozen=True, slots=True)
class SourceIndexCandidate:
    object_id: str
    object_kind: SourceCandidateKind
    match_kind: SourceCandidateMatch
    source_unit_ids: tuple[str, ...]
    source_element_ids: tuple[str, ...] = ()
    matched_lexemes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.object_id:
            raise ValueError("source candidate object_id must be non-empty")
        if not self.source_unit_ids:
            raise ValueError("source candidate must retain source units")


def retrieve_exact_candidates(
    index: SourceIndex,
    identities: Iterable[str],
) -> tuple[SourceIndexCandidate, ...]:
    ordered = tuple(dict.fromkeys(identity for identity in identities if identity))
    known = (
        frozenset(index.source_unit_ids),
        frozenset(index.canonical_node_ids),
        frozenset(index.canonical_edge_ids),
        frozenset(index.canonical_claim_ids),
    )
    candidates: list[SourceIndexCandidate] = []
    for identity in ordered:
        kind_and_sources = _exact_sources(index, identity, known)
        if kind_and_sources is None:
            continue
        kind, unit_ids, element_ids = kind_and_sources
        if unit_ids:
            candidates.append(
                _candidate(
                    index,
                    identity,
                    kind,
                    SourceCandidateMatch.EXACT_ID,
                    unit_ids,
                    (identity,),
                    element_ids,
                )
            )
    return tuple(candidates)


def retrieve_lexical_candidates(
    index: SourceIndex,
    query: str,
) -> tuple[SourceIndexCandidate, ...]:
    lexemes = tuple(dict.fromkeys(tokenize(query)))
    if not lexemes:
        return ()
    lexical_ranges = dict(index.lexical_to_ranges)
    lexical_elements = dict(index.lexical_to_elements)
    matches_by_unit: dict[str, set[str]] = {}
    for lexeme in lexemes:
        range_units = (
            unit_id
            for range_id in lexical_ranges.get(lexeme, ())
            for unit_id in index.units_for_range(range_id)
        )
        element_units = (
            unit_id
            for element_id in lexical_elements.get(lexeme, ())
            for unit_id in index.units_for_element(element_id)
        )
        for unit_id in (*range_units, *element_units):
            matches_by_unit.setdefault(unit_id, set()).add(lexeme)
    matches = _knowledge_matches(index, matches_by_unit)
    candidates = tuple(
        _lexical_candidate(index, kind, identity, matched)
        for (kind, identity), matched in matches.items()
    )
    return tuple(sorted(candidates, key=lambda item: _order_key(index, item)))


def _exact_sources(
    index: SourceIndex,
    identity: str,
    known: tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]],
) -> tuple[SourceCandidateKind, tuple[str, ...], tuple[str, ...]] | None:
    units, nodes, edges, claims = known
    if identity in units:
        return SourceCandidateKind.SOURCE_UNIT, (identity,), ()
    if identity in nodes:
        return (
            SourceCandidateKind.NODE,
            index.units_for_node(identity),
            index.elements_for_node(identity),
        )
    if identity in edges:
        return (
            SourceCandidateKind.RELATION,
            index.units_for_edge(identity),
            index.elements_for_edge(identity),
        )
    if identity in claims:
        return (
            SourceCandidateKind.CLAIM,
            index.evidence_units_for_claim(identity),
            index.evidence_elements_for_claim(identity),
        )
    return None


def _knowledge_matches(
    index: SourceIndex,
    matches_by_unit: dict[str, set[str]],
) -> dict[tuple[SourceCandidateKind, str], set[str]]:
    matches: dict[tuple[SourceCandidateKind, str], set[str]] = {}
    for unit_id, matched in matches_by_unit.items():
        matches[(SourceCandidateKind.SOURCE_UNIT, unit_id)] = set(matched)
        knowledge = index.knowledge_for_unit(unit_id)
        for kind, identities in (
            (SourceCandidateKind.NODE, knowledge.node_ids),
            (SourceCandidateKind.RELATION, knowledge.edge_ids),
            (SourceCandidateKind.CLAIM, knowledge.claim_ids),
        ):
            for identity in identities:
                matches.setdefault((kind, identity), set()).update(matched)
    return matches


def _lexical_candidate(
    index: SourceIndex,
    kind: SourceCandidateKind,
    identity: str,
    matched: set[str],
) -> SourceIndexCandidate:
    unit_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    if kind is SourceCandidateKind.SOURCE_UNIT:
        unit_ids, element_ids = (identity,), ()
    elif kind is SourceCandidateKind.NODE:
        unit_ids, element_ids = index.units_for_node(identity), index.elements_for_node(identity)
    elif kind is SourceCandidateKind.RELATION:
        unit_ids, element_ids = index.units_for_edge(identity), index.elements_for_edge(identity)
    else:
        unit_ids = index.evidence_units_for_claim(identity)
        element_ids = index.evidence_elements_for_claim(identity)
    return _candidate(
        index,
        identity,
        kind,
        SourceCandidateMatch.LEXICAL,
        unit_ids,
        tuple(sorted(matched)),
        element_ids,
    )


def _candidate(
    index: SourceIndex,
    identity: str,
    kind: SourceCandidateKind,
    match_kind: SourceCandidateMatch,
    unit_ids: tuple[str, ...],
    matched_lexemes: tuple[str, ...],
    element_ids: tuple[str, ...],
) -> SourceIndexCandidate:
    return SourceIndexCandidate(
        object_id=identity,
        object_kind=kind,
        match_kind=match_kind,
        source_unit_ids=ordered_subset(unit_ids, index.source_unit_ids),
        source_element_ids=ordered_subset(element_ids, index.source_element_ids),
        matched_lexemes=matched_lexemes,
    )


def _order_key(
    index: SourceIndex,
    candidate: SourceIndexCandidate,
) -> tuple[int, int, int, str]:
    ordinal_by_unit = {unit_id: ordinal for ordinal, unit_id in index.ordinal_to_unit}
    first_ordinal = min(
        (ordinal_by_unit[unit_id] for unit_id in candidate.source_unit_ids),
        default=len(ordinal_by_unit),
    )
    kind_order = {
        SourceCandidateKind.SOURCE_UNIT: 0,
        SourceCandidateKind.NODE: 1,
        SourceCandidateKind.RELATION: 2,
        SourceCandidateKind.CLAIM: 3,
    }
    return (
        -len(candidate.matched_lexemes),
        first_ordinal,
        kind_order[candidate.object_kind],
        candidate.object_id,
    )

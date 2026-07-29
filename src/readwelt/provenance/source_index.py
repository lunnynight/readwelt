"""Rebuildable source-first and knowledge-to-source navigation projections."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from readwelt.article_graph.digest import content_digest
from readwelt.article_graph.models import ArticleGraph, MergeReport
from readwelt.article_ir import UnitizationResult
from readwelt.semantic.tokenization import tokenize

from .ledger import ProvenanceLedger
from .source_index_candidates import (
    SourceIndexCandidate,
    retrieve_exact_candidates,
    retrieve_lexical_candidates,
)
from .source_index_projection import (
    SourceIndexDiagnostic,
    build_source_index_values,
    ordered_subset,
    ranges_for_units,
    reverse,
)
from .source_index_validation import validate_source_index

SOURCE_INDEX_SCHEMA_VERSION = "source-index.v3"


@dataclass(frozen=True, slots=True)
class UnitKnowledge:
    node_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceLookup:
    """A fail-empty source locator result at Source Plane identity level."""

    range_ids: tuple[str, ...] = ()
    unit_ids: tuple[str, ...] = ()
    element_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceNeighborhood:
    parent_unit_id: str | None = None
    child_unit_ids: tuple[str, ...] = ()
    previous_unit_id: str | None = None
    next_unit_id: str | None = None


@dataclass(frozen=True, slots=True)
class SourceIndexClosure:
    valid: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceIndex:
    schema_version: str
    graph_digest: str
    ledger_head_digest: str
    node_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    edge_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    claim_to_evidence_units: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_nodes: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_edges: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_claims: tuple[tuple[str, tuple[str, ...]], ...]
    source_unit_ids: tuple[str, ...]
    source_range_ids: tuple[str, ...]
    source_element_ids: tuple[str, ...]
    canonical_node_ids: tuple[str, ...]
    canonical_edge_ids: tuple[str, ...]
    canonical_claim_ids: tuple[str, ...]
    range_intervals: tuple[tuple[int, int, str], ...]
    range_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_ranges: tuple[tuple[str, tuple[str, ...]], ...]
    ordinal_to_unit: tuple[tuple[int, str], ...]
    section_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    heading_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    element_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    page_to_units: tuple[tuple[int, tuple[str, ...]], ...]
    page_to_elements: tuple[tuple[int, tuple[str, ...]], ...]
    lexical_to_ranges: tuple[tuple[str, tuple[str, ...]], ...]
    lexical_to_elements: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_parent: tuple[tuple[str, str], ...]
    parent_to_children: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_previous: tuple[tuple[str, str], ...]
    unit_to_next: tuple[tuple[str, str], ...]
    element_to_parent: tuple[tuple[str, str], ...]
    parent_to_child_elements: tuple[tuple[str, tuple[str, ...]], ...]
    element_to_previous: tuple[tuple[str, str], ...]
    element_to_next: tuple[tuple[str, str], ...]
    lexical_tokenizer_version: str
    diagnostics: tuple[SourceIndexDiagnostic, ...]
    content_digest: str
    node_to_elements: tuple[tuple[str, tuple[str, ...]], ...] = ()
    edge_to_elements: tuple[tuple[str, tuple[str, ...]], ...] = ()
    claim_to_evidence_elements: tuple[tuple[str, tuple[str, ...]], ...] = ()
    element_to_nodes: tuple[tuple[str, tuple[str, ...]], ...] = ()
    element_to_edges: tuple[tuple[str, tuple[str, ...]], ...] = ()
    element_to_claims: tuple[tuple[str, tuple[str, ...]], ...] = ()
    source_section_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version not in {"source-index.v2", SOURCE_INDEX_SCHEMA_VERSION}:
            raise ValueError(f"unsupported source index schema: {self.schema_version}")
        if reverse(dict(self.node_to_units)) != self.unit_to_nodes:
            raise ValueError("node source index directions disagree")
        if reverse(dict(self.edge_to_units)) != self.unit_to_edges:
            raise ValueError("edge source index directions disagree")
        if reverse(dict(self.claim_to_evidence_units)) != self.unit_to_claims:
            raise ValueError("claim source index directions disagree")
        if reverse(dict(self.node_to_elements)) != self.element_to_nodes:
            raise ValueError("node element index directions disagree")
        if reverse(dict(self.edge_to_elements)) != self.element_to_edges:
            raise ValueError("edge element index directions disagree")
        if reverse(dict(self.claim_to_evidence_elements)) != self.element_to_claims:
            raise ValueError("claim element index directions disagree")
        if reverse(dict(self.range_to_units)) != self.unit_to_ranges:
            raise ValueError("range source index directions disagree")
        closure = self.validate_closure()
        if not closure.valid:
            raise ValueError(f"source index closure failed: {closure.diagnostics[0]}")
        if self.content_digest != content_digest(self._digest_payload()):
            raise ValueError("source index content digest mismatch")

    @classmethod
    def rebuild(
        cls,
        graph: ArticleGraph,
        unitization: UnitizationResult,
        ledger: ProvenanceLedger | None = None,
        merge_report: MergeReport | None = None,
    ) -> SourceIndex:
        """Rebuild deterministic source and knowledge projections from immutable facts."""

        del merge_report
        if ledger is not None and not ledger.verify_chain().valid:
            raise ValueError("cannot project SourceIndex from an invalid ledger")
        if graph.snapshot_id != unitization.snapshot_id:
            raise ValueError("graph and Source Plane belong to different snapshots")

        values = build_source_index_values(
            graph,
            unitization,
            schema_version=SOURCE_INDEX_SCHEMA_VERSION,
            ledger_head_digest=ledger.head_digest if ledger is not None else "",
        )
        return cls(
            **cast(Any, values),
            content_digest=content_digest(values),
        )

    def units_for_node(self, node_id: str) -> tuple[str, ...]:
        return dict(self.node_to_units).get(node_id, ())

    def units_for_edge(self, edge_id: str) -> tuple[str, ...]:
        return dict(self.edge_to_units).get(edge_id, ())

    def evidence_units_for_claim(self, claim_id: str) -> tuple[str, ...]:
        return dict(self.claim_to_evidence_units).get(claim_id, ())

    def elements_for_node(self, node_id: str) -> tuple[str, ...]:
        return dict(self.node_to_elements).get(node_id, ())

    def elements_for_edge(self, edge_id: str) -> tuple[str, ...]:
        return dict(self.edge_to_elements).get(edge_id, ())

    def evidence_elements_for_claim(self, claim_id: str) -> tuple[str, ...]:
        return dict(self.claim_to_evidence_elements).get(claim_id, ())

    def knowledge_for_unit(self, unit_id: str) -> UnitKnowledge:
        return UnitKnowledge(
            node_ids=dict(self.unit_to_nodes).get(unit_id, ()),
            edge_ids=dict(self.unit_to_edges).get(unit_id, ()),
            claim_ids=dict(self.unit_to_claims).get(unit_id, ()),
        )

    def knowledge_for_range(self, range_id: str) -> UnitKnowledge:
        unit_ids = self.units_for_range(range_id)
        return _combine_knowledge(self.knowledge_for_unit(unit_id) for unit_id in unit_ids)

    def knowledge_for_element(self, element_id: str) -> UnitKnowledge:
        return UnitKnowledge(
            node_ids=dict(self.element_to_nodes).get(element_id, ()),
            edge_ids=dict(self.element_to_edges).get(element_id, ()),
            claim_ids=dict(self.element_to_claims).get(element_id, ()),
        )

    def units_for_range(self, range_id: str) -> tuple[str, ...]:
        return dict(self.range_to_units).get(range_id, ())

    def range_at_offset(self, offset: int) -> str | None:
        if offset < 0:
            return None
        return next(
            (range_id for start, end, range_id in self.range_intervals if start <= offset < end),
            None,
        )

    def locate_offsets(self, start_offset: int, end_offset: int) -> SourceLookup:
        if start_offset < 0 or end_offset <= start_offset:
            return SourceLookup()
        range_ids = tuple(
            range_id
            for start, end, range_id in self.range_intervals
            if start < end_offset and end > start_offset
        )
        return self._lookup_for_ranges(range_ids)

    def unit_at_ordinal(self, ordinal: int) -> str | None:
        return dict(self.ordinal_to_unit).get(ordinal)

    def ordered_units(
        self,
        start_ordinal: int = 0,
        end_ordinal: int | None = None,
    ) -> tuple[str, ...]:
        if start_ordinal < 0 or (end_ordinal is not None and end_ordinal <= start_ordinal):
            return ()
        return tuple(
            unit_id
            for ordinal, unit_id in self.ordinal_to_unit
            if ordinal >= start_ordinal and (end_ordinal is None or ordinal < end_ordinal)
        )

    def units_for_section(self, section_id: str) -> tuple[str, ...]:
        return dict(self.section_to_units).get(section_id, ())

    def units_for_heading(self, heading: str) -> tuple[str, ...]:
        return dict(self.heading_to_units).get(heading, ())

    def units_for_element(self, element_id: str) -> tuple[str, ...]:
        return dict(self.element_to_units).get(element_id, ())

    def locate_page(self, page: int) -> SourceLookup:
        if page < 1:
            return SourceLookup()
        unit_ids = dict(self.page_to_units).get(page, ())
        return SourceLookup(
            range_ids=ranges_for_units(unit_ids, dict(self.unit_to_ranges)),
            unit_ids=unit_ids,
            element_ids=dict(self.page_to_elements).get(page, ()),
        )

    def locate_lexical(self, query: str) -> SourceLookup:
        lexemes = tuple(dict.fromkeys(tokenize(query)))
        if not lexemes:
            return SourceLookup()
        lexical_ranges = dict(self.lexical_to_ranges)
        lexical_elements = dict(self.lexical_to_elements)
        range_ids = ordered_subset(
            (range_id for lexeme in lexemes for range_id in lexical_ranges.get(lexeme, ())),
            self.source_range_ids,
        )
        element_ids = ordered_subset(
            (element_id for lexeme in lexemes for element_id in lexical_elements.get(lexeme, ())),
            self.source_element_ids,
        )
        lookup = self._lookup_for_ranges(range_ids)
        return SourceLookup(
            range_ids=lookup.range_ids,
            unit_ids=lookup.unit_ids,
            element_ids=element_ids,
        )

    def retrieve_exact_candidates(
        self,
        identities: Iterable[str],
    ) -> tuple[SourceIndexCandidate, ...]:
        return retrieve_exact_candidates(self, identities)

    def retrieve_lexical_candidates(self, query: str) -> tuple[SourceIndexCandidate, ...]:
        return retrieve_lexical_candidates(self, query)

    def neighborhood(self, unit_id: str) -> SourceNeighborhood:
        if unit_id not in frozenset(self.source_unit_ids):
            return SourceNeighborhood()
        return SourceNeighborhood(
            parent_unit_id=dict(self.unit_to_parent).get(unit_id),
            child_unit_ids=dict(self.parent_to_children).get(unit_id, ()),
            previous_unit_id=dict(self.unit_to_previous).get(unit_id),
            next_unit_id=dict(self.unit_to_next).get(unit_id),
        )

    def parent_element(self, element_id: str) -> str | None:
        return dict(self.element_to_parent).get(element_id)

    def child_elements(self, element_id: str) -> tuple[str, ...]:
        return dict(self.parent_to_child_elements).get(element_id, ())

    def previous_element(self, element_id: str) -> str | None:
        return dict(self.element_to_previous).get(element_id)

    def next_element(self, element_id: str) -> str | None:
        return dict(self.element_to_next).get(element_id)

    def validate_closure(self) -> SourceIndexClosure:
        problems = validate_source_index(
            self,
            current_schema=SOURCE_INDEX_SCHEMA_VERSION,
        )
        return SourceIndexClosure(valid=not problems, diagnostics=problems)

    def _lookup_for_ranges(self, range_ids: tuple[str, ...]) -> SourceLookup:
        known_ranges = frozenset(self.source_range_ids)
        admitted = tuple(range_id for range_id in range_ids if range_id in known_ranges)
        unit_ids = ordered_subset(
            (
                unit_id
                for range_id in admitted
                for unit_id in dict(self.range_to_units).get(range_id, ())
            ),
            self.source_unit_ids,
        )
        return SourceLookup(range_ids=admitted, unit_ids=unit_ids)

    def _digest_payload(self) -> dict[str, object]:
        payload = {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
            if field != "content_digest"
        }
        if self.schema_version == "source-index.v2":
            for field in (
                "node_to_elements",
                "edge_to_elements",
                "claim_to_evidence_elements",
                "element_to_nodes",
                "element_to_edges",
                "element_to_claims",
                "source_section_ids",
            ):
                payload.pop(field)
        return payload


def _combine_knowledge(items: Iterable[UnitKnowledge]) -> UnitKnowledge:
    values = tuple(items)
    return UnitKnowledge(
        node_ids=tuple(sorted({item for value in values for item in value.node_ids})),
        edge_ids=tuple(sorted({item for value in values for item in value.edge_ids})),
        claim_ids=tuple(sorted({item for value in values for item in value.claim_ids})),
    )

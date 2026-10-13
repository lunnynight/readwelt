"""Truthful Source Plane evidence projection for ArticleGraph query hits."""

from __future__ import annotations

from collections.abc import Iterable

from readwelt.article_ir import AnchoredTextUnit, SourceReference, UnitizationResult
from readwelt.provenance import SourceCandidateKind, SourceIndex, SourceIndexCandidate

from .digest import content_digest
from .models import ArticleEdge, ArticleGraph, ArticleNode, Claim
from .query_errors import fail_query
from .query_models import (
    EvidenceEnvelope,
    LocatorPrecision,
    QueryErrorCode,
    QueryHit,
    QueryObjectKind,
    RelationHop,
    SourceLocator,
)


class QueryEvidenceProjector:
    def __init__(
        self,
        graph: ArticleGraph,
        source_index: SourceIndex,
        unitization: UnitizationResult,
    ) -> None:
        self._source_index = source_index
        self._units = {unit.unit_id: unit for unit in unitization.units}
        self._nodes = {node.node_id: node for node in graph.nodes}
        self._edges = {edge.edge_id: edge for edge in graph.edges}
        self._claims = {claim.claim_id: claim for claim in graph.claims}

    @property
    def known_graph_ids(self) -> frozenset[str]:
        return frozenset((*self._nodes, *self._edges, *self._claims))

    def hit(
        self,
        candidate: SourceIndexCandidate,
        *,
        rank: int,
        relation_path: tuple[RelationHop, ...] = (),
    ) -> QueryHit:
        evidence = self._evidence(candidate.object_id, candidate.source_unit_ids)
        label: str | None = None
        text: str | None = None
        status: str | None = None
        confidence: float | None = None
        confidence_method: str | None = None
        ambiguity: tuple[str, ...] = ()
        if candidate.object_kind is SourceCandidateKind.SOURCE_UNIT:
            unit = self._units[candidate.object_id]
            label = unit.kind
            text = unit.exact_text
        else:
            graph_object = self._graph_object(candidate.object_id)
            if isinstance(graph_object, ArticleNode):
                label = graph_object.label
                text = graph_object.label
            elif isinstance(graph_object, ArticleEdge):
                label = graph_object.relation
            else:
                text = graph_object.text
            status = graph_object.epistemic_status.value
            confidence = graph_object.confidence
            confidence_method = graph_object.confidence_method
            ambiguity = graph_object.ambiguity
        return QueryHit(
            object_id=candidate.object_id,
            object_kind=self._query_kind(candidate.object_kind),
            rank=rank,
            score=float(len(candidate.matched_lexemes)) or None,
            match_reason=candidate.match_kind.value,
            label=label,
            text=text,
            epistemic_status=status,
            confidence=confidence,
            confidence_method=confidence_method,
            ambiguity=ambiguity,
            source_unit_ids=candidate.source_unit_ids,
            source_element_ids=candidate.source_element_ids,
            evidence=evidence,
            relation_path=relation_path,
        )

    def _evidence(
        self,
        object_id: str,
        unit_ids: Iterable[str],
    ) -> tuple[EvidenceEnvelope, ...]:
        envelopes: list[EvidenceEnvelope] = []
        for unit_id in unit_ids:
            unit = self._units.get(unit_id)
            if unit is None:
                fail_query(
                    QueryErrorCode.DANGLING_SOURCE_REFERENCE,
                    f"source unit does not resolve: {unit_id}",
                )
            locators = tuple(self._locators(unit))
            if not locators:
                fail_query(
                    QueryErrorCode.DANGLING_SOURCE_REFERENCE,
                    f"source unit has no truthful locator: {unit_id}",
                )
            provenance_digest = (
                self._source_index.ledger_head_digest or self._source_index.content_digest
            )
            values = {
                "graph_object_ids": (object_id,),
                "locators": tuple(locator.to_dict() for locator in locators),
                "exact_text": unit.exact_text,
                "provenance_digest": provenance_digest,
            }
            envelopes.append(
                EvidenceEnvelope(
                    evidence_id=content_digest(values),
                    graph_object_ids=(object_id,),
                    locators=locators,
                    exact_text=unit.exact_text,
                    provenance_digest=provenance_digest,
                )
            )
        return tuple(envelopes)

    def _locators(self, unit: AnchoredTextUnit) -> Iterable[SourceLocator]:
        range_ids = dict(self._source_index.unit_to_ranges).get(unit.unit_id, ())
        for reference in unit.source_references:
            yield self._locator(unit.unit_id, range_ids, reference)

    @staticmethod
    def _locator(
        unit_id: str,
        range_ids: tuple[str, ...],
        reference: SourceReference,
    ) -> SourceLocator:
        if range_ids and reference.start_offset is not None:
            precision = LocatorPrecision.EXACT_RANGE
            range_id = range_ids[0]
        elif reference.element_id is not None:
            precision = LocatorPrecision.SOURCE_ELEMENT
            range_id = None
        elif reference.page is not None:
            precision = LocatorPrecision.PAGE
            range_id = None
        else:
            precision = LocatorPrecision.SOURCE_UNIT
            range_id = None
        return SourceLocator(
            precision=precision,
            source_unit_id=unit_id,
            source_range_id=range_id,
            source_element_id=reference.element_id,
            section_id=reference.section_id,
            page=reference.page,
            bounding_box=reference.bounding_box,
            start_offset=reference.start_offset,
            end_offset=reference.end_offset,
        )

    def _graph_object(self, object_id: str) -> ArticleNode | ArticleEdge | Claim:
        value = (
            self._nodes.get(object_id) or self._edges.get(object_id) or self._claims.get(object_id)
        )
        if value is None:
            fail_query(QueryErrorCode.OBJECT_NOT_FOUND, f"graph object not found: {object_id}")
        return value

    @staticmethod
    def _query_kind(kind: SourceCandidateKind) -> QueryObjectKind:
        return {
            SourceCandidateKind.SOURCE_UNIT: QueryObjectKind.SOURCE_UNIT,
            SourceCandidateKind.NODE: QueryObjectKind.NODE,
            SourceCandidateKind.RELATION: QueryObjectKind.EDGE,
            SourceCandidateKind.CLAIM: QueryObjectKind.CLAIM,
        }[kind]

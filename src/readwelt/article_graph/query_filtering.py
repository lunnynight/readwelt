"""Deterministic candidate filtering for public ArticleGraph queries."""

from __future__ import annotations

from readwelt.provenance import SourceCandidateKind, SourceIndex, SourceIndexCandidate

from .models import ArticleGraph
from .query_models import QueryFilter, QueryObjectKind


class QueryCandidateFilter:
    def __init__(self, graph: ArticleGraph, source_index: SourceIndex) -> None:
        self._kinds = {
            SourceCandidateKind.SOURCE_UNIT: QueryObjectKind.SOURCE_UNIT,
            SourceCandidateKind.NODE: QueryObjectKind.NODE,
            SourceCandidateKind.RELATION: QueryObjectKind.EDGE,
            SourceCandidateKind.CLAIM: QueryObjectKind.CLAIM,
        }
        self._relations = {edge.edge_id: edge.relation for edge in graph.edges}
        self._statuses = {
            node.node_id: node.epistemic_status.value for node in graph.nodes
        }
        self._statuses.update(
            {edge.edge_id: edge.epistemic_status.value for edge in graph.edges}
        )
        self._statuses.update(
            {claim.claim_id: claim.epistemic_status.value for claim in graph.claims}
        )
        self._page_units = dict(source_index.page_to_units)

    def apply(
        self,
        candidates: tuple[SourceIndexCandidate, ...],
        filters: QueryFilter,
    ) -> tuple[SourceIndexCandidate, ...]:
        return tuple(candidate for candidate in candidates if self._matches(candidate, filters))

    def _matches(self, candidate: SourceIndexCandidate, filters: QueryFilter) -> bool:
        if filters.object_kinds and self._kinds[candidate.object_kind] not in filters.object_kinds:
            return False
        if filters.source_unit_ids and not set(candidate.source_unit_ids).intersection(
            filters.source_unit_ids
        ):
            return False
        if filters.source_element_ids and not set(candidate.source_element_ids).intersection(
            filters.source_element_ids
        ):
            return False
        if filters.relation_kinds and self._relations.get(candidate.object_id) not in set(
            filters.relation_kinds
        ):
            return False
        if filters.epistemic_statuses and self._statuses.get(candidate.object_id) not in set(
            filters.epistemic_statuses
        ):
            return False
        if filters.page_start is not None:
            page_end = filters.page_end or filters.page_start
            allowed_units = {
                unit_id
                for page in range(filters.page_start, page_end + 1)
                for unit_id in self._page_units.get(page, ())
            }
            if not allowed_units.intersection(candidate.source_unit_ids):
                return False
        return True


__all__ = ["QueryCandidateFilter"]

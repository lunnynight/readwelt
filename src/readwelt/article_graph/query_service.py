"""In-memory operation and traversal core for the ArticleGraph Query Plane."""

from __future__ import annotations

from readwelt.article_ir import UnitizationResult
from readwelt.provenance import SourceIndex, SourceIndexCandidate

from .models import ArticleEdge, ArticleGraph
from .query_errors import ArticleGraphQueryFailure, fail_query
from .query_models import (
    ArticleGraphQueryRequest,
    QueryErrorCode,
    QueryOperation,
    QueryPage,
    RelationHop,
)
from .query_results import QueryResultAssembler


class ArticleGraphQueryService:
    """Query one immutable graph/source snapshot without persistence concerns."""

    def __init__(
        self,
        graph: ArticleGraph,
        source_index: SourceIndex,
        unitization: UnitizationResult,
    ) -> None:
        if graph.snapshot_id != unitization.snapshot_id:
            raise ValueError("graph and Source Plane belong to different snapshots")
        if source_index.graph_digest != graph.content_digest:
            raise ValueError("SourceIndex belongs to a different graph")
        if tuple(unit.unit_id for unit in unitization.units) != source_index.source_unit_ids:
            raise ValueError("SourceIndex and Source Plane unit identities disagree")
        self._graph = graph
        self._source_index = source_index
        self._nodes = {node.node_id: node for node in graph.nodes}
        self._claims = {claim.claim_id: claim for claim in graph.claims}
        self._results = QueryResultAssembler(graph, source_index, unitization)

    def search(self, request: ArticleGraphQueryRequest) -> QueryPage:
        """Return deterministic source-first matches across source and graph objects."""
        self._require_operation(request, QueryOperation.SEARCH)
        return self._results.page(request, self._candidates(request))

    def locate(self, request: ArticleGraphQueryRequest) -> QueryPage:
        self._require_operation(request, QueryOperation.LOCATE)
        return self._results.page(request, self._candidates(request))

    def evidence(self, request: ArticleGraphQueryRequest) -> QueryPage:
        self._require_operation(request, QueryOperation.EVIDENCE)
        if not request.object_ids:
            fail_query(QueryErrorCode.INVALID_REQUEST, "evidence requires object_ids")
        candidates = self._source_index.retrieve_exact_candidates(request.object_ids)
        resolved = frozenset(candidate.object_id for candidate in candidates)
        dangling = tuple(
            identity
            for identity in request.object_ids
            if identity in self._results.known_graph_ids and identity not in resolved
        )
        if dangling:
            fail_query(
                QueryErrorCode.DANGLING_SOURCE_REFERENCE,
                f"source evidence does not resolve for: {', '.join(dangling)}",
            )
        return self._results.page(request, candidates)

    def neighbors(self, request: ArticleGraphQueryRequest) -> QueryPage:
        self._require_operation(request, QueryOperation.NEIGHBORS)
        if not request.object_ids:
            fail_query(QueryErrorCode.INVALID_REQUEST, "neighbors requires object_ids")
        unknown = tuple(identity for identity in request.object_ids if identity not in self._nodes)
        if unknown:
            fail_query(
                QueryErrorCode.OBJECT_NOT_FOUND,
                f"neighbor seed is not a canonical node: {', '.join(unknown)}",
            )
        adjacency = self._adjacency()
        frontier: list[tuple[str, tuple[RelationHop, ...], int]] = [
            (identity, (), 0) for identity in request.object_ids
        ]
        visited = set(request.object_ids)
        ordered_ids: list[str] = []
        paths: dict[str, tuple[RelationHop, ...]] = {}
        while frontier:
            node_id, path, depth = frontier.pop(0)
            if depth >= request.budget.max_depth:
                continue
            for edge, neighbor_id in adjacency.get(node_id, ()):
                if neighbor_id in visited:
                    continue
                if len(visited) >= request.budget.max_visited_objects:
                    fail_query(QueryErrorCode.BUDGET_EXHAUSTED, "max_visited_objects reached")
                hop = self._hop(edge)
                next_path = (*path, hop)
                visited.add(neighbor_id)
                ordered_ids.append(neighbor_id)
                paths[neighbor_id] = next_path
                frontier.append((neighbor_id, next_path, depth + 1))
        candidates = self._source_index.retrieve_exact_candidates(ordered_ids)
        return self._results.page(request, candidates, relation_paths=paths)

    def trace_claim(self, request: ArticleGraphQueryRequest) -> QueryPage:
        self._require_operation(request, QueryOperation.TRACE_CLAIM)
        if not request.object_ids:
            fail_query(QueryErrorCode.INVALID_REQUEST, "trace_claim requires claim object_ids")
        ordered_ids: list[str] = []
        paths: dict[str, tuple[RelationHop, ...]] = {}
        for claim_id in request.object_ids:
            claim = self._claims.get(claim_id)
            if claim is None:
                fail_query(QueryErrorCode.OBJECT_NOT_FOUND, f"claim not found: {claim_id}")
            ordered_ids.append(claim_id)
            endpoints = tuple(
                identity
                for identity in (claim.subject_node_id, claim.object_node_id)
                if identity is not None
            )
            ordered_ids.extend(identity for identity in endpoints if identity not in ordered_ids)
            for edge in self._matching_edges(endpoints):
                if edge.edge_id not in ordered_ids:
                    ordered_ids.append(edge.edge_id)
                hop = self._hop(edge)
                paths[edge.edge_id] = (hop,)
                paths.setdefault(edge.target_node_id, (hop,))
        candidates = self._source_index.retrieve_exact_candidates(ordered_ids)
        resolved = frozenset(candidate.object_id for candidate in candidates)
        dangling = tuple(identity for identity in ordered_ids if identity not in resolved)
        if dangling:
            fail_query(
                QueryErrorCode.DANGLING_SOURCE_REFERENCE,
                f"claim trace source does not resolve for: {', '.join(dangling)}",
            )
        return self._results.page(request, candidates, relation_paths=paths)

    def expand_context(self, request: ArticleGraphQueryRequest) -> QueryPage:
        self._require_operation(request, QueryOperation.EXPAND_CONTEXT)
        seeds = self._candidates(request)
        seed_units = tuple(
            dict.fromkeys(unit_id for candidate in seeds for unit_id in candidate.source_unit_ids)
        )
        expanded_units: list[str] = list(seed_units)
        frontier = [(unit_id, 0) for unit_id in seed_units]
        visited = set(seed_units)
        while frontier:
            unit_id, depth = frontier.pop(0)
            if depth >= request.budget.max_depth:
                continue
            neighborhood = self._source_index.neighborhood(unit_id)
            adjacent = (
                neighborhood.parent_unit_id,
                *neighborhood.child_unit_ids,
                neighborhood.previous_unit_id,
                neighborhood.next_unit_id,
            )
            for candidate_id in adjacent:
                if candidate_id is None or candidate_id in visited:
                    continue
                if len(visited) >= request.budget.max_visited_objects:
                    break
                visited.add(candidate_id)
                expanded_units.append(candidate_id)
                frontier.append((candidate_id, depth + 1))
        expanded = self._source_index.retrieve_exact_candidates(expanded_units)
        return self._results.page(request, self._deduplicate((*seeds, *expanded)))

    def _candidates(
        self,
        request: ArticleGraphQueryRequest,
    ) -> tuple[SourceIndexCandidate, ...]:
        exact = self._source_index.retrieve_exact_candidates(request.object_ids)
        lexical = (
            self._source_index.retrieve_lexical_candidates(request.query)
            if request.query is not None
            else ()
        )
        return self._deduplicate((*exact, *lexical))

    @staticmethod
    def _deduplicate(
        candidates: tuple[SourceIndexCandidate, ...],
    ) -> tuple[SourceIndexCandidate, ...]:
        return tuple(
            candidate
            for index, candidate in enumerate(candidates)
            if candidate.object_id not in {item.object_id for item in candidates[:index]}
        )

    def _adjacency(self) -> dict[str, tuple[tuple[ArticleEdge, str], ...]]:
        values: dict[str, list[tuple[ArticleEdge, str]]] = {}
        for edge in self._graph.edges:
            values.setdefault(edge.source_node_id, []).append((edge, edge.target_node_id))
            values.setdefault(edge.target_node_id, []).append((edge, edge.source_node_id))
        return {
            node_id: tuple(
                sorted(items, key=lambda item: (item[0].relation, item[0].edge_id, item[1]))
            )
            for node_id, items in values.items()
        }

    def _matching_edges(self, endpoints: tuple[str, ...]) -> tuple[ArticleEdge, ...]:
        return tuple(
            edge
            for edge in sorted(self._graph.edges, key=lambda item: (item.relation, item.edge_id))
            if edge.source_node_id in endpoints and edge.target_node_id in endpoints
        )

    @staticmethod
    def _hop(edge: ArticleEdge) -> RelationHop:
        return RelationHop(
            edge_id=edge.edge_id,
            relation_kind=edge.relation,
            source_object_id=edge.source_node_id,
            target_object_id=edge.target_node_id,
        )

    @staticmethod
    def _require_operation(
        request: ArticleGraphQueryRequest,
        expected: QueryOperation,
    ) -> None:
        if request.operation is not expected:
            fail_query(
                QueryErrorCode.UNSUPPORTED_OPERATION,
                f"expected {expected.value}, got {request.operation.value}",
            )


__all__ = ["ArticleGraphQueryFailure", "ArticleGraphQueryService"]

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from readwelt.article_graph import (
    ArticleGraphQueryFailure,
    ArticleGraphQueryRequest,
    ArticleGraphQueryService,
    LocatorPrecision,
    QueryBudget,
    QueryErrorCode,
    QueryOperation,
    QueryTruncationReason,
)
from readwelt.provenance import SourceIndex
from tests.provenance.test_source_index import _build


def test_locate_returns_truthful_source_precision_and_receipt(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    document_id = build.unitization.units[0].document_id

    page = service.locate(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=QueryOperation.LOCATE,
            query="revision",
            budget=QueryBudget(max_hits=100),
        )
    )

    assert page.hits
    assert page.receipt.returned_object_ids == tuple(hit.object_id for hit in page.hits)
    assert page.usage.returned_hits == len(page.hits)
    assert all(hit.evidence for hit in page.hits)
    assert any(
        locator.page == 2 and locator.precision is LocatorPrecision.EXACT_RANGE
        for hit in page.hits
        for evidence in hit.evidence
        for locator in evidence.locators
    )


def test_evidence_resolves_graph_object_to_exact_source(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    node = build.graph.nodes[0]

    page = service.evidence(
        ArticleGraphQueryRequest(
            document_id=build.unitization.units[0].document_id,
            operation=QueryOperation.EVIDENCE,
            object_ids=(node.node_id,),
        )
    )

    assert tuple(hit.object_id for hit in page.hits) == (node.node_id,)
    assert page.hits[0].evidence
    assert all(node.node_id in item.graph_object_ids for item in page.hits[0].evidence)


def test_evidence_fails_closed_when_known_object_source_is_dangling(tmp_path: Path) -> None:
    build = _build(tmp_path)
    node = build.graph.nodes[0]
    graph = replace(
        build.graph,
        nodes=(replace(node, source_unit_ids=("unit:missing",)),),
        edges=(),
        claims=(),
    )
    index = SourceIndex.rebuild(graph, build.unitization)
    service = ArticleGraphQueryService(graph, index, build.unitization)

    with pytest.raises(ArticleGraphQueryFailure) as captured:
        service.evidence(
            ArticleGraphQueryRequest(
                document_id=build.unitization.units[0].document_id,
                operation=QueryOperation.EVIDENCE,
                object_ids=(node.node_id,),
            )
        )

    assert captured.value.error.code is QueryErrorCode.DANGLING_SOURCE_REFERENCE


def test_evidence_requires_object_ids(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)

    with pytest.raises(ArticleGraphQueryFailure) as captured:
        service.evidence(
            ArticleGraphQueryRequest(
                document_id=build.unitization.units[0].document_id,
                operation=QueryOperation.EVIDENCE,
            )
        )

    assert captured.value.error.code is QueryErrorCode.INVALID_REQUEST


def test_neighbors_are_stable_bounded_and_include_relation_paths(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    edge = build.graph.edges[0]
    request = ArticleGraphQueryRequest(
        document_id=build.unitization.units[0].document_id,
        operation=QueryOperation.NEIGHBORS,
        object_ids=(edge.source_node_id,),
        budget=QueryBudget(max_hits=100, max_depth=1),
    )

    first = service.neighbors(request)
    second = service.neighbors(request)

    assert first == second
    assert first.hits
    assert all(hit.relation_path for hit in first.hits)
    assert all(len(hit.relation_path) == 1 for hit in first.hits)


def test_trace_claim_returns_claim_endpoints_and_stable_relation_path(tmp_path: Path) -> None:
    build = _build(tmp_path)
    edge = build.graph.edges[0]
    claim = replace(
        build.graph.claims[0],
        subject_node_id=edge.source_node_id,
        predicate=edge.relation,
        object_node_id=edge.target_node_id,
    )
    graph = replace(build.graph, claims=(claim, *build.graph.claims[1:]))
    index = SourceIndex.rebuild(graph, build.unitization)
    service = ArticleGraphQueryService(graph, index, build.unitization)

    page = service.trace_claim(
        ArticleGraphQueryRequest(
            document_id=build.unitization.units[0].document_id,
            operation=QueryOperation.TRACE_CLAIM,
            object_ids=(claim.claim_id,),
            budget=QueryBudget(max_hits=100),
        )
    )

    returned = tuple(hit.object_id for hit in page.hits)
    assert returned[0] == claim.claim_id
    assert claim.subject_node_id in returned
    assert claim.object_node_id in returned
    assert any(hit.relation_path for hit in page.hits)


def test_context_expansion_adds_adjacent_source_units(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    seed = build.unitization.units[0]

    page = service.expand_context(
        ArticleGraphQueryRequest(
            document_id=seed.document_id,
            operation=QueryOperation.EXPAND_CONTEXT,
            object_ids=(seed.unit_id,),
            budget=QueryBudget(max_hits=100, max_depth=1),
        )
    )

    returned = tuple(hit.object_id for hit in page.hits)
    assert seed.unit_id in returned
    assert build.unitization.units[1].unit_id in returned


def test_continuation_is_stable_and_bound_to_normalized_query(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    base = ArticleGraphQueryRequest(
        document_id=build.unitization.units[0].document_id,
        operation=QueryOperation.LOCATE,
        query="cache",
        budget=QueryBudget(max_hits=2),
    )

    first = service.locate(base)
    assert first.continuation is not None
    second = service.locate(base.model_copy(update={"continuation": first.continuation}))

    assert set(first.receipt.returned_object_ids).isdisjoint(second.receipt.returned_object_ids)
    assert second.receipt.input_continuation_digest is not None

    changed = base.model_copy(update={"query": "revision", "continuation": first.continuation})
    with pytest.raises(ArticleGraphQueryFailure) as captured:
        service.locate(changed)
    assert captured.value.error.code is QueryErrorCode.RESTART_REQUIRED


def test_invalid_continuation_fails_with_typed_error(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)

    with pytest.raises(ArticleGraphQueryFailure) as captured:
        service.locate(
            ArticleGraphQueryRequest(
                document_id=build.unitization.units[0].document_id,
                operation=QueryOperation.LOCATE,
                query="cache",
                continuation="not-a-token",
            )
        )

    assert captured.value.error.code is QueryErrorCode.INVALID_CONTINUATION


@pytest.mark.parametrize("page_size", (1, 2, 3, 7))
def test_continuation_pages_reconstruct_one_shot_order_without_duplicates(
    tmp_path: Path,
    page_size: int,
) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    document_id = build.unitization.units[0].document_id
    one_shot = service.locate(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=QueryOperation.LOCATE,
            query="cache",
            budget=QueryBudget(max_hits=500),
        )
    )
    request = ArticleGraphQueryRequest(
        document_id=document_id,
        operation=QueryOperation.LOCATE,
        query="cache",
        budget=QueryBudget(max_hits=page_size),
    )

    observed: list[str] = []
    for _ in range(100):
        page = service.locate(request)
        observed.extend(page.receipt.returned_object_ids)
        if page.continuation is None:
            break
        request = request.model_copy(update={"continuation": page.continuation})
    else:
        pytest.fail("continuation did not terminate")

    assert observed == list(one_shot.receipt.returned_object_ids)
    assert len(observed) == len(set(observed))


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("max_visited_objects", QueryTruncationReason.MAX_VISITED_OBJECTS),
        ("max_evidence_characters", QueryTruncationReason.MAX_EVIDENCE_CHARACTERS),
        ("max_source_bytes", QueryTruncationReason.MAX_SOURCE_BYTES),
        ("max_estimated_tokens", QueryTruncationReason.MAX_ESTIMATED_TOKENS),
    ),
)
def test_resource_budgets_truncate_with_explicit_reason(
    tmp_path: Path,
    field: str,
    reason: QueryTruncationReason,
) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    document_id = build.unitization.units[0].document_id
    reference = service.locate(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=QueryOperation.LOCATE,
            query="cache",
            budget=QueryBudget(max_hits=500),
        )
    )
    first = reference.hits[0]
    limits = {
        "max_visited_objects": 1,
        "max_evidence_characters": sum(len(item.exact_text or "") for item in first.evidence),
        "max_source_bytes": sum(
            len((item.exact_text or "").encode("utf-8")) for item in first.evidence
        ),
        "max_estimated_tokens": (
            sum(len(item.exact_text or "") for item in first.evidence) + 3
        )
        // 4,
    }
    values = QueryBudget(max_hits=500).to_dict()
    values[field] = limits[field]

    page = service.locate(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=QueryOperation.LOCATE,
            query="cache",
            budget=QueryBudget.from_dict(values),
        )
    )

    assert page.truncation_reason is reason
    assert page.continuation is not None
    assert page.usage.returned_hits == 1


def test_relation_path_and_depth_budgets_are_enforced(tmp_path: Path) -> None:
    build = _build(tmp_path)
    service = ArticleGraphQueryService(build.graph, build.source_index, build.unitization)
    degree: dict[str, int] = {}
    for edge in build.graph.edges:
        degree[edge.source_node_id] = degree.get(edge.source_node_id, 0) + 1
        degree[edge.target_node_id] = degree.get(edge.target_node_id, 0) + 1
    seed = max(degree, key=degree.__getitem__)
    document_id = build.unitization.units[0].document_id

    empty = service.neighbors(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=QueryOperation.NEIGHBORS,
            object_ids=(seed,),
            budget=QueryBudget(max_hits=100, max_depth=0),
        )
    )
    assert empty.hits == ()

    bounded = service.neighbors(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=QueryOperation.NEIGHBORS,
            object_ids=(seed,),
            budget=QueryBudget(max_hits=100, max_depth=1, max_relation_paths=1),
        )
    )
    assert bounded.usage.relation_paths == 1
    assert bounded.truncation_reason is QueryTruncationReason.MAX_RELATION_PATHS

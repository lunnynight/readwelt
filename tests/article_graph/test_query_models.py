from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from readwelt.article_graph import (
    ArticleGraphQueryRequest,
    EvidenceEnvelope,
    LocatorPrecision,
    QueryBudget,
    QueryError,
    QueryErrorCode,
    QueryHit,
    QueryObjectKind,
    QueryOperation,
    QueryPage,
    QueryReceipt,
    QueryUsage,
    SourceLocator,
)


def _page() -> QueryPage:
    budget = QueryBudget(max_hits=2)
    usage = QueryUsage(returned_hits=1, source_bytes=12, estimated_tokens=3)
    locator = SourceLocator(
        precision=LocatorPrecision.SOURCE_UNIT,
        source_unit_id="unit-1",
    )
    evidence = EvidenceEnvelope(
        evidence_id="evidence-1",
        graph_object_ids=("node-1",),
        locators=(locator,),
        exact_text="source text",
        provenance_digest="a" * 64,
    )
    hit = QueryHit(
        object_id="node-1",
        object_kind=QueryObjectKind.NODE,
        rank=1,
        score=1.0,
        match_reason="exact_label",
        evidence=(evidence,),
    )
    receipt = QueryReceipt(
        receipt_id="receipt-1",
        snapshot_id="snapshot-1",
        graph_digest="b" * 64,
        operation=QueryOperation.SEARCH,
        normalized_query_digest="c" * 64,
        returned_object_ids=("node-1",),
        budget=budget,
        usage=usage,
        result_digest="d" * 64,
    )
    return QueryPage(
        snapshot_id="snapshot-1",
        graph_digest="b" * 64,
        operation=QueryOperation.SEARCH,
        normalized_query_digest="c" * 64,
        hits=(hit,),
        budget=budget,
        usage=usage,
        receipt=receipt,
    )


def test_locator_serializes_unavailable_page_precision_truthfully() -> None:
    locator = SourceLocator(
        precision=LocatorPrecision.SOURCE_UNIT,
        source_unit_id="unit-1",
    )

    encoded = locator.to_dict()

    assert encoded["page"] is None
    assert encoded["bounding_box"] is None
    assert encoded["start_offset"] is None
    assert encoded["end_offset"] is None
    assert SourceLocator.from_dict(encoded) == locator


def test_evidence_requires_source_locator_and_hit_ownership() -> None:
    with pytest.raises(ValidationError, match="at least one source locator"):
        EvidenceEnvelope(
            evidence_id="evidence-1",
            graph_object_ids=("node-1",),
            locators=(),
            provenance_digest="a" * 64,
        )

    unrelated = EvidenceEnvelope(
        evidence_id="evidence-2",
        graph_object_ids=("claim-1",),
        locators=(
            SourceLocator(
                precision=LocatorPrecision.SOURCE_UNIT,
                source_unit_id="unit-1",
            ),
        ),
        provenance_digest="b" * 64,
    )
    with pytest.raises(ValidationError, match="reference the returned object"):
        QueryHit(
            object_id="node-1",
            object_kind=QueryObjectKind.NODE,
            rank=1,
            match_reason="seed",
            evidence=(unrelated,),
        )


def test_page_and_receipt_must_describe_the_same_result() -> None:
    page = _page()
    mismatched = page.receipt.model_copy(update={"returned_object_ids": ("node-2",)})

    with pytest.raises(ValidationError, match="page and receipt disagree"):
        page.model_copy(update={"receipt": mismatched}).model_validate(
            {**page.to_dict(), "receipt": mismatched.to_dict()}
        )


def test_wire_serialization_is_stable_and_roundtrips() -> None:
    page = _page()
    first = json.dumps(page.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    decoded = QueryPage.from_dict(json.loads(first))
    second = json.dumps(
        decoded.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert decoded == page
    assert second == first
    assert QueryPage.model_json_schema()["properties"]["schema_version"]["const"] == (
        "readwelt.articlegraph-query-page.v1"
    )


def test_minimal_v1_request_remains_parseable_when_optional_fields_are_absent() -> None:
    request = ArticleGraphQueryRequest.from_dict(
        {
            "schema_version": "readwelt.articlegraph-query-request.v1",
            "document_id": "doc-1",
            "operation": "search",
        }
    )

    assert request.query is None
    assert request.object_ids == ()
    assert request.budget == QueryBudget()
    assert request.filters.source_unit_ids == ()


def test_unknown_versions_and_inconsistent_restart_errors_fail_closed() -> None:
    with pytest.raises(ValidationError, match="readwelt.articlegraph-query-request.v1"):
        ArticleGraphQueryRequest.from_dict(
            {
                "schema_version": "readwelt.articlegraph-query-request.v2",
                "document_id": "doc-1",
                "operation": "search",
            }
        )

    with pytest.raises(ValidationError, match="must set restart_required"):
        QueryError(
            code=QueryErrorCode.RESTART_REQUIRED,
            message="snapshot changed",
        )


@pytest.mark.parametrize(
    "field",
    (
        "max_hits",
        "max_visited_objects",
        "max_relation_paths",
        "max_evidence_characters",
        "max_source_bytes",
        "max_estimated_tokens",
    ),
)
def test_all_positive_query_budgets_reject_zero(field: str) -> None:
    with pytest.raises(ValidationError):
        QueryBudget(**{field: 0})


def test_depth_budget_accepts_zero_but_rejects_negative() -> None:
    assert QueryBudget(max_depth=0).max_depth == 0
    with pytest.raises(ValidationError):
        QueryBudget(max_depth=-1)

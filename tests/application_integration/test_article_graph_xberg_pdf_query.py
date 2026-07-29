from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from readwelt.application import ReadweltApplicationService
from readwelt.article_graph import (
    ArticleGraphQueryRequest,
    QueryBudget,
    QueryOperation,
)

_REPOSITORY = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = (
    _REPOSITORY / "tests" / "fixtures" / "articlegraph_query" / "xberg_zh_research_pdf.v1.json"
)


def test_real_xberg_chinese_research_pdf_query_is_source_first(tmp_path: Path) -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    source = _REPOSITORY / fixture["source_path"]
    if not source.is_file():
        pytest.skip("optional real Xberg Chinese PDF corpus checkout is unavailable")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture["source_sha256"]

    service = ReadweltApplicationService(
        tmp_path / ".readwelt",
        ingestion_backend="xberg",
        candidate_providers=(),
        dense_encoder=None,
    )
    snapshot = service.import_document(source)
    service.prepare(snapshot.document_id)
    page = service.query_article_graph(
        ArticleGraphQueryRequest(
            document_id=snapshot.document_id,
            operation=QueryOperation.SEARCH,
            query=fixture["query"],
            budget=QueryBudget(max_hits=fixture["minimum_hits"]),
        )
    )

    assert snapshot.content_digest == fixture["normalized_content_digest"]
    assert len(page.hits) >= fixture["minimum_hits"]
    assert page.hits[0].object_id == fixture["expected_first_object_id"]
    assert page.receipt.retrieval_backend == "deterministic"

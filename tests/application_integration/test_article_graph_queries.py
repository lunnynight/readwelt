from __future__ import annotations

import io
import json
from pathlib import Path

from readwelt.application import ReadweltApplicationService
from readwelt.article_graph import ArticleGraphQueryRequest, QueryBudget, QueryOperation
from readwelt.cli.main import main


def _prepared_chinese_document(tmp_path: Path) -> tuple[ReadweltApplicationService, str]:
    source = tmp_path / "研究报告.txt"
    source.write_text(
        "# 研究结论\n税收抵免使中小企业研发投入增加。\n\n"
        "# 研究方法\n研究使用匹配样本与稳健性检验。",
        encoding="utf-8",
    )
    service = ReadweltApplicationService(
        tmp_path / ".readwelt",
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    snapshot = service.import_document(source)
    service.prepare(snapshot.document_id)
    return service, snapshot.document_id


def test_python_query_entry_point_reads_verified_persisted_artifacts(tmp_path: Path) -> None:
    service, document_id = _prepared_chinese_document(tmp_path)

    page = service.query_article_graph(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=QueryOperation.SEARCH,
            query="研发投入",
            budget=QueryBudget(max_hits=20),
        )
    )

    assert page.hits
    assert page.snapshot_id
    assert page.receipt.graph_digest == page.graph_digest
    assert page.receipt.returned_object_ids == tuple(hit.object_id for hit in page.hits)


def test_cli_and_python_use_equivalent_normalized_requests_and_ordering(tmp_path: Path) -> None:
    service, document_id = _prepared_chinese_document(tmp_path)
    request = ArticleGraphQueryRequest(
        document_id=document_id,
        operation=QueryOperation.LOCATE,
        query="稳健性检验",
        budget=QueryBudget(max_hits=20),
    )
    python_page = service.query_article_graph(request)
    output = io.StringIO()

    exit_code = main(
        [
            "articlegraph",
            "query",
            "locate",
            document_id,
            "--query",
            "稳健性检验",
            "--max-hits",
            "20",
            "--project",
            str(service.root),
            "--json",
        ],
        service=service,
        stdout=output,
    )

    assert exit_code == 0
    cli_page = json.loads(output.getvalue())
    assert cli_page == python_page.to_dict()
    assert cli_page["receipt"]["returned_object_ids"] == [
        hit.object_id for hit in python_page.hits
    ]


def test_cli_query_failure_has_stable_machine_code(tmp_path: Path) -> None:
    service = ReadweltApplicationService(
        tmp_path / ".readwelt",
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    error = io.StringIO()

    exit_code = main(
        [
            "articlegraph",
            "query",
            "search",
            "missing-document",
            "--query",
            "证据",
            "--json",
        ],
        service=service,
        stderr=error,
    )

    assert exit_code == 2
    assert json.loads(error.getvalue())["error"]["code"] == "document_not_found"

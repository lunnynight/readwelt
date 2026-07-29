from __future__ import annotations

from pathlib import Path

import pytest

from readwelt.application import ReadweltApplicationService


def _service_with_graph(
    project: Path,
    document_id: str,
    *,
    node_count: int,
) -> ReadweltApplicationService:
    service = ReadweltApplicationService(project, ingestion_backend="plain_text")
    reference = service._artifacts.put_json(
        {
            "schema_version": "article-graph.v4",
            "mentions": [],
            "nodes": [
                {"node_id": f"node-{index}", "source_unit_ids": [f"unit-{index}"]}
                for index in range(node_count)
            ],
            "edges": [],
            "claims": [],
        },
        artifact_type="article_graph",
        schema_version="article-graph.v4",
    )
    service._manifests.write(
        service._layout.document_manifest(document_id),
        {
            "schema_version": "1",
            "document_id": document_id,
            "article_graph_artifact": reference,
        },
    )
    return service


def test_article_graph_pages_are_stable_complete_and_non_overlapping(tmp_path: Path) -> None:
    service = _service_with_graph(tmp_path / "project", "doc-1", node_count=7)
    first = service.get_article_graph_page("doc-1", limit=3)
    repeated = service.get_article_graph_page("doc-1", limit=3)

    assert first == repeated
    assert first["schema_version"] == "readwelt.article-graph-page.v1"
    assert first["total"] == 7

    items: list[dict[str, object]] = []
    cursors: set[str] = set()
    page = first
    while True:
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert cursor not in cursors
        cursors.add(cursor)
        page = service.get_article_graph_page("doc-1", limit=3, cursor=cursor)

    assert [item["node_id"] for item in items] == [f"node-{index}" for index in range(7)]
    assert len({item["node_id"] for item in items}) == 7
    assert page["next_cursor"] is None


def test_article_graph_cursor_is_bound_and_tamper_evident(tmp_path: Path) -> None:
    service = _service_with_graph(tmp_path / "project", "doc-1", node_count=3)
    _service_with_graph(tmp_path / "project", "doc-2", node_count=4)
    cursor = service.get_article_graph_page("doc-1", limit=1)["next_cursor"]
    assert isinstance(cursor, str)

    with pytest.raises(ValueError, match="stale or incompatible"):
        service.get_article_graph_page("doc-2", limit=1, cursor=cursor)
    with pytest.raises(ValueError, match="integrity"):
        service.get_article_graph_page("doc-1", limit=1, cursor=cursor[:-1] + "0")
    with pytest.raises(ValueError, match="encoding"):
        service.get_article_graph_page("doc-1", limit=1, cursor="not-a-cursor")


def test_article_graph_empty_collection_is_a_terminal_page(tmp_path: Path) -> None:
    service = _service_with_graph(tmp_path / "project", "doc-empty", node_count=0)

    page = service.get_article_graph_page("doc-empty", collection="nodes", limit=10)

    assert page["items"] == []
    assert page["total"] == 0
    assert page["next_cursor"] is None

"""Thin ArticleGraph public methods mixed into the application facade."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from readwelt.article_graph import ArticleGraphQueryRequest, QueryPage


class ArticleGraphApplicationMixin:
    def get_article_graph_page(
        self,
        document_id: str,
        *,
        collection: str = "nodes",
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        from .article_graph_pages import article_graph_page

        return article_graph_page(
            self,  # type: ignore[arg-type]
            document_id,
            collection=collection,
            limit=limit,
            cursor=cursor,
        )

    def query_article_graph(
        self,
        request: ArticleGraphQueryRequest | Mapping[str, object],
    ) -> QueryPage:
        from .article_graph_queries import query_article_graph

        return query_article_graph(self, request)  # type: ignore[arg-type]


__all__ = ["ArticleGraphApplicationMixin"]

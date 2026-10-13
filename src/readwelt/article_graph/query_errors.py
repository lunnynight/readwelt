"""Typed failures shared by ArticleGraph query components."""

from __future__ import annotations

from typing import Never

from .query_models import QueryError, QueryErrorCode


class ArticleGraphQueryFailure(RuntimeError):
    def __init__(self, error: QueryError) -> None:
        super().__init__(error.message)
        self.error = error

    @property
    def code(self) -> str:
        """Stable machine-readable code used by public adapters."""
        return self.error.code.value


def fail_query(code: QueryErrorCode, message: str) -> Never:
    raise ArticleGraphQueryFailure(
        QueryError(
            code=code,
            message=message,
            restart_required=code is QueryErrorCode.RESTART_REQUIRED,
        )
    )

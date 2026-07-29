"""Query-first evidence selection used by six-stage compatibility adapters."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.article_graph import (
    ArticleGraphBuildResult,
    ArticleGraphQueryRequest,
    ArticleGraphQueryService,
    QueryOperation,
    QueryPage,
)
from readwelt.domain import ReadingStage

from .stage_query_policy import query_policy_for_stage


@dataclass(frozen=True, slots=True)
class StageQueryBootstrap:
    page: QueryPage
    critical_range_ids: tuple[str, ...]
    critical_element_ids: tuple[str, ...]


def build_stage_query_bootstrap(
    graph_build: ArticleGraphBuildResult,
    stage: ReadingStage,
    *,
    document_id: str,
    query_text: str,
) -> StageQueryBootstrap:
    """Select source evidence through Query Plane before projecting a StageView adapter."""
    policy = query_policy_for_stage(stage)
    operation = QueryOperation.SEARCH
    task_intent = policy.allowed_intents[0]
    policy.validate(operation, task_intent)
    page = ArticleGraphQueryService(
        graph_build.graph,
        graph_build.source_index,
        graph_build.unitization,
    ).search(
        ArticleGraphQueryRequest(
            document_id=document_id,
            operation=operation,
            query=query_text,
            consumer_stage=stage.value,
            task_intent=task_intent,
            budget=policy.default_budget,
        )
    )
    locators = (
        locator
        for hit in page.hits
        for evidence in hit.evidence
        for locator in evidence.locators
    )
    range_ids: list[str] = []
    element_ids: list[str] = []
    for locator in locators:
        if locator.source_range_id is not None and locator.source_range_id not in range_ids:
            range_ids.append(locator.source_range_id)
        if locator.source_element_id is not None and locator.source_element_id not in element_ids:
            element_ids.append(locator.source_element_id)
    return StageQueryBootstrap(page, tuple(range_ids), tuple(element_ids))


__all__ = ["StageQueryBootstrap", "build_stage_query_bootstrap"]

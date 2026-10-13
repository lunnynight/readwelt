"""Six-stage ArticleGraph query permissions and default budgets."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.article_graph import QueryBudget, QueryOperation
from readwelt.domain import ReadingStage


@dataclass(frozen=True, slots=True)
class StageQueryPolicy:
    stage: ReadingStage
    allowed_operations: tuple[QueryOperation, ...]
    allowed_intents: tuple[str, ...]
    default_budget: QueryBudget

    def validate(self, operation: QueryOperation, task_intent: str) -> None:
        if operation not in self.allowed_operations:
            raise ValueError(f"{operation.value} is not allowed for {self.stage.value}")
        if task_intent not in self.allowed_intents:
            raise ValueError(f"{task_intent!r} is not an allowed intent for {self.stage.value}")


_SOURCE_OPERATIONS = (
    QueryOperation.SEARCH,
    QueryOperation.LOCATE,
    QueryOperation.EVIDENCE,
    QueryOperation.EXPAND_CONTEXT,
)
_GRAPH_OPERATIONS = (
    QueryOperation.SEARCH,
    QueryOperation.LOCATE,
    QueryOperation.EVIDENCE,
    QueryOperation.NEIGHBORS,
    QueryOperation.TRACE_CLAIM,
    QueryOperation.EXPAND_CONTEXT,
)

STAGE_QUERY_POLICIES = {
    ReadingStage.MAINLINE: StageQueryPolicy(
        ReadingStage.MAINLINE,
        _SOURCE_OPERATIONS,
        ("find_main_claims", "locate_support"),
        QueryBudget(max_hits=40, max_depth=1, max_estimated_tokens=4_096),
    ),
    ReadingStage.STRUCTURE: StageQueryPolicy(
        ReadingStage.STRUCTURE,
        (*_SOURCE_OPERATIONS, QueryOperation.NEIGHBORS),
        ("map_structure", "trace_relations"),
        QueryBudget(max_hits=60, max_depth=2, max_estimated_tokens=6_144),
    ),
    ReadingStage.DECOMPRESSION: StageQueryPolicy(
        ReadingStage.DECOMPRESSION,
        _GRAPH_OPERATIONS,
        ("unpack_reasoning", "trace_claim"),
        QueryBudget(max_hits=80, max_depth=3, max_estimated_tokens=8_192),
    ),
    ReadingStage.AUTHOR_MODEL: StageQueryPolicy(
        ReadingStage.AUTHOR_MODEL,
        _GRAPH_OPERATIONS,
        ("model_author", "trace_assumptions"),
        QueryBudget(max_hits=70, max_depth=3, max_estimated_tokens=8_192),
    ),
    ReadingStage.BOUNDARIES: StageQueryPolicy(
        ReadingStage.BOUNDARIES,
        _GRAPH_OPERATIONS,
        ("test_boundaries", "find_counterevidence"),
        QueryBudget(max_hits=80, max_depth=3, max_estimated_tokens=8_192),
    ),
    ReadingStage.TRANSFER: StageQueryPolicy(
        ReadingStage.TRANSFER,
        _GRAPH_OPERATIONS,
        ("evaluate_transfer", "locate_analogies"),
        QueryBudget(max_hits=60, max_depth=2, max_estimated_tokens=6_144),
    ),
}


def query_policy_for_stage(stage: ReadingStage | str) -> StageQueryPolicy:
    return STAGE_QUERY_POLICIES[ReadingStage(stage)]


__all__ = ["STAGE_QUERY_POLICIES", "StageQueryPolicy", "query_policy_for_stage"]

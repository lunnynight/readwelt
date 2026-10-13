from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from readwelt.application.run_store import ApplicationRunStore
from readwelt.application.stage_query_policy import STAGE_QUERY_POLICIES, query_policy_for_stage
from readwelt.article_graph import (
    ArticleGraphQueryRequest,
    ArticleGraphQueryService,
    QueryOperation,
)
from readwelt.domain import (
    EpistemicStatus,
    ExecutionStatus,
    ModelStatus,
    PublicationStatus,
    ReadingRun,
    ReadingStage,
)
from readwelt.providers import ProviderSelection
from readwelt.storage import ArtifactStore, ProjectLayout
from tests.provenance.test_source_index import _build


def test_every_stage_has_explicit_intents_operations_and_bounded_defaults() -> None:
    assert set(STAGE_QUERY_POLICIES) == set(ReadingStage)
    for stage in ReadingStage:
        policy = query_policy_for_stage(stage)
        assert policy.allowed_operations
        assert policy.allowed_intents
        assert policy.default_budget.max_hits <= 80
        assert policy.default_budget.max_depth <= 3
        assert policy.default_budget.max_estimated_tokens <= 8_192
        policy.validate(policy.allowed_operations[0], policy.allowed_intents[0])


def test_stage_policy_rejects_unapproved_intent_and_operation() -> None:
    policy = query_policy_for_stage(ReadingStage.MAINLINE)
    with pytest.raises(ValueError, match="not an allowed intent"):
        policy.validate(QueryOperation.SEARCH, "invent_a_thesis")
    with pytest.raises(ValueError, match="not allowed"):
        policy.validate(QueryOperation.TRACE_CLAIM, "find_main_claims")


def test_query_receipt_roundtrips_through_cas_and_run_manifest(tmp_path: Path) -> None:
    build = _build(tmp_path)
    stage = ReadingStage.MAINLINE
    policy = query_policy_for_stage(stage)
    page = ArticleGraphQueryService(
        build.graph,
        build.source_index,
        build.unitization,
    ).search(
        ArticleGraphQueryRequest(
            document_id=build.unitization.units[0].document_id,
            operation=QueryOperation.SEARCH,
            query="revision",
            consumer_stage=stage.value,
            task_intent="find_main_claims",
            budget=policy.default_budget,
        )
    )
    layout = ProjectLayout.resolve(".readwelt", base_directory=tmp_path)
    layout.initialize()
    store = ApplicationRunStore(layout, ArtifactStore(layout))
    run = ReadingRun(
        run_id="run_query_receipt",
        schema_version="1",
        snapshot_id=build.graph.snapshot_id,
        execution_status=ExecutionStatus.RUNNING,
        epistemic_status=EpistemicStatus.UNDERDETERMINED,
        model_status=ModelStatus.READY,
        publication_status=PublicationStatus.WITHHELD,
        current_task="six_stage_reading",
        artifacts=(),
        warnings=(),
        created_at=datetime.now(UTC),
    )
    store.write(
        run,
        pipeline_policy="readwelt-six-stage-v1",
        selection=ProviderSelection.build(primary="local"),
        purpose="receipt persistence",
        token_budget=128,
        hard_serialized_token_budget=None,
    )

    first_ref = store.append_query_receipt(run.run_id, stage, page.receipt)
    repeated_ref = store.append_query_receipt(run.run_id, stage, page.receipt)

    assert first_ref == repeated_ref
    assert store.load_query_receipts(run.run_id) == (page.receipt,)
    assert store.load_query_receipts(run.run_id, stage) == (page.receipt,)

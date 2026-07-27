from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from readwelt.application.run_store import ApplicationRunStore
from readwelt.domain import (
    EpistemicStatus,
    ExecutionStatus,
    ModelStatus,
    PublicationStatus,
    ReadingRun,
    ReadingStage,
    StageArtifact,
    StageInputState,
    StageInputStatus,
)
from readwelt.providers import ProviderSelection
from readwelt.storage import ArtifactStore, ProjectLayout


def test_provisional_stage_page_is_not_loaded_as_settled_prefix(tmp_path) -> None:
    layout = ProjectLayout.resolve(".readwelt", base_directory=tmp_path)
    layout.initialize()
    store = ApplicationRunStore(layout, ArtifactStore(layout))
    run = ReadingRun(
        run_id="run_stage_input",
        schema_version="1",
        snapshot_id="snapshot_stage_input",
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
        purpose="test bounded settlement",
        token_budget=128,
        hard_serialized_token_budget=None,
    )
    provisional = _artifact(StageInputStatus.PROVISIONAL)

    store.append_stage_artifact(run.run_id, provisional)

    assert store.load_stage_artifacts(run.run_id) == ()
    assert store.load_provisional_stage_artifacts(run.run_id) == (provisional,)

    complete = replace(
        _artifact(StageInputStatus.COMPLETE),
        artifact_id="stage_artifact_complete",
        content_digest="sha256:" + "5" * 64,
    )
    store.append_stage_artifact(run.run_id, complete)

    assert store.load_stage_artifacts(run.run_id) == (complete,)
    assert store.load_provisional_stage_artifacts(run.run_id) == (provisional,)


def _artifact(status: StageInputStatus) -> StageArtifact:
    continuation = "sha256:" + "4" * 64 if status is StageInputStatus.PROVISIONAL else None
    return StageArtifact(
        artifact_id="stage_artifact_page",
        run_id="run_stage_input",
        stage=ReadingStage.MAINLINE,
        claims=(),
        gaps=(),
        warnings=(),
        input_artifact_ids=(),
        provider="test",
        model="test",
        status=EpistemicStatus.UNDERDETERMINED,
        content_digest="sha256:" + "3" * 64,
        input_state=StageInputState(
            status=status,
            stage_view_digest="sha256:" + "1" * 64,
            coverage_digest="sha256:" + "2" * 64,
            continuation_digest=continuation,
            blocking_reasons=(),
            unresolved_critical_ids=(),
        ),
    )

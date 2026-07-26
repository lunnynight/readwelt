"""Immutable run state as persisted by the local runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from readwelt.domain.artifacts import ArtifactRef
from readwelt.domain.status import (
    EpistemicStatus,
    ExecutionStatus,
    ModelStatus,
    PublicationStatus,
)


@dataclass(frozen=True, slots=True)
class ReadingRun:
    run_id: str
    schema_version: str
    snapshot_id: str
    execution_status: ExecutionStatus
    epistemic_status: EpistemicStatus
    model_status: ModelStatus
    publication_status: PublicationStatus
    current_task: str
    artifacts: tuple[ArtifactRef, ...]
    warnings: tuple[str, ...]
    created_at: datetime
    completed_at: datetime | None = None
    parent_run_id: str | None = None
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "1":
            raise ValueError(f"unsupported run schema: {self.schema_version}")
        if self.execution_status is ExecutionStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed run must have completed_at")
        if self.execution_status is not ExecutionStatus.COMPLETED and self.completed_at is not None:
            raise ValueError("only completed runs may have completed_at")

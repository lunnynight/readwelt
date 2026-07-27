"""Persist application-run state and append its lifecycle events."""

from __future__ import annotations

from datetime import UTC, datetime

from readwelt.domain import ReadingRun
from readwelt.providers import ProviderSelection
from readwelt.storage import EventLog, ProjectLayout

from .run_store import ApplicationRunStore


def write_application_run(
    run_store: ApplicationRunStore,
    run: ReadingRun,
    *,
    pipeline_policy: str,
    selection: ProviderSelection,
    purpose: str,
    token_budget: int,
    hard_serialized_token_budget: int | None,
) -> None:
    run_store.write(
        run,
        pipeline_policy=pipeline_policy,
        selection=selection,
        purpose=purpose,
        token_budget=token_budget,
        hard_serialized_token_budget=hard_serialized_token_budget,
    )


def emit_run_event(
    events: EventLog,
    layout: ProjectLayout,
    run_id: str,
    event_type: str,
    task: str,
) -> None:
    events.append(
        layout.run_events(run_id),
        {
            "schema_version": "1",
            "event_type": event_type,
            "run_id": run_id,
            "task": task,
            "occurred_at": datetime.now(UTC),
        },
    )

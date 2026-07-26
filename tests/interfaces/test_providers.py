from __future__ import annotations

import asyncio

import pytest

from readwelt.providers.contracts import (
    ProviderConflictError,
    ProviderSelection,
    StageCandidate,
)
from readwelt.providers.external_agent import ExternalAgentAdapter

from .fakes import FakeService


def test_primary_provider_conflict_is_explicit() -> None:
    with pytest.raises(ProviderConflictError) as caught:
        ProviderSelection.build(mode="primary", primary="local", candidates=["api"])

    assert caught.value.code == "provider_conflict"


def test_compare_requires_primary_and_candidate() -> None:
    selection = ProviderSelection.build(mode="compare", primary="local", candidates=["agent"])

    assert selection.to_dict() == {
        "mode": "compare",
        "primary": "local",
        "candidates": ["agent"],
    }


def test_agent_pull_and_submit_are_versioned(tmp_path) -> None:
    service = FakeService(tmp_path)
    adapter = ExternalAgentAdapter(service)

    request = asyncio.run(adapter.pull("run-1", "stage-3"))
    assert request["schema_version"] == "1"
    assert request["evidence_packet"]["anchors"] == ["a-1"]

    candidate = StageCandidate(
        schema_version="1",
        run_id="run-1",
        stage="stage-3",
        candidate={"claims": []},
        provider="codex",
    )
    result = asyncio.run(adapter.submit("run-1", "stage-3", candidate.to_dict()))
    assert result["accepted"] is True


def test_agent_submission_cannot_change_target(tmp_path) -> None:
    adapter = ExternalAgentAdapter(FakeService(tmp_path))
    candidate = StageCandidate(
        schema_version="1",
        run_id="other-run",
        stage="stage-3",
        candidate={},
        provider="claude-code",
    )

    with pytest.raises(ValueError, match="must match"):
        asyncio.run(adapter.submit("run-1", "stage-3", candidate.to_dict()))

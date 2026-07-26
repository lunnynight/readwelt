from __future__ import annotations

import asyncio

import pytest

from readwelt.providers import (
    AgentInputRequired,
    ExternalAgentMailboxProvider,
    ProviderContractError,
    StageCandidate,
    StageRequest,
)
from readwelt.storage import ProjectLayout


def test_agent_mailbox_pauses_then_replays_candidate(tmp_path) -> None:
    layout = ProjectLayout.resolve(".readwelt", base_directory=tmp_path)
    layout.initialize()
    mailbox = ExternalAgentMailboxProvider(layout)
    request = StageRequest(
        schema_version="1",
        run_id="run-1",
        stage="mainline",
        evidence_packet={"anchors": []},
    )

    response_schema = {"type": "object", "required": ["claims"]}
    with pytest.raises(AgentInputRequired):
        asyncio.run(mailbox.generate(request, response_schema))

    frozen_request = mailbox.pull("run-1", "mainline")
    assert frozen_request.run_id == request.run_id
    assert frozen_request.response_schema == response_schema
    request_digest = frozen_request.provenance["request_digest"]
    candidate = StageCandidate(
        schema_version="1",
        run_id="run-1",
        stage="mainline",
        candidate={"claims": []},
        provider="codex",
        model="gpt",
        provenance={"request_digest": request_digest},
    )
    assert mailbox.submit(candidate) == candidate
    assert asyncio.run(mailbox.generate(request, response_schema)) == candidate


def test_agent_mailbox_rejects_path_escape(tmp_path) -> None:
    layout = ProjectLayout.resolve(".readwelt", base_directory=tmp_path)
    layout.initialize()
    mailbox = ExternalAgentMailboxProvider(layout)

    with pytest.raises(ProviderContractError, match="unsafe run_id"):
        mailbox.pull("../outside", "mainline")

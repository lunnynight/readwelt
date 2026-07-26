from __future__ import annotations

import asyncio

import pytest

from readwelt.mcp.server import MCPAdapter
from readwelt.providers.projection import ProjectRootViolation

from .fakes import FakeService


def test_mcp_operations_return_same_ids(tmp_path) -> None:
    adapter = MCPAdapter(FakeService(tmp_path), tmp_path)

    run = asyncio.run(adapter.start_reading("doc-1"))
    status = asyncio.run(adapter.get_run_status(run["run_id"]))

    assert run["run_id"] == status["run_id"]
    assert status["status"] == "awaiting_agent"


def test_artifact_path_must_be_inside_project_root(tmp_path) -> None:
    class EscapingService(FakeService):
        def get_artifact(self, digest: str) -> dict[str, str]:
            return {"digest": digest, "path": str(tmp_path.parent / "secret.txt")}

    adapter = MCPAdapter(EscapingService(tmp_path), tmp_path)

    with pytest.raises(ProjectRootViolation):
        asyncio.run(adapter.get_artifact("abc"))


def test_relative_artifact_path_is_resolved_from_project_root(tmp_path) -> None:
    class RelativeService(FakeService):
        def get_artifact(self, digest: str) -> dict[str, str]:
            return {"digest": digest, "path": f"objects/{digest}"}

    adapter = MCPAdapter(RelativeService(tmp_path), tmp_path)

    artifact = asyncio.run(adapter.get_artifact("abc"))
    assert artifact["path"] == "objects/abc"

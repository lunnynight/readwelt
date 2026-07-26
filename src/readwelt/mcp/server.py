"""Official-SDK MCP adapter.

Importing this module does not require MCP.  The dependency is loaded only when
``create_mcp_server`` is called.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from readwelt.providers.contracts import ProviderSelection
from readwelt.providers.external_agent import ExternalAgentAdapter
from readwelt.providers.projection import (
    compact_result,
    ensure_within_project,
    resolve_project_root,
    to_jsonable,
)
from readwelt.providers.service_port import invoke, invoke_read, load_application_service


class MCPUnavailable(RuntimeError):
    code = "optional_dependency_missing"


def _artifact_uri(digest: str) -> str:
    return f"readwelt://artifacts/{digest}"


class MCPAdapter:
    """SDK-independent MCP operation implementations, useful for testing."""

    def __init__(self, service: object, project_root: Path):
        self.service = service
        self.project_root = project_root.resolve()
        self.agent = ExternalAgentAdapter(service)

    async def read_document(
        self,
        source: str,
        provider: str | None = None,
        provider_mode: str = "primary",
        candidate_providers: list[str] | None = None,
    ) -> Any:
        self._validate_source(source)
        selection = ProviderSelection.build(
            mode=provider_mode,
            primary=provider,
            candidates=candidate_providers or (),
        )
        return to_jsonable(await invoke_read(self.service, source, selection))

    async def import_document(self, source: str) -> Any:
        self._validate_source(source)
        return to_jsonable(await invoke(self.service, "import_document", source))

    async def prepare_document(self, document_id: str) -> Any:
        return to_jsonable(await invoke(self.service, "prepare", document_id))

    async def batch_prepare(
        self,
        sources: list[str],
        concurrency: int = 8,
    ) -> Any:
        for source in sources:
            self._validate_source(source)
        return to_jsonable(
            await invoke(
                self.service,
                "batch_prepare",
                sources,
                concurrency=concurrency,
            )
        )

    async def start_reading(
        self,
        document_id: str,
        provider: str | None = None,
        provider_mode: str = "primary",
        candidate_providers: list[str] | None = None,
    ) -> Any:
        return await self.read_document(
            document_id,
            provider=provider,
            provider_mode=provider_mode,
            candidate_providers=candidate_providers,
        )

    async def get_run_status(self, run_id: str) -> Any:
        return to_jsonable(await invoke(self.service, "get_run_status", run_id))

    async def get_artifact(self, digest: str) -> Any:
        result = to_jsonable(await invoke(self.service, "get_artifact", digest))
        if isinstance(result, Mapping) and result.get("path"):
            ensure_within_project(self.project_root, str(result["path"]))
        return compact_result(result, resource_uri=_artifact_uri(digest))

    async def pull_stage_request(self, run_id: str, stage: str) -> Any:
        return await self.agent.pull(run_id, stage)

    async def submit_stage_candidate(
        self, run_id: str, stage: str, candidate: Mapping[str, Any]
    ) -> Any:
        return await self.agent.submit(run_id, stage, candidate)

    async def start_agent_reading(
        self,
        source: str,
        purpose: str = "完整逆向阅读",
        token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        """Start a provider-free run for any external Agent host."""

        self._validate_source(source)
        return await self.agent.start(
            source,
            purpose=purpose,
            token_budget=token_budget,
            idempotency_key=idempotency_key,
        )

    async def get_agent_turn(self, run_id: str) -> Any:
        """Return the current actionable turn for a resumable Agent run."""

        return await self.agent.current(run_id)

    async def submit_agent_turn(
        self,
        run_id: str,
        candidate: Mapping[str, Any],
        agent_name: str,
        model: str | None = None,
        agent_provenance: Mapping[str, Any] | None = None,
    ) -> Any:
        """Submit one stage payload and immediately return the next turn."""

        return await self.agent.advance(
            run_id,
            candidate,
            agent_name=agent_name,
            model=model,
            agent_provenance=agent_provenance,
        )

    def _validate_source(self, source: str) -> None:
        candidate = Path(source)
        if candidate.exists():
            ensure_within_project(self.project_root.parent, candidate)


def create_mcp_server(
    service: object | None = None,
    *,
    project_root: str | Path = ".readwelt",
) -> Any:
    """Create a FastMCP server using the official MCP Python SDK."""

    try:
        from mcp.server.fastmcp import FastMCP
    except (ImportError, ModuleNotFoundError) as exc:
        raise MCPUnavailable("MCP support requires the optional dependency mcp>=1.27,<2") from exc

    root = resolve_project_root(project_root)
    operations = MCPAdapter(service or load_application_service(root), root)
    server = FastMCP("Readwelt")

    server.tool(
        name="read_document",
        description="Import, prepare, and start a Readwelt reading run.",
    )(operations.read_document)
    server.tool(
        name="import_document",
        description="Import a source into the local Readwelt project.",
    )(operations.import_document)
    server.tool(
        name="prepare_document",
        description="Build semantic preparation artifacts for a document.",
    )(operations.prepare_document)
    server.tool(
        name="batch_prepare",
        description="Bounded, resumable import and semantic preparation without model calls.",
    )(operations.batch_prepare)
    server.tool(
        name="start_reading",
        description="Start a reading run for an existing document.",
    )(operations.start_reading)
    server.tool(
        name="get_run_status",
        description="Return the current run stage, status, and gaps.",
    )(operations.get_run_status)
    server.tool(
        name="get_artifact",
        description="Return a small artifact or a stable resource reference.",
    )(operations.get_artifact)
    server.tool(
        name="pull_stage_request",
        description="Pull a StageRequest awaiting an external agent candidate.",
    )(operations.pull_stage_request)
    server.tool(
        name="submit_stage_candidate",
        description="Submit an external-agent StageCandidate for validation.",
    )(operations.submit_stage_candidate)
    server.tool(
        name="start_agent_reading",
        description=(
            "Start a host-neutral six-stage reading with no internal model provider "
            "and return the first actionable Agent turn."
        ),
    )(operations.start_agent_reading)
    server.tool(
        name="get_agent_turn",
        description=(
            "Resume a host-neutral Agent run and return either its pending StageRequest "
            "or final output artifacts."
        ),
    )(operations.get_agent_turn)
    server.tool(
        name="submit_agent_turn",
        description=(
            "Submit only the current stage candidate payload; Readwelt binds run, stage, "
            "and request provenance, then returns the next turn or final outputs."
        ),
    )(operations.submit_agent_turn)

    server.resource(
        "readwelt://runs/{run_id}/stage-request/{stage}",
        name="stage_request",
        description="Versioned StageRequest and EvidencePacket for an agent stage.",
    )(operations.pull_stage_request)
    server.resource(
        "readwelt://artifacts/{digest}",
        name="artifact",
        description="A project-root-bounded Readwelt artifact.",
    )(operations.get_artifact)
    return server


def run_stdio(
    service: object | None = None,
    *,
    project_root: str | Path = ".readwelt",
) -> None:
    server = create_mcp_server(service, project_root=project_root)
    server.run(transport="stdio")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="readwelt-mcp")
    parser.add_argument(
        "--project",
        default=os.environ.get("READWELT_PROJECT_ROOT", ".readwelt"),
        help="Readwelt project directory; defaults to READWELT_PROJECT_ROOT or .readwelt",
    )
    args = parser.parse_args(argv)
    run_stdio(project_root=args.project)

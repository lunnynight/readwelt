"""Pull/submit adapter for Claude Code, Codex, and other external agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import (
    ProviderContractError,
    ProviderSelection,
    StageCandidate,
    StageRequest,
)
from .projection import compact_result, to_jsonable
from .service_port import invoke, invoke_read


def stage_request_uri(run_id: str, stage: str) -> str:
    return f"readwelt://runs/{run_id}/stage-request/{stage}"


class ExternalAgentAdapter:
    """Host-neutral reading loop shared by MCP, HTTP, CLI, and SDK callers."""

    def __init__(self, service: object):
        self._service = service

    async def start(
        self,
        source: str,
        *,
        purpose: str = "完整逆向阅读",
        token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Start an agent-owned run and return its first actionable turn."""

        options: dict[str, Any] = {"purpose": purpose}
        if token_budget is not None:
            options["token_budget"] = token_budget
        if idempotency_key is not None:
            options["idempotency_key"] = idempotency_key
        run = await invoke_read(
            self._service,
            source,
            ProviderSelection.build(mode="agent_takeover"),
            **options,
        )
        return await self._turn(run)

    async def current(self, run_id: str) -> dict[str, Any]:
        """Resume any agent-owned run without host-specific session state."""

        run = await invoke(self._service, "get_run_status", run_id)
        return await self._turn(run)

    async def advance(
        self,
        run_id: str,
        candidate: Mapping[str, Any],
        *,
        agent_name: str,
        model: str | None = None,
        agent_provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Bind one candidate to the pending turn and return the next turn."""

        if not agent_name.strip():
            raise ProviderContractError("agent_name is required")
        run = to_jsonable(await invoke(self._service, "get_run_status", run_id))
        if not isinstance(run, Mapping):
            raise ProviderContractError("run status projection must be an object")
        stage = _pending_stage(run)
        request_value = await invoke(self._service, "pull_stage_request", run_id, stage)
        request = StageRequest.from_mapping(to_jsonable(request_value))
        provenance = {
            **dict(agent_provenance or {}),
            "request_digest": request.provenance.get("request_digest"),
            "agent_protocol": "readwelt.agent-turn.v1",
        }
        envelope = StageCandidate(
            schema_version=request.schema_version,
            run_id=run_id,
            stage=stage,
            candidate=dict(candidate),
            provider=agent_name.strip(),
            model=model,
            provenance=provenance,
        )
        advanced = await invoke(
            self._service,
            "submit_stage_candidate",
            run_id,
            stage,
            envelope.to_dict(),
        )
        return await self._turn(advanced)

    async def pull(self, run_id: str, stage: str) -> dict[str, Any]:
        raw = await invoke(self._service, "pull_stage_request", run_id, stage)
        projected = to_jsonable(raw)
        request = StageRequest.from_mapping(projected)
        if request.run_id != run_id or request.stage != stage:
            raise ProviderContractError(
                "application service returned a StageRequest for a different run or stage"
            )
        uri = request.resource_uri or stage_request_uri(run_id, stage)
        compacted = compact_result(request.to_dict(), resource_uri=uri)
        if not isinstance(compacted, dict):
            raise ProviderContractError("StageRequest projection must be an object")
        return compacted

    async def submit(self, run_id: str, stage: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        candidate = StageCandidate.from_mapping(payload)
        if candidate.run_id != run_id or candidate.stage != stage:
            raise ProviderContractError(
                "StageCandidate run_id and stage must match the submission target"
            )
        result = await invoke(
            self._service,
            "submit_stage_candidate",
            run_id,
            stage,
            candidate.to_dict(),
        )
        projected = to_jsonable(result)
        if not isinstance(projected, dict):
            raise ProviderContractError("candidate submission result must be an object")
        return projected

    async def _turn(self, raw_run: object) -> dict[str, Any]:
        run = to_jsonable(raw_run)
        if not isinstance(run, Mapping):
            raise ProviderContractError("run status projection must be an object")
        run_id = str(run.get("run_id", "")).strip()
        if not run_id:
            raise ProviderContractError("run status has no run_id")
        execution_status = str(run.get("execution_status", run.get("status", "")))
        current_task = str(run.get("current_task", ""))
        base: dict[str, Any] = {
            "schema_version": "readwelt.agent-turn.v1",
            "run_id": run_id,
            "execution_status": execution_status,
            "epistemic_status": run.get("epistemic_status"),
            "current_task": current_task,
        }
        if current_task.startswith("awaiting_agent:"):
            stage = _pending_stage(run)
            base.update(
                {
                    "action": "generate_stage_candidate",
                    "stage": stage,
                    "request": await self.pull(run_id, stage),
                }
            )
            warnings = run.get("warnings", ())
            if warnings:
                base["validation_errors"] = warnings
            return base
        if execution_status == "completed":
            artifacts = run.get("artifacts", ())
            outputs = [
                item
                for item in artifacts
                if isinstance(item, Mapping)
                and item.get("artifact_type") in {"reading_bundle", "reader_report_markdown"}
            ]
            base.update({"action": "completed", "outputs": outputs})
            return base
        if execution_status == "failed":
            base.update({"action": "failed", "warnings": run.get("warnings", ())})
            return base
        base["action"] = "inspect"
        return base


def _pending_stage(run: Mapping[str, Any]) -> str:
    current_task = str(run.get("current_task", ""))
    prefix = "awaiting_agent:"
    if not current_task.startswith(prefix):
        raise ProviderContractError("run is not awaiting an external agent candidate")
    stage = current_task.removeprefix(prefix).strip()
    if not stage:
        raise ProviderContractError("pending run has no reading stage")
    return stage

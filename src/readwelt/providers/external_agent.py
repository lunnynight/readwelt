"""Pull/submit adapter for Claude Code, Codex, and other external agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import ProviderContractError, StageCandidate, StageRequest
from .projection import compact_result, to_jsonable
from .service_port import invoke


def stage_request_uri(run_id: str, stage: str) -> str:
    return f"readwelt://runs/{run_id}/stage-request/{stage}"


class ExternalAgentAdapter:
    """Transport-neutral implementation of the external-agent handshake."""

    def __init__(self, service: object):
        self._service = service

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

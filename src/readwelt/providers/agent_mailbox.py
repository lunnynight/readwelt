"""Durable pull/submit mailbox for Claude Code, Codex, and other agents."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from readwelt.storage import ManifestStore, ProjectLayout
from readwelt.storage.serialization import canonical_json_bytes

from .contracts import (
    DEFAULT_TOKEN_COUNTER,
    AgentInputRequired,
    InputTokenCounter,
    ProviderContractError,
    ProviderEnvelopeProfile,
    ProviderKind,
    StageCandidate,
    StageRequest,
    validate_provider_input,
)
from .model_protocol import JsonSchema

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


class ExternalAgentMailboxProvider:
    """Pause at missing candidates and durably replay submitted ones."""

    kind = ProviderKind.AGENT
    name = "external-agent-mailbox"
    model = "external-agent"

    def __init__(
        self,
        layout: ProjectLayout,
        *,
        token_counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
    ) -> None:
        self._layout = layout
        self._manifests = ManifestStore()
        self._token_counter = token_counter

    @property
    def input_token_counter(self) -> InputTokenCounter:
        return self._token_counter

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate:
        request = replace(request, response_schema=dict(response_schema))
        request = self._bind_request_digest(request)
        validate_provider_input(
            request,
            response_schema,
            profile=ProviderEnvelopeProfile.AGENT_MAILBOX,
            model=self.model,
            counter=self._token_counter,
        )
        candidate_path = self._candidate_path(request.run_id, request.stage)
        if candidate_path.exists():
            candidate = StageCandidate.from_mapping(self._manifests.read(candidate_path))
            self._validate_pair(request, candidate)
            return candidate
        request_path = self._request_path(request.run_id, request.stage)
        if request_path.exists():
            existing = StageRequest.from_mapping(self._manifests.read(request_path))
            if existing != request:
                previous_digest = request.provenance.get("previous_request_digest")
                existing_digest = existing.provenance.get("request_digest")
                if previous_digest != existing_digest:
                    raise ProviderContractError(
                        "an external-agent request is already frozen for this run and stage"
                    )
                archived = self._stage_path(
                    request.run_id,
                    request.stage,
                    f"pages/request-{str(existing_digest).removeprefix('sha256:')}.json",
                )
                archived.parent.mkdir(parents=True, exist_ok=True)
                request_path.replace(archived)
                self._manifests.write(request_path, request.to_dict())
        else:
            self._manifests.write(request_path, request.to_dict())
        raise AgentInputRequired(request)

    def pull(self, run_id: str, stage: str) -> StageRequest:
        path = self._request_path(run_id, stage)
        if not path.exists():
            raise ProviderContractError(f"no external-agent request is awaiting {run_id}/{stage}")
        return StageRequest.from_mapping(self._manifests.read(path))

    def submit(self, candidate: StageCandidate) -> StageCandidate:
        request = self.pull(candidate.run_id, candidate.stage)
        self._validate_pair(request, candidate)
        expected_digest = request.provenance.get("request_digest")
        if candidate.provenance.get("request_digest") != expected_digest:
            raise ProviderContractError(
                "StageCandidate provenance.request_digest must match its StageRequest"
            )
        path = self._candidate_path(candidate.run_id, candidate.stage)
        if path.exists():
            existing = StageCandidate.from_mapping(self._manifests.read(path))
            if existing != candidate:
                raise ProviderContractError(
                    "a different StageCandidate is already frozen for this run and stage"
                )
            return existing
        self._manifests.write(path, candidate.to_dict())
        return candidate

    def has_candidate(self, run_id: str, stage: str) -> bool:
        return self._candidate_path(run_id, stage).exists()

    def reject(self, run_id: str, stage: str, reason: str) -> None:
        """Archive a rejected candidate so the same request can be retried."""

        path = self._candidate_path(run_id, stage)
        if not path.exists():
            raise ProviderContractError(f"no external-agent candidate exists for {run_id}/{stage}")
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        rejected = self._stage_path(
            run_id,
            stage,
            f"rejected/candidate-{digest}.json",
        )
        rejected.parent.mkdir(parents=True, exist_ok=True)
        path.replace(rejected)
        self._manifests.write(
            rejected.with_suffix(".rejection.json"),
            {
                "schema_version": "readwelt.agent-rejection.v1",
                "run_id": run_id,
                "stage": stage,
                "candidate_digest": f"sha256:{digest}",
                "reason": reason,
                "rejected_at": datetime.now(UTC).isoformat(),
            },
        )

    def accept_page(self, run_id: str, stage: str) -> None:
        """Archive a provisionally accepted page candidate before continuation."""

        path = self._candidate_path(run_id, stage)
        if not path.exists():
            raise ProviderContractError(f"no external-agent candidate exists for {run_id}/{stage}")
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        accepted = self._stage_path(
            run_id,
            stage,
            f"pages/candidate-{digest}.json",
        )
        accepted.parent.mkdir(parents=True, exist_ok=True)
        path.replace(accepted)

    def _request_path(self, run_id: str, stage: str) -> Path:
        return self._stage_path(run_id, stage, "request.json")

    def _candidate_path(self, run_id: str, stage: str) -> Path:
        return self._stage_path(run_id, stage, "candidate.json")

    def _stage_path(self, run_id: str, stage: str, filename: str) -> Path:
        for value, label in ((run_id, "run_id"), (stage, "stage")):
            if not _SAFE_COMPONENT.fullmatch(value):
                raise ProviderContractError(f"unsafe {label}: {value!r}")
        path = (self._layout.root / "runs" / run_id / "agent" / stage / filename).resolve()
        path.relative_to(self._layout.root)
        return path

    @staticmethod
    def _validate_pair(
        request: StageRequest,
        candidate: StageCandidate,
    ) -> None:
        if candidate.run_id != request.run_id or candidate.stage != request.stage:
            raise ProviderContractError(
                "StageCandidate run_id and stage must match its StageRequest"
            )
        if candidate.schema_version != request.schema_version:
            raise ProviderContractError("StageCandidate schema_version must match its StageRequest")

    @staticmethod
    def _bind_request_digest(request: StageRequest) -> StageRequest:
        provenance = dict(request.provenance)
        supplied = provenance.pop("request_digest", None)
        unbound = replace(request, provenance=provenance)
        digest = (
            "sha256:"
            + hashlib.sha256(
                canonical_json_bytes(unbound.to_dict(validate_budget=False))
            ).hexdigest()
        )
        if supplied is not None and supplied != digest:
            raise ProviderContractError("StageRequest request_digest is invalid")
        return replace(
            request,
            provenance={**provenance, "request_digest": digest},
        )

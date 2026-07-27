"""Application adapter from provider resolution to one settled candidate."""

from __future__ import annotations

import json

from readwelt.providers import (
    AgentInputRequired,
    CandidateProvider,
    ProviderConflictError,
    ProviderKind,
    ProviderResolver,
    ProviderSelection,
    ProviderUnavailableError,
    ResolutionStatus,
    StageCandidate,
    StageRequest,
)
from readwelt.providers.model_protocol import JsonSchema
from readwelt.token_budget import DEFAULT_TOKEN_COUNTER, InputTokenCounter

from .run_store import ApplicationRunStore


class AuditedCandidateProvider:
    """Persist the provider boundary before and after every invocation."""

    def __init__(
        self,
        provider: CandidateProvider,
        run_store: ApplicationRunStore,
    ) -> None:
        self._provider = provider
        self._run_store = run_store

    @property
    def kind(self) -> ProviderKind:
        return self._provider.kind

    @property
    def name(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str:
        return self._provider.model

    @property
    def input_token_counter(self) -> InputTokenCounter:
        return getattr(
            self._provider,
            "input_token_counter",
            DEFAULT_TOKEN_COUNTER,
        )

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate:
        invocation_id = self._run_store.begin_provider_invocation(
            request,
            provider=self.name,
            model=self.model,
        )
        try:
            candidate = await self._provider.generate(request, response_schema)
        except AgentInputRequired as exc:
            self._run_store.finish_provider_invocation(
                request.run_id,
                invocation_id,
                status="awaiting_agent",
                error=str(exc),
            )
            raise
        except Exception as exc:
            self._run_store.finish_provider_invocation(
                request.run_id,
                invocation_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        self._run_store.finish_provider_invocation(
            request.run_id,
            invocation_id,
            status="candidate_received",
            candidate=candidate,
        )
        return candidate


class ResolvingCandidateProvider:
    """Adapt the multi-provider resolver to the engine's one-candidate port."""

    def __init__(
        self,
        resolver: ProviderResolver,
        selection: ProviderSelection,
    ) -> None:
        self._resolver = resolver
        self._selection = selection

    @property
    def kind(self) -> ProviderKind:
        return self._selection.primary or ProviderKind.AGENT

    @property
    def name(self) -> str:
        selected = (self._selection.primary, *self._selection.candidates)
        names = ",".join(item.value for item in selected if item is not None)
        return f"resolver:{self._selection.mode.value}:{names}"

    @property
    def model(self) -> str:
        return "provider-resolver"

    @property
    def input_token_counter(self) -> InputTokenCounter:
        return self._resolver.planning_token_counter(self._selection)

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate:
        resolution = await self._resolver.resolve(
            self._selection,
            request,
            response_schema,
        )
        if resolution.status is ResolutionStatus.AWAITING_AGENT:
            raise ProviderUnavailableError(
                "agent_takeover requires the durable external-agent mailbox"
            )
        if not resolution.candidates:
            raise ProviderUnavailableError("provider resolver returned no candidate")
        if len(resolution.candidates) == 1:
            return resolution.candidates[0]

        canonical = {
            json.dumps(
                candidate.candidate,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for candidate in resolution.candidates
        }
        if len(canonical) != 1:
            providers = ", ".join(candidate.provider for candidate in resolution.candidates)
            raise ProviderConflictError(
                f"compare providers disagree at {request.stage}: {providers}; "
                "an explicit mediation policy is required"
            )
        primary = resolution.candidates[0]
        return StageCandidate(
            schema_version=primary.schema_version,
            run_id=primary.run_id,
            stage=primary.stage,
            candidate=primary.candidate,
            provider=primary.provider,
            model=primary.model,
            provenance={
                **primary.provenance,
                "compare_consensus": [candidate.provider for candidate in resolution.candidates],
            },
        )

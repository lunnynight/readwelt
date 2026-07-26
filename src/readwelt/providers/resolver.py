"""Explicit provider-mode resolution with no silent conflict handling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from .contracts import (
    ProviderConflictError,
    ProviderKind,
    ProviderMode,
    ProviderSelection,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
)
from .model_protocol import CandidateProvider, JsonSchema


class ResolutionStatus(StrEnum):
    COMPLETED = "completed"
    AWAITING_AGENT = "awaiting_agent"


@dataclass(frozen=True, slots=True)
class ProviderResolution:
    status: ResolutionStatus
    candidates: tuple[StageCandidate, ...] = ()
    attempted: tuple[ProviderKind, ...] = ()


class ProviderResolver:
    """Resolve the user's explicit mode; mediation remains outside this class."""

    def __init__(self, providers: tuple[CandidateProvider, ...]) -> None:
        resolved: dict[ProviderKind, CandidateProvider] = {}
        for provider in providers:
            if provider.kind in resolved:
                raise ProviderConflictError(
                    f"more than one provider is registered for {provider.kind.value}"
                )
            resolved[provider.kind] = provider
        self._providers = resolved

    async def resolve(
        self,
        selection: ProviderSelection,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> ProviderResolution:
        if selection.mode is ProviderMode.AGENT_TAKEOVER:
            return ProviderResolution(
                status=ResolutionStatus.AWAITING_AGENT,
                attempted=(ProviderKind.AGENT,),
            )
        if selection.primary is None:
            raise ProviderConflictError("provider selection has no primary provider")

        if selection.mode is ProviderMode.PRIMARY:
            candidate = await self._provider(selection.primary).generate(request, response_schema)
            return ProviderResolution(
                status=ResolutionStatus.COMPLETED,
                candidates=(candidate,),
                attempted=(selection.primary,),
            )

        ordered = (selection.primary, *selection.candidates)
        if selection.mode is ProviderMode.COMPARE:
            providers = tuple(self._provider(kind) for kind in ordered)
            candidates = await asyncio.gather(
                *(provider.generate(request, response_schema) for provider in providers)
            )
            return ProviderResolution(
                status=ResolutionStatus.COMPLETED,
                candidates=tuple(candidates),
                attempted=ordered,
            )

        if selection.mode is ProviderMode.FALLBACK:
            unavailable: list[str] = []
            attempted: list[ProviderKind] = []
            for kind in ordered:
                attempted.append(kind)
                try:
                    candidate = await self._provider(kind).generate(request, response_schema)
                except ProviderUnavailableError as exc:
                    unavailable.append(f"{kind.value}: {exc}")
                    continue
                return ProviderResolution(
                    status=ResolutionStatus.COMPLETED,
                    candidates=(candidate,),
                    attempted=tuple(attempted),
                )
            raise ProviderUnavailableError(
                "all fallback providers are unavailable: " + "; ".join(unavailable)
            )

        raise ProviderConflictError(f"unsupported provider mode: {selection.mode}")

    def _provider(self, kind: ProviderKind) -> CandidateProvider:
        try:
            return self._providers[kind]
        except KeyError as exc:
            raise ProviderUnavailableError(f"{kind.value} provider is not configured") from exc

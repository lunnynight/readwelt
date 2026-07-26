from __future__ import annotations

import asyncio

import pytest

from readwelt.providers import (
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
from tests.interfaces.fakes import DeterministicFakeProvider

SCHEMA = {
    "type": "object",
    "properties": {"source": {"type": "string"}},
    "required": ["source"],
}
REQUEST = StageRequest(
    schema_version="1",
    run_id="r1",
    stage="stage-4",
    evidence_packet={},
)


class UnavailableFake(DeterministicFakeProvider):
    async def generate(self, request: StageRequest, response_schema: JsonSchema) -> StageCandidate:
        raise ProviderUnavailableError(f"{self.name} offline")


def fake(kind: ProviderKind) -> DeterministicFakeProvider:
    return DeterministicFakeProvider({"source": kind.value}, kind=kind, name=f"{kind.value}-fake")


def test_primary_uses_exactly_selected_provider() -> None:
    resolver = ProviderResolver((fake(ProviderKind.LOCAL), fake(ProviderKind.API)))
    selection = ProviderSelection.build(mode="primary", primary="api")

    result = asyncio.run(resolver.resolve(selection, REQUEST, SCHEMA))

    assert [item.candidate["source"] for item in result.candidates] == ["api"]
    assert result.attempted == (ProviderKind.API,)


def test_compare_returns_all_candidates_in_explicit_order() -> None:
    resolver = ProviderResolver((fake(ProviderKind.LOCAL), fake(ProviderKind.API)))
    selection = ProviderSelection.build(mode="compare", primary="local", candidates=["api"])

    result = asyncio.run(resolver.resolve(selection, REQUEST, SCHEMA))

    assert [item.candidate["source"] for item in result.candidates] == ["local", "api"]


def test_fallback_only_advances_on_unavailable() -> None:
    resolver = ProviderResolver(
        (
            UnavailableFake({}, kind=ProviderKind.LOCAL, name="offline"),
            fake(ProviderKind.API),
        )
    )
    selection = ProviderSelection.build(mode="fallback", primary="local", candidates=["api"])

    result = asyncio.run(resolver.resolve(selection, REQUEST, SCHEMA))

    assert result.candidates[0].candidate["source"] == "api"
    assert result.attempted == (ProviderKind.LOCAL, ProviderKind.API)


def test_fallback_does_not_hide_contract_failures() -> None:
    resolver = ProviderResolver(
        (
            DeterministicFakeProvider({"wrong": "shape"}, kind=ProviderKind.LOCAL, name="invalid"),
            fake(ProviderKind.API),
        )
    )
    selection = ProviderSelection.build(mode="fallback", primary="local", candidates=["api"])

    with pytest.raises(ValueError, match="missing required fields"):
        asyncio.run(resolver.resolve(selection, REQUEST, SCHEMA))


def test_agent_takeover_never_calls_a_model() -> None:
    resolver = ProviderResolver(())
    selection = ProviderSelection.build(mode="agent_takeover")

    result = asyncio.run(resolver.resolve(selection, REQUEST, SCHEMA))

    assert result.status is ResolutionStatus.AWAITING_AGENT
    assert result.candidates == ()


def test_unconfigured_provider_is_explicitly_unavailable() -> None:
    resolver = ProviderResolver(())
    selection = ProviderSelection.build(mode="primary", primary="api")

    with pytest.raises(ProviderUnavailableError, match="not configured"):
        asyncio.run(resolver.resolve(selection, REQUEST, SCHEMA))


def test_duplicate_kind_registration_is_a_conflict() -> None:
    with pytest.raises(ProviderConflictError, match="more than one"):
        ProviderResolver((fake(ProviderKind.LOCAL), fake(ProviderKind.LOCAL)))

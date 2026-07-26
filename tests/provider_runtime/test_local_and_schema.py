from __future__ import annotations

import asyncio

import pytest

from readwelt.providers import (
    LocalOpenAICompatibleProvider,
    ProviderContractError,
    StageRequest,
)
from tests.interfaces.fakes import DeterministicFakeProvider

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["claims"],
    "additionalProperties": False,
}


def request() -> StageRequest:
    return StageRequest(
        schema_version="1",
        run_id="run-1",
        stage="stage-1",
        evidence_packet={"anchors": ["a-1"]},
        provenance={"prompt_version": "p1"},
    )


def test_fake_provider_validates_and_records_provenance() -> None:
    provider = DeterministicFakeProvider({"claims": ["supported"]})

    result = asyncio.run(provider.generate(request(), SCHEMA))

    assert result.candidate == {"claims": ["supported"]}
    assert result.provenance["provider"] == "deterministic-fake"
    assert result.provenance["prompt_version"] == "p1"
    assert result.provenance["token_usage"] == {}
    assert isinstance(result.provenance["latency_ms"], float)


def test_fake_provider_rejects_invalid_structured_output() -> None:
    provider = DeterministicFakeProvider({"claims": "not-an-array"})

    with pytest.raises(ProviderContractError, match="array"):
        asyncio.run(provider.generate(request(), SCHEMA))


@pytest.mark.parametrize(
    "base_url",
    [
        "https://models.example/v1",
        "http://192.168.1.4:11434/v1",
    ],
)
def test_local_provider_rejects_non_loopback(base_url: str) -> None:
    with pytest.raises(ProviderContractError, match="loopback"):
        LocalOpenAICompatibleProvider(model="local", base_url=base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://[::1]:11434/v1",
    ],
)
def test_local_provider_accepts_loopback(base_url: str) -> None:
    provider = LocalOpenAICompatibleProvider(model="local", base_url=base_url)
    assert provider.kind.value == "local"

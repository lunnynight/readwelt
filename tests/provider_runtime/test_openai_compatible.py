from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from readwelt.providers import (
    OpenAICompatibleProvider,
    ProviderContractError,
    ProviderUnavailableError,
    StageRequest,
)

SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {"type": "string"}}},
    "required": ["claims"],
    "additionalProperties": False,
}


def request() -> StageRequest:
    return StageRequest(
        schema_version="1",
        run_id="r1",
        stage="stage-2",
        evidence_packet={"anchors": ["a1"]},
    )


def response_payload(content: Any = '{"claims":["c1"]}') -> dict[str, Any]:
    return {
        "id": "chat-1",
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
        },
    }


def test_openai_compatible_calls_custom_base_url_and_records_usage() -> None:
    async def scenario() -> None:
        def handler(call: httpx.Request) -> httpx.Response:
            assert call.url == "https://model.example/v1/chat/completions"
            assert call.headers["authorization"] == "Bearer secret"
            body = __import__("json").loads(call.content)
            assert body["response_format"]["json_schema"]["strict"] is True
            return httpx.Response(200, json=response_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                model="model-a",
                api_key="secret",  # pragma: allowlist secret
                base_url="https://model.example/v1/",
                client=client,
            )
            result = await provider.generate(request(), SCHEMA)
            assert result.provider == "openai-compatible"
            assert result.model == "model-a"
            assert result.provenance["token_usage"]["total_tokens"] == 14
            assert result.provenance["response_id"] == "chat-1"
            assert result.provenance["provider_input_budget"]["profile"] == (
                "openai_chat_completions.v1"
            )
            assert result.provenance["provider_input_budget"]["mode"] == (
                "conservative_upper_bound"
            )

    asyncio.run(scenario())


def test_missing_api_key_is_explicitly_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAICompatibleProvider(model="model-a")

    with pytest.raises(ProviderUnavailableError, match="no API key"):
        asyncio.run(provider.generate(request(), SCHEMA))


def test_http_failure_is_unavailable_without_leaking_body() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(401, text="sensitive-provider-body")
            )
        ) as client:
            provider = OpenAICompatibleProvider(model="model-a", api_key="secret", client=client)
            with pytest.raises(ProviderUnavailableError, match="HTTP 401") as caught:
                await provider.generate(request(), SCHEMA)
            assert "sensitive-provider-body" not in str(caught.value)

    asyncio.run(scenario())


def test_invalid_model_json_is_contract_error() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=response_payload("not-json"))
            )
        ) as client:
            provider = OpenAICompatibleProvider(model="model-a", api_key="secret", client=client)
            with pytest.raises(ProviderContractError, match="invalid chat completion"):
                await provider.generate(request(), SCHEMA)

    asyncio.run(scenario())

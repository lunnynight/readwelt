"""OpenAI-compatible structured candidate provider."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx

from .contracts import (
    DEFAULT_TOKEN_COUNTER,
    InputTokenCounter,
    ProviderContractError,
    ProviderEnvelopeProfile,
    ProviderInputBudgetReceipt,
    ProviderKind,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
    openai_chat_payload,
    validate_json_schema,
    validate_provider_input,
)
from .model_protocol import JsonSchema


def parse_openai_structured_response(
    response: httpx.Response,
    response_schema: JsonSchema,
    *,
    provider_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse and validate the shared OpenAI-compatible structured response."""

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        candidate = json.loads(content) if isinstance(content, str) else content
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ProviderContractError(f"{provider_name} returned an invalid chat completion") from exc
    if not isinstance(candidate, Mapping):
        raise ProviderContractError(f"{provider_name} returned a non-object candidate")
    validate_json_schema(candidate, response_schema)
    return dict(candidate), dict(body)


class OpenAICompatibleProvider:
    """Call `/chat/completions` and require a schema-valid JSON object."""

    kind = ProviderKind.API

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        name: str = "openai-compatible",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
        token_counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._name = name
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._token_counter = token_counter

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def input_token_counter(self) -> InputTokenCounter:
        return self._token_counter

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate:
        if not self._api_key:
            raise ProviderUnavailableError(f"{self.name} is unavailable: no API key was configured")

        started = time.perf_counter()
        payload = self._payload(request, response_schema)
        input_budget = validate_provider_input(
            request,
            response_schema,
            profile=ProviderEnvelopeProfile.OPENAI_CHAT,
            model=self.model,
            counter=self._token_counter,
        )
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                        timeout=self._timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"{self.name} is unavailable: {type(exc).__name__}"
            ) from exc

        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                f"{self.name} is unavailable: HTTP {response.status_code}"
            )
        return self._candidate_from_response(
            request,
            response,
            response_schema,
            latency_ms,
            input_budget,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: StageRequest, response_schema: JsonSchema) -> dict[str, Any]:
        return openai_chat_payload(
            request,
            response_schema,
            model=self.model,
        )

    def _candidate_from_response(
        self,
        request: StageRequest,
        response: httpx.Response,
        response_schema: JsonSchema,
        latency_ms: float,
        input_budget: ProviderInputBudgetReceipt,
    ) -> StageCandidate:
        candidate, body = parse_openai_structured_response(
            response,
            response_schema,
            provider_name=self.name,
        )

        usage = body.get("usage", {})
        token_usage = {
            key: int(usage[key])
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(usage.get(key), int)
        }
        return StageCandidate(
            schema_version=request.schema_version,
            run_id=request.run_id,
            stage=request.stage,
            candidate=dict(candidate),
            provider=self.name,
            model=self.model,
            provenance={
                **dict(request.provenance),
                "provider_kind": self.kind.value,
                "provider": self.name,
                "model": self.model,
                "latency_ms": latency_ms,
                "provider_input_budget": input_budget.to_dict(),
                "token_usage": token_usage,
                "response_id": body.get("id"),
            },
            raw_response=dict(body),
        )

"""OpenAI-compatible structured candidate provider."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from .contracts import (
    ProviderContractError,
    ProviderKind,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
)
from .model_protocol import JsonSchema


def validate_json_schema(value: Any, schema: JsonSchema, path: str = "$") -> None:
    """Validate the useful, deterministic subset of JSON Schema used by stages."""
    if "const" in schema and value != schema["const"]:
        raise ProviderContractError(f"{path} must equal the schema const")
    if "enum" in schema and value not in schema["enum"]:
        raise ProviderContractError(f"{path} is not one of the allowed values")
    _validate_combinators(value, schema, path)
    _validate_type(value, schema, path)
    if isinstance(value, Mapping):
        _validate_object(value, schema, path)
    if isinstance(value, list):
        _validate_array(value, schema, path)


def _validate_combinators(value: Any, schema: JsonSchema, path: str) -> None:
    if "allOf" in schema:
        for child in _schema_sequence(schema["allOf"], f"{path}.allOf"):
            validate_json_schema(value, child, path)
    if "anyOf" in schema:
        choices = _schema_sequence(schema["anyOf"], f"{path}.anyOf")
        if not any(_is_valid(value, child) for child in choices):
            raise ProviderContractError(f"{path} does not match any allowed schema")
    if "oneOf" in schema:
        choices = _schema_sequence(schema["oneOf"], f"{path}.oneOf")
        if sum(_is_valid(value, child) for child in choices) != 1:
            raise ProviderContractError(f"{path} must match exactly one allowed schema")


def _validate_type(value: Any, schema: JsonSchema, path: str) -> None:
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(value, item) for item in expected):
            raise ProviderContractError(f"{path} has an invalid JSON type")
    elif isinstance(expected, str) and not _matches_type(value, expected):
        raise ProviderContractError(f"{path} must be of type {expected}")


def _validate_object(value: Mapping[str, Any], schema: JsonSchema, path: str) -> None:
    required = schema.get("required", ())
    if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
        raise ProviderContractError(f"{path}.required must be an array")
    missing = [str(key) for key in required if key not in value]
    if missing:
        raise ProviderContractError(f"{path} is missing required fields: {', '.join(missing)}")
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ProviderContractError(f"{path}.properties must be an object")
    for key, child in properties.items():
        if key not in value:
            continue
        if not isinstance(child, Mapping):
            raise ProviderContractError(f"{path}.{key} schema must be an object")
        validate_json_schema(value[key], child, f"{path}.{key}")
    if schema.get("additionalProperties") is False:
        extras = set(value) - set(properties)
        if extras:
            raise ProviderContractError(
                f"{path} contains unsupported fields: {', '.join(sorted(extras))}"
            )


def _validate_array(value: list[Any], schema: JsonSchema, path: str) -> None:
    if "items" not in schema:
        return
    items = schema["items"]
    if not isinstance(items, Mapping):
        raise ProviderContractError(f"{path}.items must be an object")
    for index, item in enumerate(value):
        validate_json_schema(item, items, f"{path}[{index}]")


def _schema_sequence(value: Any, path: str) -> list[JsonSchema]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProviderContractError(f"{path} must be an array")
    if not all(isinstance(item, Mapping) for item in value):
        raise ProviderContractError(f"{path} entries must be objects")
    return list(value)


def _is_valid(value: Any, schema: JsonSchema) -> bool:
    try:
        validate_json_schema(value, schema)
    except ProviderContractError:
        return False
    return True


def _matches_type(value: Any, expected: str) -> bool:
    checks = {
        "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "string": isinstance(value, str),
        "array": isinstance(value, list),
        "object": isinstance(value, Mapping),
    }
    if expected not in checks:
        raise ProviderContractError(f"unsupported JSON Schema type: {expected}")
    return checks[expected]


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
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._name = name
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate:
        if not self._api_key:
            raise ProviderUnavailableError(f"{self.name} is unavailable: no API key was configured")

        started = time.perf_counter()
        payload = self._payload(request, response_schema)
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
        return self._candidate_from_response(request, response, response_schema, latency_ms)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: StageRequest, response_schema: JsonSchema) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only a JSON object that satisfies the supplied response schema. "
                        "Do not invent evidence anchors."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(request.to_dict(), ensure_ascii=False),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "readwelt_stage_candidate",
                    "strict": True,
                    "schema": dict(response_schema),
                },
            },
        }

    def _candidate_from_response(
        self,
        request: StageRequest,
        response: httpx.Response,
        response_schema: JsonSchema,
        latency_ms: float,
    ) -> StageCandidate:
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            candidate = json.loads(content) if isinstance(content, str) else content
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderContractError(f"{self.name} returned an invalid chat completion") from exc
        if not isinstance(candidate, Mapping):
            raise ProviderContractError(f"{self.name} returned a non-object candidate")
        validate_json_schema(candidate, response_schema)

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
                "token_usage": token_usage,
                "response_id": body.get("id"),
            },
            raw_response=dict(body),
        )

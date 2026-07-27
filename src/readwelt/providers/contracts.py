"""Transport-neutral contracts used by external candidate providers.

The domain layer owns stage validation and settlement.  These types only define
the versioned JSON envelope exchanged with an external agent.
"""

# ruff: noqa: I001

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from readwelt.provider_input import (
    DEFAULT_TOKEN_COUNTER as DEFAULT_TOKEN_COUNTER,
    InputTokenCounter as InputTokenCounter,
    ProviderContractError as ProviderContractError,
    ProviderEnvelopeProfile as ProviderEnvelopeProfile,
    ProviderInputBudgetReceipt as ProviderInputBudgetReceipt,
    canonical_json_bytes as canonical_json_bytes,
    claude_code_prompt as claude_code_prompt,
    measure_planned_provider_inputs as measure_planned_provider_inputs,
    openai_chat_payload as openai_chat_payload,
    openai_structured_payload as openai_structured_payload,
    provider_profiles as provider_profiles,
    validate_provider_input as validate_provider_input,
)


class ProviderConflictError(ProviderContractError):
    """More than one provider was selected without an explicit policy."""

    code = "provider_conflict"


class ProviderUnavailableError(ProviderContractError):
    """The selected provider transport is unavailable."""

    code = "provider_unavailable"


def validate_json_schema(
    value: Any,
    schema: Mapping[str, Any],
    path: str = "$",
) -> None:
    """Validate the deterministic JSON Schema subset used by stage providers."""

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


def _validate_combinators(
    value: Any,
    schema: Mapping[str, Any],
    path: str,
) -> None:
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


def _validate_type(value: Any, schema: Mapping[str, Any], path: str) -> None:
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(value, item) for item in expected):
            raise ProviderContractError(f"{path} has an invalid JSON type")
    elif isinstance(expected, str) and not _matches_type(value, expected):
        raise ProviderContractError(f"{path} must be of type {expected}")


def _validate_object(
    value: Mapping[str, Any],
    schema: Mapping[str, Any],
    path: str,
) -> None:
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


def _validate_array(
    value: list[Any],
    schema: Mapping[str, Any],
    path: str,
) -> None:
    if "items" not in schema:
        return
    items = schema["items"]
    if not isinstance(items, Mapping):
        raise ProviderContractError(f"{path}.items must be an object")
    for index, item in enumerate(value):
        validate_json_schema(item, items, f"{path}[{index}]")


def _schema_sequence(value: Any, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProviderContractError(f"{path} must be an array")
    if not all(isinstance(item, Mapping) for item in value):
        raise ProviderContractError(f"{path} entries must be objects")
    return list(value)


def _is_valid(value: Any, schema: Mapping[str, Any]) -> bool:
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


class AgentInputRequired(ProviderContractError):
    """A run reached a stage that must be completed by an external agent."""

    code = "agent_input_required"

    def __init__(self, request: StageRequest) -> None:
        self.request = request
        super().__init__(f"external agent candidate required for {request.run_id}/{request.stage}")


class ProviderKind(StrEnum):
    LOCAL = "local"
    API = "api"
    AGENT = "agent"
    CLAUDE_CODE = "claude-code"


class ProviderMode(StrEnum):
    PRIMARY = "primary"
    COMPARE = "compare"
    FALLBACK = "fallback"
    AGENT_TAKEOVER = "agent_takeover"


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    """Explicit provider choice passed through to the application service."""

    mode: ProviderMode = ProviderMode.PRIMARY
    primary: ProviderKind | None = None
    candidates: tuple[ProviderKind, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        mode: str | ProviderMode = ProviderMode.PRIMARY,
        primary: str | ProviderKind | None = None,
        candidates: Sequence[str | ProviderKind] = (),
    ) -> ProviderSelection:
        parsed_mode = ProviderMode(mode)
        parsed_primary = ProviderKind(primary) if primary is not None else None
        parsed_candidates = tuple(dict.fromkeys(ProviderKind(item) for item in candidates))

        if parsed_mode is ProviderMode.AGENT_TAKEOVER:
            if parsed_candidates:
                raise ProviderConflictError(
                    "agent_takeover cannot run additional candidate providers"
                )
            if parsed_primary not in (None, ProviderKind.AGENT):
                raise ProviderConflictError(
                    "agent_takeover cannot use a non-agent primary provider"
                )
            parsed_primary = ProviderKind.AGENT

        if parsed_mode is ProviderMode.PRIMARY:
            selected = tuple(
                dict.fromkeys(
                    item for item in (parsed_primary, *parsed_candidates) if item is not None
                )
            )
            if len(selected) > 1:
                raise ProviderConflictError(
                    "primary mode requires exactly one provider; use compare or fallback"
                )
            if selected:
                parsed_primary = selected[0]
                parsed_candidates = ()

        if parsed_mode in (ProviderMode.COMPARE, ProviderMode.FALLBACK):
            if parsed_primary is None:
                raise ProviderConflictError(f"{parsed_mode} requires a primary provider")
            if not parsed_candidates:
                raise ProviderConflictError(
                    f"{parsed_mode} requires at least one additional provider"
                )
            if parsed_primary in parsed_candidates:
                raise ProviderConflictError(
                    "primary provider cannot also appear in candidate providers"
                )

        return cls(
            mode=parsed_mode,
            primary=parsed_primary,
            candidates=parsed_candidates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "primary": self.primary.value if self.primary else None,
            "candidates": [item.value for item in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class StageRequest:
    schema_version: str
    run_id: str
    stage: str
    evidence_packet: Mapping[str, Any]
    response_schema: Mapping[str, Any] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    resource_uri: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    hard_serialized_token_budget: int | None = None
    estimated_serialized_tokens: int | None = None
    budget_manifest: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> StageRequest:
        required = ("schema_version", "run_id", "stage", "evidence_packet")
        missing = [key for key in required if key not in value]
        if missing:
            raise ProviderContractError(
                f"StageRequest is missing required fields: {', '.join(missing)}"
            )
        packet = value["evidence_packet"]
        if not isinstance(packet, Mapping):
            raise ProviderContractError("evidence_packet must be an object")
        return cls(
            schema_version=str(value["schema_version"]),
            run_id=str(value["run_id"]),
            stage=str(value["stage"]),
            evidence_packet=dict(packet),
            response_schema=dict(value.get("response_schema", {})),
            capabilities=tuple(str(item) for item in value.get("capabilities", ())),
            resource_uri=(
                str(value["resource_uri"]) if value.get("resource_uri") is not None else None
            ),
            provenance=dict(value.get("provenance", {})),
            hard_serialized_token_budget=(
                int(value["hard_serialized_token_budget"])
                if value.get("hard_serialized_token_budget") is not None
                else None
            ),
            estimated_serialized_tokens=(
                int(value["estimated_serialized_tokens"])
                if value.get("estimated_serialized_tokens") is not None
                else None
            ),
            budget_manifest=dict(value.get("budget_manifest", {})),
        )

    def to_dict(self, *, validate_budget: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if validate_budget and self.hard_serialized_token_budget is not None:
            from readwelt.token_budget import (
                DEFAULT_TOKEN_COUNTER,
                TokenCountMode,
                require_counter_receipt,
            )

            from .request_budget import serialized_request_tokens

            counter = self.budget_manifest.get("counter")
            if not isinstance(counter, Mapping):
                raise ProviderContractError("hard StageRequest budget has no token counter receipt")
            receipt = {
                **dict(counter),
                "tokens": self.estimated_serialized_tokens,
            }
            try:
                require_counter_receipt(receipt)
            except ValueError as error:
                raise ProviderContractError(str(error)) from error
            counter_id = counter.get("counter_id")
            mode = counter.get("mode")
            if counter_id == DEFAULT_TOKEN_COUNTER.counter_id:
                actual = serialized_request_tokens(value)
                if self.estimated_serialized_tokens != actual:
                    raise ProviderContractError(
                        "StageRequest serialized token estimate does not match final payload"
                    )
            elif mode == TokenCountMode.EXACT.value:
                if self.estimated_serialized_tokens is None:
                    raise ProviderContractError("exact StageRequest token receipt has no count")
                actual = self.estimated_serialized_tokens
            else:
                raise ProviderContractError(
                    "unknown conservative counter cannot prove the StageRequest hard bound"
                )
            provider_input = self.budget_manifest.get("provider_input")
            provider_tokens = (
                provider_input.get("max_tokens") if isinstance(provider_input, Mapping) else None
            )
            if not isinstance(provider_tokens, int):
                raise ProviderContractError("hard StageRequest budget has no provider input count")
            if (
                actual > self.hard_serialized_token_budget
                or provider_tokens > self.hard_serialized_token_budget
            ):
                raise ProviderContractError("complete provider input exceeds hard provider budget")
        return value


@dataclass(frozen=True, slots=True)
class StageCandidate:
    schema_version: str
    run_id: str
    stage: str
    candidate: Mapping[str, Any]
    provider: str
    model: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    raw_response: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> StageCandidate:
        required = ("schema_version", "run_id", "stage", "candidate", "provider")
        missing = [key for key in required if key not in value]
        if missing:
            raise ProviderContractError(
                f"StageCandidate is missing required fields: {', '.join(missing)}"
            )
        candidate = value["candidate"]
        if not isinstance(candidate, Mapping):
            raise ProviderContractError("candidate must be an object")
        return cls(
            schema_version=str(value["schema_version"]),
            run_id=str(value["run_id"]),
            stage=str(value["stage"]),
            candidate=dict(candidate),
            provider=str(value["provider"]),
            model=str(value["model"]) if value.get("model") is not None else None,
            provenance=dict(value.get("provenance", {})),
            raw_response=(
                dict(value["raw_response"])
                if isinstance(value.get("raw_response"), Mapping)
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

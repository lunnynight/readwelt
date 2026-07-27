"""Provider input envelopes and final hard-budget validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from readwelt.token_budget import (
    DEFAULT_TOKEN_COUNTER,
    InputTokenCounter,
    TokenCount,
    canonical_json_bytes,
    canonical_json_text,
)

__all__ = [
    "DEFAULT_TOKEN_COUNTER",
    "InputTokenCounter",
    "ProviderEnvelopeProfile",
    "ProviderInputBudgetReceipt",
    "ProviderContractError",
    "agent_mailbox_input",
    "canonical_json_bytes",
    "claude_code_input",
    "claude_code_prompt",
    "measure_planned_provider_inputs",
    "measure_provider_input",
    "openai_chat_payload",
    "provider_profiles",
    "validate_provider_input",
]

JsonSchema = Mapping[str, Any]


class ProviderContractError(ValueError):
    """A provider request cannot be proven safe under its public contract."""

    code = "provider_contract_error"


class StageRequestLike(Protocol):
    @property
    def hard_serialized_token_budget(self) -> int | None: ...

    def to_dict(self, *, validate_budget: bool = True) -> dict[str, Any]: ...


OPENAI_SYSTEM_INSTRUCTIONS = (
    "Return only a JSON object that satisfies the supplied response schema. "
    "Do not invent evidence anchors."
)
CLAUDE_PROMPT_INSTRUCTIONS = (
    "You are a Readwelt stage candidate generator. "
    "Use only the supplied evidence packet and upstream claims. "
    "Do not invent source anchors or outside facts. "
    "Every gaps entry must be an object with kind and description. "
    "source_claim_ids may contain only claim_id values already present in "
    "evidence_packet.upstream_claims; never cite a claim created in this response. "
    "When evidence_packet.upstream_claims is empty, omit source_claim_ids or use []. "
    "Return exactly one object satisfying the JSON Schema supplied by the host."
)


class ProviderEnvelopeProfile(StrEnum):
    OPENAI_CHAT = "openai_chat_completions.v1"
    CLAUDE_CODE = "claude_code_print_json_schema.v1"
    AGENT_MAILBOX = "agent_mailbox_stage_request.v1"


@dataclass(frozen=True, slots=True)
class ProviderInputBudgetReceipt:
    schema_version: str
    profile: ProviderEnvelopeProfile
    model: str
    count: TokenCount
    hard_token_budget: int | None

    @property
    def within_budget(self) -> bool:
        return self.hard_token_budget is None or self.count.tokens <= self.hard_token_budget

    def to_dict(self) -> dict[str, Any]:
        unused_headroom = (
            None if self.hard_token_budget is None else self.hard_token_budget - self.count.tokens
        )
        tokenizer_contract = (
            {"max_input_tokens_per_utf8_byte": 1}
            if self.count.mode.value == "conservative_upper_bound"
            else {"exact_counter_id": self.count.counter_id}
        )
        return {
            "schema_version": self.schema_version,
            "profile": self.profile.value,
            "model": self.model,
            "profile_tokenizer_contract": tokenizer_contract,
            **self.count.to_dict(),
            "hard_token_budget": self.hard_token_budget,
            "within_budget": self.within_budget,
            "unused_headroom_tokens": unused_headroom,
        }


def openai_chat_payload(
    request: StageRequestLike,
    response_schema: JsonSchema,
    *,
    model: str,
    validate_request: bool = True,
) -> dict[str, Any]:
    return openai_structured_payload(
        model=model,
        system_instructions=OPENAI_SYSTEM_INSTRUCTIONS,
        input_value=_request_without_embedded_response_schema(
            request,
            validate_request=validate_request,
        ),
        response_schema=response_schema,
        schema_name="readwelt_stage_candidate",
    )


def openai_structured_payload(
    *,
    model: str,
    system_instructions: str,
    input_value: object,
    response_schema: JsonSchema,
    schema_name: str,
) -> dict[str, Any]:
    """Build the shared strict JSON-schema chat-completions envelope."""

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instructions},
            {
                "role": "user",
                "content": canonical_json_text(input_value),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": dict(response_schema),
            },
        },
    }


def claude_code_prompt(
    request: StageRequestLike,
    *,
    validate_request: bool = True,
) -> str:
    return (
        CLAUDE_PROMPT_INSTRUCTIONS
        + "\n\nSTAGE REQUEST:\n"
        + canonical_json_text(
            _request_without_embedded_response_schema(
                request,
                validate_request=validate_request,
            )
        )
    )


def claude_code_input(
    request: StageRequestLike,
    response_schema: JsonSchema,
    *,
    model: str,
    validate_request: bool = True,
) -> dict[str, Any]:
    return {
        "transport": "claude-code-print",
        "model": model,
        "stdin_prompt": claude_code_prompt(
            request,
            validate_request=validate_request,
        ),
        "json_schema_argument": canonical_json_text(dict(response_schema)),
        "output_format": "json",
        "tools": "",
    }


def agent_mailbox_input(
    request: StageRequestLike,
    response_schema: JsonSchema,
    *,
    validate_request: bool = True,
) -> dict[str, Any]:
    # The durable StageRequest already carries the complete response schema.
    # Do not count or transport a second identical copy beside it.
    _ = response_schema
    return {
        "transport": "readwelt-agent-mailbox",
        "stage_request": request.to_dict(validate_budget=validate_request),
    }


def _request_without_embedded_response_schema(
    request: StageRequestLike,
    *,
    validate_request: bool,
) -> dict[str, Any]:
    """Project a request when the transport binds the schema separately."""

    value = request.to_dict(validate_budget=validate_request)
    value.pop("response_schema", None)
    return value


def provider_profiles(
    *,
    provider_name: str,
    provider_kind: str | None,
) -> tuple[ProviderEnvelopeProfile, ...]:
    """Resolve all profiles hidden behind a direct or resolver provider."""

    normalized = provider_name.strip().lower()
    if normalized.startswith("resolver:"):
        try:
            _, _, raw_kinds = normalized.split(":", 2)
            kinds = tuple(value for value in raw_kinds.split(",") if value)
        except ValueError as error:
            raise ProviderContractError(
                f"invalid resolver provider identity: {provider_name}"
            ) from error
        if not kinds:
            raise ProviderContractError("resolver provider has no candidate profiles")
        return tuple(dict.fromkeys(_profile_for_kind(kind) for kind in kinds))
    if provider_kind is not None:
        try:
            return (_profile_for_kind(str(provider_kind)),)
        except ValueError as error:
            raise ProviderContractError(
                f"unknown provider kind has no hard-budget profile: {provider_kind}"
            ) from error
    if "claude" in normalized:
        return (ProviderEnvelopeProfile.CLAUDE_CODE,)
    if "mailbox" in normalized or normalized in {"agent", "external-agent"}:
        return (ProviderEnvelopeProfile.AGENT_MAILBOX,)
    if "openai" in normalized or normalized in {"api", "local"}:
        return (ProviderEnvelopeProfile.OPENAI_CHAT,)
    raise ProviderContractError(
        f"provider {provider_name!r} has no declared hard-budget envelope profile"
    )


def measure_provider_input(
    request: StageRequestLike,
    response_schema: JsonSchema,
    *,
    profile: ProviderEnvelopeProfile,
    model: str,
    counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
    validate_request: bool = True,
) -> ProviderInputBudgetReceipt:
    envelope = _input_envelope(
        request,
        response_schema,
        profile=profile,
        model=model,
        validate_request=validate_request,
    )
    return ProviderInputBudgetReceipt(
        schema_version="provider-input-budget.v1",
        profile=profile,
        model=model,
        count=counter.count_json(envelope),
        hard_token_budget=request.hard_serialized_token_budget,
    )


def measure_planned_provider_inputs(
    request: StageRequestLike,
    response_schema: JsonSchema,
    *,
    profiles: tuple[ProviderEnvelopeProfile, ...],
    model: str,
    counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
) -> tuple[ProviderInputBudgetReceipt, ...]:
    return tuple(
        measure_provider_input(
            request,
            response_schema,
            profile=profile,
            model=model,
            counter=counter,
            validate_request=False,
        )
        for profile in profiles
    )


def validate_provider_input(
    request: StageRequestLike,
    response_schema: JsonSchema,
    *,
    profile: ProviderEnvelopeProfile,
    model: str,
    counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
) -> ProviderInputBudgetReceipt:
    receipt = measure_provider_input(
        request,
        response_schema,
        profile=profile,
        model=model,
        counter=counter,
    )
    if not receipt.within_budget:
        assert receipt.hard_token_budget is not None
        raise ProviderContractError(
            "complete provider input envelope exceeds hard provider budget: "
            f"{receipt.count.tokens}>{receipt.hard_token_budget} "
            f"({receipt.profile.value}, {receipt.count.counter_id})"
        )
    return receipt


def _input_envelope(
    request: StageRequestLike,
    response_schema: JsonSchema,
    *,
    profile: ProviderEnvelopeProfile,
    model: str,
    validate_request: bool,
) -> Mapping[str, Any]:
    if profile is ProviderEnvelopeProfile.OPENAI_CHAT:
        return openai_chat_payload(
            request,
            response_schema,
            model=model,
            validate_request=validate_request,
        )
    if profile is ProviderEnvelopeProfile.CLAUDE_CODE:
        return claude_code_input(
            request,
            response_schema,
            model=model,
            validate_request=validate_request,
        )
    if profile is ProviderEnvelopeProfile.AGENT_MAILBOX:
        return agent_mailbox_input(
            request,
            response_schema,
            validate_request=validate_request,
        )
    raise ProviderContractError(f"unsupported provider envelope profile: {profile}")


def _profile_for_kind(kind: str) -> ProviderEnvelopeProfile:
    if kind in {"api", "local"}:
        return ProviderEnvelopeProfile.OPENAI_CHAT
    if kind == "claude-code":
        return ProviderEnvelopeProfile.CLAUDE_CODE
    if kind == "agent":
        return ProviderEnvelopeProfile.AGENT_MAILBOX
    raise ProviderContractError(f"provider kind has no input envelope profile: {kind}")

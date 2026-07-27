from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from readwelt.provider_input import (
    ProviderEnvelopeProfile,
    agent_mailbox_input,
    claude_code_input,
    openai_chat_payload,
    validate_provider_input,
)
from readwelt.providers import (
    OpenAICompatibleProvider,
    ProviderContractError,
    ProviderResolver,
    ProviderSelection,
    StageRequest,
)
from readwelt.providers.request_budget import settle_stage_request
from readwelt.token_budget import ExactTokenizerCounter, Utf8ByteUpperBoundCounter


def _request(*, text: str = "证据") -> StageRequest:
    return StageRequest(
        schema_version="1",
        run_id="run-provider-budget",
        stage="stage_1_mainline",
        evidence_packet={
            "anchors": [
                {
                    "anchor_id": "anchor-1",
                    "exact_text": text,
                }
            ]
        },
        response_schema={"type": "object", "properties": {}},
    )


def test_utf8_counter_is_auditable_and_does_not_underestimate_chinese() -> None:
    text = "深度阅读" * 100
    count = Utf8ByteUpperBoundCounter().count_text(text)

    assert count.mode.value == "conservative_upper_bound"
    assert count.tokens == len(text.encode("utf-8"))
    assert count.tokens > (len(text.encode("utf-8")) + 3) // 4
    assert "at most one input token" in count.guarantee


def test_exact_tokenizer_adapter_records_identity_and_mode() -> None:
    counter = ExactTokenizerCounter(
        "fixture-tokenizer@revision-1",
        lambda text: text.split(),
    )

    count = counter.count_text("one two three")

    assert count.counter_id == "fixture-tokenizer@revision-1"
    assert count.mode.value == "exact"
    assert count.tokens == 3


def test_exact_counter_can_recover_capacity_without_weakening_default_bound() -> None:
    exact = ExactTokenizerCounter(
        "fixture-provider-tokenizer@revision-1",
        lambda text: range((len(text) + 3) // 4),
    )
    with pytest.raises(ProviderContractError, match="minimum complete"):
        settle_stage_request(
            _request(text="中文证据" * 40),
            hard_serialized_token_budget=2_000,
            provider_name="openai-compatible",
            provider_kind="api",
            provider_model="model-a",
        )

    settled = settle_stage_request(
        _request(text="中文证据" * 40),
        hard_serialized_token_budget=2_000,
        provider_name="openai-compatible",
        provider_kind="api",
        provider_model="model-a",
        token_counter=exact,
    )
    receipt = validate_provider_input(
        settled,
        settled.response_schema,
        profile=ProviderEnvelopeProfile.OPENAI_CHAT,
        model="model-a",
        counter=exact,
    )

    assert receipt.within_budget
    assert receipt.count.mode.value == "exact"
    assert receipt.to_dict()["unused_headroom_tokens"] >= 0
    assert settled.budget_manifest["counter"]["counter_id"] == exact.counter_id


def test_primary_resolver_preserves_provider_exact_counter_for_planning() -> None:
    exact = ExactTokenizerCounter(
        "fixture-openai-tokenizer@revision-1",
        lambda text: range((len(text) + 3) // 4),
    )
    provider = OpenAICompatibleProvider(
        model="model-a",
        api_key="secret",  # pragma: allowlist secret
        token_counter=exact,
    )
    resolver = ProviderResolver((provider,))
    selection = ProviderSelection.build(primary="api")

    assert resolver.planning_token_counter(selection) is exact


def test_settlement_reserves_all_resolver_compare_envelopes() -> None:
    settled = settle_stage_request(
        _request(text="中文证据" * 20),
        hard_serialized_token_budget=10_000,
        provider_name="resolver:compare:local,claude-code",
        provider_model="provider-resolver",
    )

    provider_input = settled.budget_manifest["provider_input"]
    profiles = {receipt["profile"] for receipt in provider_input["receipts"]}
    assert profiles == {
        "openai_chat_completions.v1",
        "claude_code_print_json_schema.v1",
    }
    assert provider_input["max_tokens"] == max(
        receipt["tokens"] for receipt in provider_input["receipts"]
    )
    assert provider_input["max_tokens"] <= 10_000


def test_unknown_provider_without_declared_profile_fails_closed() -> None:
    with pytest.raises(ProviderContractError, match="no declared hard-budget"):
        settle_stage_request(
            _request(),
            hard_serialized_token_budget=10_000,
            provider_name="unknown-model-host",
        )


def test_openai_revalidates_actual_schema_before_network_call() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    async def scenario() -> None:
        request = settle_stage_request(
            _request(),
            hard_serialized_token_budget=8_000,
            provider_name="openai-compatible",
            provider_kind="api",
            provider_model="model-a",
        )
        oversized_schema = {
            "type": "object",
            "description": "模式" * 4_000,
        }
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                model="model-a",
                api_key="secret",  # pragma: allowlist secret
                client=client,
            )
            with pytest.raises(
                ProviderContractError,
                match="complete provider input envelope exceeds",
            ):
                await provider.generate(request, oversized_schema)

    asyncio.run(scenario())
    assert calls == 0


def test_final_receipt_covers_instructions_request_and_response_schema() -> None:
    request = settle_stage_request(
        _request(text="中文"),
        hard_serialized_token_budget=8_000,
        provider_name="claude-code",
        provider_kind="claude-code",
        provider_model="claude-test",
    )

    receipt = validate_provider_input(
        request,
        request.response_schema,
        profile=ProviderEnvelopeProfile.CLAUDE_CODE,
        model="claude-test",
    )

    assert receipt.within_budget
    assert receipt.count.tokens > request.estimated_serialized_tokens
    assert receipt.to_dict()["profile"] == "claude_code_print_json_schema.v1"
    assert receipt.to_dict()["profile_tokenizer_contract"] == {"max_input_tokens_per_utf8_byte": 1}


def test_provider_transports_bind_one_response_schema_copy() -> None:
    request = _request()
    schema = request.response_schema

    openai = openai_chat_payload(request, schema, model="model-a")
    openai_request = json.loads(openai["messages"][1]["content"])
    assert "response_schema" not in openai_request
    assert openai["response_format"]["json_schema"]["schema"] == schema

    claude = claude_code_input(request, schema, model="claude-test")
    assert '"response_schema"' not in claude["stdin_prompt"]
    assert json.loads(claude["json_schema_argument"]) == schema

    mailbox = agent_mailbox_input(request, schema)
    assert mailbox["stage_request"]["response_schema"] == schema
    assert "response_schema" not in mailbox

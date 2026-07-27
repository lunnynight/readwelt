"""Host-neutral, auditable token-counting contracts."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class TokenCountMode(StrEnum):
    EXACT = "exact"
    CONSERVATIVE_UPPER_BOUND = "conservative_upper_bound"


@dataclass(frozen=True, slots=True)
class TokenCount:
    counter_id: str
    mode: TokenCountMode
    tokens: int
    utf8_bytes: int
    guarantee: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "counter_id": self.counter_id,
            "mode": self.mode.value,
            "tokens": self.tokens,
            "utf8_bytes": self.utf8_bytes,
            "guarantee": self.guarantee,
        }


class InputTokenCounter(Protocol):
    """Count one fully serialized model-input envelope."""

    @property
    def counter_id(self) -> str: ...

    @property
    def mode(self) -> TokenCountMode: ...

    @property
    def guarantee(self) -> str: ...

    def count_text(self, value: str) -> TokenCount: ...

    def count_json(self, value: object) -> TokenCount: ...


class Utf8ByteUpperBoundCounter:
    """Upper bound for a profile emitting at most one token per UTF-8 byte."""

    counter_id = "readwelt.utf8_bytes.max_1_token_per_byte.v1"
    mode = TokenCountMode.CONSERVATIVE_UPPER_BOUND
    guarantee = (
        "valid only for provider profiles declaring that serialized model input "
        "emits at most one input token per non-empty UTF-8 byte"
    )

    def count_text(self, value: str) -> TokenCount:
        encoded = value.encode("utf-8")
        return TokenCount(
            counter_id=self.counter_id,
            mode=self.mode,
            tokens=max(1, len(encoded)),
            utf8_bytes=len(encoded),
            guarantee=self.guarantee,
        )

    def count_json(self, value: object) -> TokenCount:
        return self.count_text(canonical_json_text(value))


class ExactTokenizerCounter:
    """Thin adapter around a provider/model tokenizer supplied by the host."""

    mode = TokenCountMode.EXACT
    guarantee = "provider/model tokenizer exact count for the serialized envelope"

    def __init__(self, counter_id: str, encode: Callable[[str], object]) -> None:
        if not counter_id.strip():
            raise ValueError("exact token counter id must be non-empty")
        self._counter_id = counter_id.strip()
        self._encode = encode

    @property
    def counter_id(self) -> str:
        return self._counter_id

    def count_text(self, value: str) -> TokenCount:
        encoded = self._encode(value)
        try:
            tokens = len(encoded)  # type: ignore[arg-type]
        except TypeError as error:
            raise ValueError(
                f"exact token counter {self.counter_id} returned a non-sized value"
            ) from error
        if tokens < 0:
            raise ValueError(f"exact token counter {self.counter_id} returned a negative count")
        return TokenCount(
            counter_id=self.counter_id,
            mode=self.mode,
            tokens=tokens,
            utf8_bytes=len(value.encode("utf-8")),
            guarantee=self.guarantee,
        )

    def count_json(self, value: object) -> TokenCount:
        return self.count_text(canonical_json_text(value))


DEFAULT_TOKEN_COUNTER = Utf8ByteUpperBoundCounter()


def canonical_json_text(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json_bytes(value: object) -> bytes:
    return canonical_json_text(value).encode("utf-8")


def require_counter_receipt(value: Mapping[str, Any]) -> None:
    counter_id = value.get("counter_id")
    mode = value.get("mode")
    tokens = value.get("tokens")
    guarantee = value.get("guarantee")
    if not isinstance(counter_id, str) or not counter_id:
        raise ValueError("provider input budget has no token counter id")
    if mode not in {item.value for item in TokenCountMode}:
        raise ValueError("provider input budget has an invalid counter mode")
    if not isinstance(tokens, int) or tokens < 0:
        raise ValueError("provider input budget has an invalid token count")
    if not isinstance(guarantee, str) or not guarantee:
        raise ValueError("provider input budget has no counter guarantee")

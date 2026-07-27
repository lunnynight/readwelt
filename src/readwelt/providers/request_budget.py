"""Authoritative settlement of the complete provider-bound StageRequest."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from readwelt.article_graph.digest import content_digest

from .contracts import (
    DEFAULT_TOKEN_COUNTER,
    InputTokenCounter,
    ProviderContractError,
    ProviderEnvelopeProfile,
    StageRequest,
    canonical_json_bytes,
    measure_planned_provider_inputs,
    provider_profiles,
)

_PAGED_FIELDS = (
    "anchors",
    "retrieval_hits",
    "upstream_claims",
    "external_evidence",
    "external_evidence_omissions",
    "omitted_anchor_ids",
    "omitted_sections",
)


class MinimumProviderEnvelopeExceeded(ProviderContractError):
    """The irreducible provider envelope cannot fit its declared hard budget."""

    def __init__(self, actual_tokens: int, hard_budget: int) -> None:
        super().__init__(
            "minimum complete provider input envelope exceeds hard provider budget: "
            f"{actual_tokens}>{hard_budget}"
        )
        self.actual_tokens = actual_tokens
        self.hard_budget = hard_budget


def settle_stage_request(
    request: StageRequest,
    *,
    hard_serialized_token_budget: int,
    critical_anchor_ids: tuple[str, ...] = (),
    provider_name: str = "external-agent-mailbox",
    provider_kind: str | None = None,
    provider_model: str = "host-default",
    token_counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
) -> StageRequest:
    """Compact material and settle the complete planned provider envelope."""

    if hard_serialized_token_budget < 1:
        raise ProviderContractError("hard StageRequest budget must be positive")
    profiles = provider_profiles(
        provider_name=provider_name,
        provider_kind=provider_kind,
    )
    full_packet = dict(request.evidence_packet)
    critical = frozenset(critical_anchor_ids)
    ordered = {
        field: _prioritized(field, full_packet.get(field, ()), critical) for field in _PAGED_FIELDS
    }
    limits = {
        "anchors": 24,
        "retrieval_hits": 24,
        "upstream_claims": 12,
        "external_evidence": 8,
        "external_evidence_omissions": 8,
        "omitted_anchor_ids": 8,
        "omitted_sections": 8,
    }
    minimum_limits = {
        field: (
            sum(_anchor_id(item) in critical for item in values)
            if field in {"anchors", "retrieval_hits", "upstream_claims"}
            else 0
        )
        for field, values in ordered.items()
    }
    limits = {
        field: min(len(ordered[field]), max(limit, minimum_limits[field]))
        for field, limit in limits.items()
    }
    placeholder_digest = f"sha256:{'0' * 64}"
    provenance = {**dict(request.provenance), "request_digest": placeholder_digest}

    while True:
        packet = _settled_packet(full_packet, ordered, limits, critical)
        manifest = {
            "schema_version": "stage-request-budget.v2",
            "hard_serialized_token_budget": hard_serialized_token_budget,
            "counter": {
                "counter_id": token_counter.counter_id,
                "mode": token_counter.mode.value,
                "guarantee": token_counter.guarantee,
            },
            "provider_envelope_profiles": [item.value for item in profiles],
            "material_counts": {field: len(values) for field, values in ordered.items()},
            "material_digests": {
                field: content_digest(values) for field, values in ordered.items()
            },
            "critical_anchor_count": len(critical),
            "critical_anchor_digest": content_digest(tuple(sorted(critical))),
            "recovery": "readwelt_persisted_stage_inputs",
        }
        candidate = replace(
            request,
            evidence_packet=packet,
            provenance=provenance,
            hard_serialized_token_budget=hard_serialized_token_budget,
            estimated_serialized_tokens=0,
            budget_manifest=manifest,
        )
        candidate = _with_stable_estimates(
            candidate,
            profiles=profiles,
            provider_model=provider_model,
            token_counter=token_counter,
        )
        assert candidate.estimated_serialized_tokens is not None
        provider_tokens = _planned_provider_tokens(candidate.budget_manifest)
        if provider_tokens <= hard_serialized_token_budget:
            break
        reducible = [field for field in _PAGED_FIELDS if limits[field] > minimum_limits[field]]
        if not reducible:
            raise MinimumProviderEnvelopeExceeded(
                provider_tokens,
                hard_serialized_token_budget,
            )
        field = max(
            reducible,
            key=lambda item: _page_weight(ordered[item], limits[item]),
        )
        limits[field] -= 1

    unbound = candidate.to_dict(validate_budget=False)
    raw_provenance = dict(unbound["provenance"])
    raw_provenance.pop("request_digest", None)
    unbound["provenance"] = raw_provenance
    request_digest = "sha256:" + hashlib.sha256(_canonical_json_bytes(unbound)).hexdigest()
    settled = replace(
        candidate,
        provenance={**raw_provenance, "request_digest": request_digest},
    )
    if _planned_provider_tokens(settled.budget_manifest) > hard_serialized_token_budget:
        raise ProviderContractError("settled provider envelope exceeds hard provider budget")
    settled.to_dict()
    return settled


def serialized_request_tokens(value: Mapping[str, Any]) -> int:
    """Return the declared conservative upper bound, never ``bytes / 4``."""

    return DEFAULT_TOKEN_COUNTER.count_json(value).tokens


def stage_request_material_page(
    field: str,
    values: tuple[Any, ...],
    *,
    cursor: str | None = None,
    limit: int = 64,
    critical_anchor_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Recover one integrity-bound page from persisted request material."""

    if field not in _PAGED_FIELDS:
        raise ProviderContractError(f"unsupported StageRequest material: {field}")
    if limit < 0:
        raise ProviderContractError("StageRequest material page limit cannot be negative")
    critical = frozenset(critical_anchor_ids)
    ordered = _prioritized(field, values, critical)
    manifest_digest = content_digest(ordered)
    offset = _material_cursor_offset(cursor, field, manifest_digest) if cursor is not None else 0
    if offset > len(ordered):
        raise ProviderContractError("StageRequest material cursor offset is out of range")
    page = ordered[offset : offset + limit]
    next_offset = offset + len(page)
    critical_total = sum(_anchor_id(item) in critical for item in ordered)
    critical_presented = sum(_anchor_id(item) in critical for item in page)
    return {
        "schema_version": "stage-request-material-page.v1",
        "material": field,
        "total_count": len(ordered),
        "manifest_digest": manifest_digest,
        "offset": offset,
        "returned_count": len(page),
        "items": list(page),
        "critical_count": critical_total,
        "critical_presented_count": critical_presented,
        "next_cursor": (
            _material_cursor(field, manifest_digest, next_offset)
            if next_offset < len(ordered)
            else None
        ),
    }


def _settled_packet(
    packet: dict[str, Any],
    ordered: dict[str, tuple[Any, ...]],
    limits: dict[str, int],
    critical: frozenset[str],
) -> dict[str, Any]:
    settled = {key: value for key, value in packet.items() if key not in _PAGED_FIELDS}
    for field in _PAGED_FIELDS:
        settled[field] = _material_page(
            field,
            ordered[field],
            limit=limits[field],
            critical=critical,
        )
    return settled


def _material_page(
    field: str,
    values: tuple[Any, ...],
    *,
    limit: int,
    critical: frozenset[str],
) -> dict[str, Any]:
    return stage_request_material_page(
        field,
        values,
        limit=limit,
        critical_anchor_ids=tuple(critical),
    )


def _prioritized(
    field: str,
    value: object,
    critical: frozenset[str],
) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    values = tuple(value)
    if field not in {"anchors", "retrieval_hits", "upstream_claims"}:
        return values
    return tuple(item for item in values if _anchor_id(item) in critical) + tuple(
        item for item in values if _anchor_id(item) not in critical
    )


def _anchor_id(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    anchor_id = value.get("anchor_id")
    if isinstance(anchor_id, str):
        return anchor_id
    anchor_ids = value.get("anchor_ids")
    if isinstance(anchor_ids, (list, tuple)):
        return next((str(item) for item in anchor_ids if isinstance(item, str)), None)
    return None


def _material_cursor(field: str, digest: str, offset: int) -> str:
    payload = {"field": field, "manifest_digest": digest, "offset": offset}
    return f"stage-request-material.v1:{offset}:{content_digest(payload)}"


def _material_cursor_offset(cursor: str, field: str, digest: str) -> int:
    try:
        schema, raw_offset, cursor_digest = cursor.split(":", 2)
        offset = int(raw_offset)
    except (TypeError, ValueError) as error:
        raise ProviderContractError("invalid StageRequest material cursor") from error
    payload = {"field": field, "manifest_digest": digest, "offset": offset}
    if schema != "stage-request-material.v1" or cursor_digest != content_digest(payload):
        raise ProviderContractError("stale or incompatible StageRequest material cursor")
    return offset


def _page_weight(values: tuple[Any, ...], limit: int) -> int:
    if limit <= 0:
        return 0
    return len(canonical_json_bytes(values[limit - 1]))


def _with_stable_estimates(
    request: StageRequest,
    *,
    profiles: tuple[ProviderEnvelopeProfile, ...],
    provider_model: str,
    token_counter: InputTokenCounter,
) -> StageRequest:
    candidate = request
    for _ in range(16):
        request_tokens = token_counter.count_json(candidate.to_dict(validate_budget=False)).tokens
        receipts = measure_planned_provider_inputs(
            replace(candidate, estimated_serialized_tokens=request_tokens),
            candidate.response_schema,
            profiles=profiles,
            model=provider_model,
            counter=token_counter,
        )
        receipt_values = [item.to_dict() for item in receipts]
        provider_input = {
            "schema_version": "provider-input-planning.v1",
            "receipts": receipt_values,
            "max_tokens": max(item.count.tokens for item in receipts),
        }
        manifest = {
            **dict(candidate.budget_manifest),
            "provider_input": provider_input,
        }
        next_candidate = replace(
            candidate,
            estimated_serialized_tokens=request_tokens,
            budget_manifest=manifest,
        )
        if (
            next_candidate.estimated_serialized_tokens == candidate.estimated_serialized_tokens
            and next_candidate.budget_manifest == candidate.budget_manifest
        ):
            return candidate
        candidate = next_candidate
    raise ProviderContractError("provider input budget estimates did not stabilize")


def _planned_provider_tokens(manifest: Mapping[str, Any]) -> int:
    provider_input = manifest.get("provider_input")
    if not isinstance(provider_input, Mapping):
        raise ProviderContractError("StageRequest budget has no provider input receipt")
    value = provider_input.get("max_tokens")
    if not isinstance(value, int) or value < 0:
        raise ProviderContractError("StageRequest provider input count is invalid")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return canonical_json_bytes(value)

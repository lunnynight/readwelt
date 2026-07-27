"""Provider-selection normalization and deterministic application run identity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from readwelt.domain import SourceDocumentSnapshot, stable_id
from readwelt.providers import (
    CandidateProvider,
    ProviderConflictError,
    ProviderKind,
    ProviderMode,
    ProviderSelection,
    ProviderUnavailableError,
)


class ProviderSelectionHost(Protocol):
    _configured_providers: tuple[CandidateProvider, ...]


def normalize_selection(
    service: ProviderSelectionHost,
    value: ProviderSelection | Mapping[str, Any] | None,
) -> ProviderSelection:
    if isinstance(value, ProviderSelection):
        selection = value
    elif isinstance(value, Mapping):
        selection = ProviderSelection.build(
            mode=str(value.get("mode", ProviderMode.PRIMARY)),
            primary=value.get("primary"),
            candidates=value.get("candidates", ()),
        )
    elif value is None:
        selection = default_selection(service)
    else:
        raise TypeError("provider_selection must be a ProviderSelection or mapping")
    if (
        selection.mode is ProviderMode.PRIMARY
        and selection.primary is None
        and not selection.candidates
    ):
        selection = default_selection(service)
    if selection.mode is not ProviderMode.AGENT_TAKEOVER and selection.primary is None:
        raise ProviderUnavailableError("provider selection has no primary provider")
    return selection


def default_selection(service: ProviderSelectionHost) -> ProviderSelection:
    model_kinds = tuple(
        dict.fromkeys(
            provider.kind
            for provider in service._configured_providers
            if provider.kind is not ProviderKind.AGENT
        )
    )
    if not model_kinds:
        raise ProviderUnavailableError(
            "no model provider is configured; select agent_takeover or configure "
            "a local/API provider"
        )
    if len(model_kinds) > 1:
        raise ProviderConflictError(
            "multiple providers are configured; select primary, compare, or fallback"
        )
    return ProviderSelection.build(primary=model_kinds[0])


def new_run_id(
    snapshot: SourceDocumentSnapshot,
    selection: ProviderSelection,
    *,
    pipeline_policy: str,
    idempotency_key: str,
) -> str:
    policy = json.dumps(selection.to_dict(), sort_keys=True, separators=(",", ":"))
    return stable_id(
        "run",
        snapshot.snapshot_id,
        pipeline_policy,
        policy,
        "schema:1",
        idempotency_key,
    )

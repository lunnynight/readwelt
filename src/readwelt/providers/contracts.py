"""Transport-neutral contracts used by external candidate providers.

The domain layer owns stage validation and settlement.  These types only define
the versioned JSON envelope exchanged with an external agent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ProviderContractError(ValueError):
    """A provider request cannot be represented by the public contract."""

    code = "provider_contract_error"


class ProviderConflictError(ProviderContractError):
    """More than one provider was selected without an explicit policy."""

    code = "provider_conflict"


class ProviderUnavailableError(ProviderContractError):
    """The selected provider transport is unavailable."""

    code = "provider_unavailable"


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
    capabilities: tuple[str, ...] = ()
    resource_uri: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

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
            capabilities=tuple(str(item) for item in value.get("capabilities", ())),
            resource_uri=(
                str(value["resource_uri"]) if value.get("resource_uri") is not None else None
            ),
            provenance=dict(value.get("provenance", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

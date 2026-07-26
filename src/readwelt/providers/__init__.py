"""Provider-facing contracts and adapter validation."""

from .agent_mailbox import ExternalAgentMailboxProvider
from .config import configured_model_providers
from .contracts import (
    AgentInputRequired,
    ProviderConflictError,
    ProviderContractError,
    ProviderKind,
    ProviderMode,
    ProviderSelection,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
)
from .local import LocalOpenAICompatibleProvider
from .model_protocol import CandidateProvider, JsonSchema
from .openai_compatible import OpenAICompatibleProvider, validate_json_schema
from .resolver import ProviderResolution, ProviderResolver, ResolutionStatus

__all__ = [
    "AgentInputRequired",
    "ExternalAgentMailboxProvider",
    "configured_model_providers",
    "ProviderContractError",
    "ProviderConflictError",
    "ProviderKind",
    "ProviderMode",
    "ProviderSelection",
    "ProviderUnavailableError",
    "StageCandidate",
    "StageRequest",
    "CandidateProvider",
    "JsonSchema",
    "LocalOpenAICompatibleProvider",
    "OpenAICompatibleProvider",
    "ProviderResolution",
    "ProviderResolver",
    "ResolutionStatus",
    "validate_json_schema",
]

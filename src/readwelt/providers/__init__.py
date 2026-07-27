"""Provider-facing contracts and adapter validation."""

from .agent_mailbox import ExternalAgentMailboxProvider
from .claude_code import ClaudeCodeProvider
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
    validate_json_schema,
)
from .local import LocalOpenAICompatibleProvider
from .model_protocol import CandidateProvider, JsonSchema
from .openai_compatible import OpenAICompatibleProvider
from .request_budget import (
    MinimumProviderEnvelopeExceeded,
    settle_stage_request,
    stage_request_material_page,
)
from .resolver import ProviderResolution, ProviderResolver, ResolutionStatus

__all__ = [
    "AgentInputRequired",
    "ClaudeCodeProvider",
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
    "settle_stage_request",
    "stage_request_material_page",
    "CandidateProvider",
    "JsonSchema",
    "LocalOpenAICompatibleProvider",
    "MinimumProviderEnvelopeExceeded",
    "OpenAICompatibleProvider",
    "ProviderResolution",
    "ProviderResolver",
    "ResolutionStatus",
    "validate_json_schema",
]

"""Environment-backed provider construction without implicit provider selection."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .claude_code import ClaudeCodeProvider
from .contracts import ProviderKind
from .local import LocalOpenAICompatibleProvider
from .model_protocol import CandidateProvider
from .openai_compatible import OpenAICompatibleProvider


def configured_model_providers(
    environment: Mapping[str, str] | None = None,
    *,
    requested: str | ProviderKind | None = None,
) -> tuple[CandidateProvider, ...]:
    """Build configured transports; the caller must still select one."""

    env = os.environ if environment is None else environment
    providers: list[CandidateProvider] = []
    local_model = env.get("READWELT_LOCAL_MODEL", "").strip()
    if local_model:
        providers.append(
            LocalOpenAICompatibleProvider(
                model=local_model,
                base_url=env.get(
                    "READWELT_LOCAL_BASE_URL",
                    "http://127.0.0.1:11434/v1",
                ),
                api_key=env.get("READWELT_LOCAL_API_KEY", "local"),
            )
        )
    api_model = env.get("READWELT_API_MODEL", "").strip()
    if api_model:
        providers.append(
            OpenAICompatibleProvider(
                model=api_model,
                base_url=env.get(
                    "READWELT_API_BASE_URL",
                    "https://api.openai.com/v1",
                ),
                api_key=env.get("READWELT_API_KEY") or env.get("OPENAI_API_KEY"),
            )
        )
    requested_kind = ProviderKind(requested) if requested is not None else None
    claude_enabled = env.get("READWELT_CLAUDE_CODE_ENABLED", "").strip().lower()
    if requested_kind is ProviderKind.CLAUDE_CODE or claude_enabled in {"1", "true", "yes", "on"}:
        providers.append(
            ClaudeCodeProvider(
                executable=env.get("READWELT_CLAUDE_CODE_BIN") or None,
                model=env.get("READWELT_CLAUDE_CODE_MODEL") or None,
                timeout_seconds=float(env.get("READWELT_CLAUDE_CODE_TIMEOUT_SECONDS", "300")),
                settings_path=env.get("READWELT_CLAUDE_SETTINGS_PATH") or None,
                import_settings_environment=env.get("READWELT_CLAUDE_IMPORT_SETTINGS_ENV", "1")
                .strip()
                .lower()
                not in {"0", "false", "no", "off"},
                bare=env.get("READWELT_CLAUDE_CODE_BARE", "1").strip().lower()
                not in {"0", "false", "no", "off"},
            )
        )
    return tuple(providers)

"""Environment-backed provider construction without implicit provider selection."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .local import LocalOpenAICompatibleProvider
from .model_protocol import CandidateProvider
from .openai_compatible import OpenAICompatibleProvider


def configured_model_providers(
    environment: Mapping[str, str] | None = None,
) -> tuple[CandidateProvider, ...]:
    """Build configured local/API transports; the caller must still select one."""

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
    return tuple(providers)

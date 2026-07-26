"""Loopback-only OpenAI-compatible provider."""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlparse

import httpx

from .contracts import ProviderContractError, ProviderKind
from .openai_compatible import OpenAICompatibleProvider


def _require_loopback(base_url: str) -> None:
    parsed = urlparse(base_url)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or hostname is None:
        raise ProviderContractError("local provider base_url must be an HTTP(S) URL")
    if hostname.lower() == "localhost":
        return
    try:
        if ip_address(hostname).is_loopback:
            return
    except ValueError:
        pass
    raise ProviderContractError("local provider base_url must use localhost or a loopback address")


class LocalOpenAICompatibleProvider(OpenAICompatibleProvider):
    """Adapter for Ollama, llama.cpp, vLLM, or another loopback server."""

    kind = ProviderKind.LOCAL

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434/v1",
        api_key: str = "local",
        name: str = "local-openai-compatible",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        _require_loopback(base_url)
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            name=name,
            timeout_seconds=timeout_seconds,
            client=client,
        )

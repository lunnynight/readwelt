from readwelt.providers import (
    ClaudeCodeProvider,
    LocalOpenAICompatibleProvider,
    OpenAICompatibleProvider,
    configured_model_providers,
)


def test_configured_model_providers_are_opt_in() -> None:
    assert configured_model_providers({}) == ()


def test_configured_model_providers_build_local_and_api_without_selecting() -> None:
    providers = configured_model_providers(
        {
            "READWELT_LOCAL_MODEL": "qwen",
            "READWELT_API_MODEL": "remote-model",
            "READWELT_API_KEY": "secret",  # pragma: allowlist secret
        }
    )

    assert isinstance(providers[0], LocalOpenAICompatibleProvider)
    assert isinstance(providers[1], OpenAICompatibleProvider)


def test_explicit_claude_code_selection_builds_real_host_provider(tmp_path) -> None:
    executable = tmp_path / "claude.exe"
    executable.write_bytes(b"test executable")

    providers = configured_model_providers(
        {"READWELT_CLAUDE_CODE_BIN": str(executable)},
        requested="claude-code",
    )

    assert len(providers) == 1
    assert isinstance(providers[0], ClaudeCodeProvider)

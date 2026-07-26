from readwelt.providers import (
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

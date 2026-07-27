"""Real Claude Code CLI provider using the host's existing authentication."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import (
    DEFAULT_TOKEN_COUNTER,
    InputTokenCounter,
    ProviderContractError,
    ProviderEnvelopeProfile,
    ProviderKind,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
    claude_code_prompt,
    validate_json_schema,
    validate_provider_input,
)
from .model_protocol import JsonSchema

_CLAUDE_PACKAGE_EXECUTABLE = Path("npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe")
_ROUTING_ENV_PREFIX = "ANTHROPIC_"


class ClaudeCodeProvider:
    """Generate stage candidates through a real, non-interactive Claude Code process."""

    kind = ProviderKind.CLAUDE_CODE

    def __init__(
        self,
        *,
        executable: str | Path | None = None,
        model: str | None = None,
        timeout_seconds: float = 300.0,
        settings_path: str | Path | None = None,
        import_settings_environment: bool = True,
        bare: bool = True,
        token_counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._executable = _resolve_executable(executable)
        self._model = model.strip() if model and model.strip() else None
        self._timeout_seconds = timeout_seconds
        self._settings_path = (
            Path(settings_path).expanduser()
            if settings_path is not None
            else Path.home() / ".claude" / "settings.json"
        )
        self._import_settings_environment = import_settings_environment
        self._bare = bare
        self._token_counter = token_counter

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def model(self) -> str:
        return self._model or "host-default"

    @property
    def input_token_counter(self) -> InputTokenCounter:
        return self._token_counter

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate:
        prompt = _prompt(request)
        schema_json = json.dumps(
            dict(response_schema),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        command = self._command(schema_json)
        input_budget = validate_provider_input(
            request,
            response_schema,
            profile=ProviderEnvelopeProfile.CLAUDE_CODE,
            model=self.model,
            counter=self._token_counter,
        )
        environment, credential_source = self._environment()
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tempfile.gettempdir(),
                env=environment,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise ProviderUnavailableError(
                f"{self.name} could not start the verified CLI executable"
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ProviderUnavailableError(
                f"{self.name} timed out after {self._timeout_seconds:g} seconds"
            ) from exc

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if not stdout_text:
            detail = _safe_process_detail(stderr_text)
            raise ProviderUnavailableError(f"{self.name} returned no structured output{detail}")

        payload, events = _decode_cli_output(stdout_text)
        result = _result_envelope(payload, events)
        if process.returncode != 0 or result.get("is_error") is True:
            status = result.get("api_error_status")
            message = str(result.get("result") or "host process failed")
            suffix = f" (HTTP {status})" if status is not None else ""
            raise ProviderUnavailableError(
                f"{self.name} is unavailable{suffix}: {_safe_process_detail(message, prefix=False)}"
            )

        candidate = _structured_candidate(result)
        validate_json_schema(candidate, response_schema)
        model = _actual_model(result, events) or self.model
        usage = _usage(result)
        init = next(
            (
                event
                for event in events
                if event.get("type") == "system" and event.get("subtype") == "init"
            ),
            {},
        )
        return StageCandidate(
            schema_version=request.schema_version,
            run_id=request.run_id,
            stage=request.stage,
            candidate=dict(candidate),
            provider=self.name,
            model=model,
            provenance={
                **dict(request.provenance),
                "provider_kind": self.kind.value,
                "provider": self.name,
                "model": model,
                "host_receipt": {
                    "host": "claude-code",
                    "host_version": init.get("claude_code_version"),
                    "executable_name": self._executable.name,
                    "credential_source": credential_source,
                    "bare": self._bare,
                    "session_id": result.get("session_id"),
                    "duration_ms": result.get("duration_ms"),
                    "total_cost_usd": result.get("total_cost_usd"),
                    "token_usage": usage,
                    "provider_input_budget": input_budget.to_dict(),
                    "exit_code": process.returncode,
                },
            },
            raw_response=dict(result),
        )

    def _command(self, schema_json: str) -> list[str]:
        command = [str(self._executable)]
        if self._bare:
            command.append("--bare")
        command.extend(
            (
                "-p",
                "--output-format",
                "json",
                "--json-schema",
                schema_json,
                "--tools",
                "",
                "--no-session-persistence",
                "--disable-slash-commands",
            )
        )
        if self._model is not None:
            command.extend(("--model", self._model))
        return command

    def _environment(self) -> tuple[dict[str, str], str]:
        environment = dict(os.environ)
        imported = False
        if self._import_settings_environment and self._settings_path.is_file():
            try:
                settings = json.loads(self._settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProviderUnavailableError(
                    f"{self.name} could not read Claude settings"
                ) from exc
            configured = settings.get("env", {})
            if not isinstance(configured, Mapping):
                raise ProviderContractError("Claude settings env must be an object")
            for key, value in configured.items():
                name = str(key)
                if name.startswith(_ROUTING_ENV_PREFIX) and isinstance(value, (str, int, float)):
                    environment[name] = str(value)
                    imported = True
        environment.pop("CLAUDE_BIN_PATH", None)
        environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        source = "claude_user_settings_env" if imported else "process_environment"
        return environment, source


def _resolve_executable(executable: str | Path | None) -> Path:
    if executable is not None:
        candidate = Path(executable).expanduser().resolve()
        if not candidate.is_file():
            raise ProviderUnavailableError("configured Claude Code executable does not exist")
        return candidate

    configured = os.environ.get("READWELT_CLAUDE_CODE_BIN", "").strip()
    if configured:
        return _resolve_executable(configured)

    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        packaged = (Path(appdata) / _CLAUDE_PACKAGE_EXECUTABLE).resolve()
        if packaged.is_file():
            return packaged

    discovered = shutil.which("claude")
    if discovered:
        candidate = Path(discovered).resolve()
        if os.name != "nt" or candidate.suffix.lower() not in {".bat", ".cmd", ".ps1"}:
            return candidate
    raise ProviderUnavailableError(
        "official Claude Code executable was not found; set READWELT_CLAUDE_CODE_BIN explicitly"
    )


def _prompt(request: StageRequest) -> str:
    return claude_code_prompt(request)


def _decode_cli_output(
    stdout: str,
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProviderContractError("claude-code returned invalid JSON") from exc
    if isinstance(value, Mapping):
        return value, ()
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        events = tuple(value)
        return {}, events
    raise ProviderContractError("claude-code returned an unsupported JSON envelope")


def _result_envelope(
    payload: Mapping[str, Any],
    events: tuple[Mapping[str, Any], ...],
) -> Mapping[str, Any]:
    if payload:
        return payload
    for event in reversed(events):
        if event.get("type") == "result":
            return event
    raise ProviderContractError("claude-code output has no result envelope")


def _structured_candidate(result: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = result.get("structured_output")
    if isinstance(candidate, Mapping):
        return candidate
    text = result.get("result")
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderContractError("claude-code result is not valid structured JSON") from exc
        if isinstance(parsed, Mapping):
            return parsed
    raise ProviderContractError("claude-code returned no structured candidate")


def _actual_model(
    result: Mapping[str, Any],
    events: tuple[Mapping[str, Any], ...],
) -> str | None:
    model_usage = result.get("modelUsage")
    if isinstance(model_usage, Mapping) and model_usage:
        return str(next(iter(model_usage)))
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            model = event.get("model")
            if model is not None:
                return str(model)
    return None


def _usage(result: Mapping[str, Any]) -> dict[str, int]:
    usage = result.get("usage")
    if not isinstance(usage, Mapping):
        return {}
    keys = (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    )
    return {key: int(usage[key]) for key in keys if isinstance(usage.get(key), int)}


def _safe_process_detail(value: str, *, prefix: bool = True) -> str:
    compact = " ".join(value.split())
    if not compact:
        return ""
    clipped = compact[:300]
    return f": {clipped}" if prefix else clipped

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from readwelt.providers import ClaudeCodeProvider, StageRequest


class _FakeProcess:
    returncode = 0

    def __init__(self, stdout: bytes) -> None:
        self.stdout = stdout
        self.stdin_value = b""
        self.killed = False

    async def communicate(self, value: bytes) -> tuple[bytes, bytes]:
        self.stdin_value = value
        return self.stdout, b""

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


def test_claude_code_provider_runs_verified_cli_and_records_host_receipt(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    executable = tmp_path / "claude.exe"
    executable.write_bytes(b"test executable")
    secret = "host-secret"
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": secret,
                    "ANTHROPIC_MODEL": "claude-test",
                    "CLAUDE_BIN_PATH": "untrusted-wrapper",
                    "UNRELATED_SECRET": "must-not-be-imported",
                }
            }
        ),
        encoding="utf-8",
    )
    output = json.dumps(
        [
            {
                "type": "system",
                "subtype": "init",
                "model": "claude-test",
                "claude_code_version": "9.9.9",
            },
            {
                "type": "result",
                "is_error": False,
                "session_id": "session-1",
                "duration_ms": 25,
                "total_cost_usd": 0.01,
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "modelUsage": {"claude-test": {}},
                "structured_output": {"ok": True},
            },
        ]
    ).encode()
    process = _FakeProcess(output)
    captured: dict[str, Any] = {}

    async def fake_create(*args: str, **kwargs: Any) -> _FakeProcess:
        captured["args"] = args
        captured["environment"] = kwargs["env"]
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    provider = ClaudeCodeProvider(
        executable=executable,
        settings_path=settings,
        timeout_seconds=5,
    )
    request = StageRequest(
        schema_version="1",
        run_id="run-1",
        stage="stage_1_mainline",
        evidence_packet={"anchors": []},
    )
    schema = {
        "type": "object",
        "properties": {"ok": {"const": True}},
        "required": ["ok"],
        "additionalProperties": False,
    }

    candidate = asyncio.run(provider.generate(request, schema))

    assert candidate.candidate == {"ok": True}
    assert candidate.provider == "claude-code"
    assert candidate.model == "claude-test"
    assert captured["args"][0] == str(executable.resolve())
    assert "--bare" in captured["args"]
    assert "run-1" not in captured["args"]
    assert b"run-1" in process.stdin_value
    assert captured["environment"]["ANTHROPIC_AUTH_TOKEN"] == secret
    assert "CLAUDE_BIN_PATH" not in captured["environment"]
    assert "UNRELATED_SECRET" not in captured["environment"]
    receipt = candidate.provenance["host_receipt"]
    assert receipt["host_version"] == "9.9.9"
    assert receipt["session_id"] == "session-1"
    assert receipt["provider_input_budget"]["profile"] == ("claude_code_print_json_schema.v1")
    assert secret not in json.dumps(candidate.to_dict())

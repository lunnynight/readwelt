from __future__ import annotations

import io
import json

from readwelt.application import ReadweltApplicationService
from readwelt.cli.main import main

from .fakes import FakeService


def test_read_command_calls_shared_service(tmp_path) -> None:
    service = FakeService(tmp_path)
    output = io.StringIO()

    exit_code = main(
        ["read", "article.txt", "--json"],
        service=service,
        stdout=output,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue())["run_id"] == "run-1"
    assert service.calls[0][0] == "read"


def test_prepare_supports_async_service_method(tmp_path) -> None:
    output = io.StringIO()

    exit_code = main(
        ["prepare", "doc-1", "--json"],
        service=FakeService(tmp_path),
        stdout=output,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue())["status"] == "prepared"


def test_article_graph_page_command_calls_shared_service(tmp_path) -> None:
    service = FakeService(tmp_path)
    output = io.StringIO()

    exit_code = main(
        [
            "article-graph-page",
            "doc-1",
            "--collection",
            "claims",
            "--limit",
            "17",
            "--json",
        ],
        service=service,
        stdout=output,
    )

    assert exit_code == 0
    page = json.loads(output.getvalue())
    assert page["schema_version"] == "readwelt.article-graph-page.v1"
    assert service.calls[-1] == (
        "get_article_graph_page",
        ("doc-1",),
        {"collection": "claims", "limit": 17, "cursor": None},
    )


def test_provider_conflict_has_stable_machine_error(tmp_path) -> None:
    error = io.StringIO()

    exit_code = main(
        [
            "read",
            "article.txt",
            "--provider",
            "local",
            "--candidate-provider",
            "api",
            "--json",
        ],
        service=FakeService(tmp_path),
        stderr=error,
    )

    assert exit_code == 2
    assert json.loads(error.getvalue())["error"]["code"] == "provider_conflict"


def test_quiet_does_not_print_result(tmp_path) -> None:
    output = io.StringIO()

    exit_code = main(
        ["import", "article.txt", "--quiet"],
        service=FakeService(tmp_path),
        stdout=output,
    )

    assert exit_code == 0
    assert output.getvalue() == ""


def test_cli_integrates_with_real_application_facade(tmp_path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("Evidence should remain anchored.", encoding="utf-8")
    project = tmp_path / ".readwelt"
    service = ReadweltApplicationService(project, ingestion_backend="plain_text")
    output = io.StringIO()

    exit_code = main(
        [
            "read",
            str(source),
            "--provider-mode",
            "agent_takeover",
            "--json",
        ],
        service=service,
        stdout=output,
    )

    result = json.loads(output.getvalue())
    assert exit_code == 0
    assert result["execution_status"] == "pending"
    assert result["current_task"] == "awaiting_agent:stage_1_mainline"
    assert service.get_run_status(result["run_id"]).run_id == result["run_id"]


def test_cli_exposes_host_neutral_agent_turn(tmp_path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("CLI Agent 底座。", encoding="utf-8")
    project = tmp_path / ".readwelt"
    service = ReadweltApplicationService(
        project,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    output = io.StringIO()

    exit_code = main(
        [
            "agent-start",
            str(source),
            "--idempotency-key",
            "cli-agent-turn",
            "--json",
        ],
        service=service,
        stdout=output,
    )
    turn = json.loads(output.getvalue())

    assert exit_code == 0
    assert turn["action"] == "generate_stage_candidate"
    assert turn["stage"] == "stage_1_mainline"
    assert turn["request"]["response_schema"]["type"] == "object"

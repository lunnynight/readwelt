from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_cli(
    *args: str,
    stdin: str | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "readwelt.cli", *args],
        capture_output=True,
        text=True,
        input=stdin,
        timeout=timeout,
        check=False,
    )


def _candidate(turn: dict[str, Any]) -> dict[str, Any]:
    stage = str(turn["stage"])
    request = turn["request"]
    evidence = request["evidence_packet"]
    anchors = evidence["anchors"]
    count = 2 if stage == "stage_4_author_model" else 1
    claims = [
        {
            "claim_id": f"{stage}:cli:{index}",
            "text": f"{stage} candidate {index}",
            "anchor_ids": [anchors[0]["anchor_id"]],
            "decision": "accepted",
            **(
                {"provenance": {"interpretation_id": f"cli-lens-{index}"}}
                if stage == "stage_4_author_model"
                else {}
            ),
        }
        for index in range(count)
    ]
    if stage not in {"stage_1_mainline", "stage_2_structure"}:
        claims[0]["source_claim_ids"] = [evidence["upstream_claims"][0]["claim_id"]]
        for claim in claims[1:]:
            claim["source_claim_ids"] = [evidence["upstream_claims"][0]["claim_id"]]
    return {"claims": claims, "gaps": [], "warnings": []}


def test_short_lived_cli_completes_agent_loop_and_retrieves_artifact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "article.txt"
    source.write_text(
        "Readwelt CLI 保留原文锚点，并由宿主 Agent 完成六阶段理解。", encoding="utf-8"
    )
    project = tmp_path / ".readwelt"

    doctor = _run_cli("doctor", "--project", str(project), "--json")
    assert doctor.returncode == 0, doctor.stderr
    diagnosis = json.loads(doctor.stdout)
    assert diagnosis["schema_version"] == "readwelt.doctor.v1"
    assert diagnosis["process_model"] == "short_lived_cli"
    assert diagnosis["mcp_required"] is False

    started = _run_cli(
        "agent-start",
        str(source),
        "--project",
        str(project),
        "--idempotency-key",
        "short-lived-cli-e2e",
        "--json",
    )
    assert started.returncode == 0, started.stderr
    turn = json.loads(started.stdout)
    run_id = turn["run_id"]

    resumed = _run_cli("agent-turn", run_id, "--project", str(project), "--json")
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout) == turn

    while turn["action"] == "generate_stage_candidate":
        submitted = _run_cli(
            "agent-submit",
            run_id,
            "-",
            "--agent-name",
            "cli-process-test",
            "--model",
            "host-model",
            "--project",
            str(project),
            "--json",
            stdin=json.dumps(_candidate(turn), ensure_ascii=False),
        )
        assert submitted.returncode == 0, submitted.stderr
        turn = json.loads(submitted.stdout)

    assert turn["action"] == "completed"
    report = next(
        item for item in turn["outputs"] if item["artifact_type"] == "reader_report_markdown"
    )
    metadata = _run_cli(
        "artifact-get",
        report["content_digest"],
        "--project",
        str(project),
        "--json",
    )
    assert metadata.returncode == 0, metadata.stderr
    artifact = json.loads(metadata.stdout)
    assert artifact["schema_version"] == "readwelt.artifact.v1"
    assert artifact["digest"] == report["content_digest"]
    assert "content" not in artifact
    assert (project / artifact["path"]).is_file()

    content = _run_cli(
        "artifact-get",
        report["content_digest"],
        "--content",
        "--project",
        str(project),
        "--json",
    )
    assert content.returncode == 0, content.stderr
    assert json.loads(content.stdout)["content"].startswith("# 逆向阅读")


def test_mutation_lock_is_cross_process_bounded_and_released_on_exit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "article.txt"
    source.write_text("跨进程锁。", encoding="utf-8")
    project = tmp_path / ".readwelt"
    lock_path = project / ".locks" / "mutation.lock"
    holder_script = (
        "import sys,time\n"
        "from pathlib import Path\n"
        "from filelock import FileLock\n"
        "path=Path(sys.argv[1]); path.parent.mkdir(parents=True, exist_ok=True)\n"
        "lock=FileLock(path); lock.acquire(); print('locked', flush=True); time.sleep(60)\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_script, str(lock_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"

        busy = _run_cli(
            "import",
            str(source),
            "--project",
            str(project),
            "--lock-timeout",
            "0",
            "--json",
        )
        assert busy.returncode == 2
        assert busy.stdout == ""
        assert json.loads(busy.stderr)["error"]["code"] == "project_busy"

        inspection = _run_cli("doctor", "--project", str(project), "--json")
        assert inspection.returncode == 0
        assert json.loads(inspection.stdout)["ready"] is True
    finally:
        holder.terminate()
        holder.wait(timeout=10)

    imported = _run_cli(
        "import",
        str(source),
        "--project",
        str(project),
        "--lock-timeout",
        "1",
        "--json",
    )
    assert imported.returncode == 0, imported.stderr
    assert json.loads(imported.stdout)["document_id"]


def test_invalid_json_mode_arguments_emit_only_structured_error() -> None:
    invalid = _run_cli("agent-submit", "--json")

    assert invalid.returncode == 2
    assert invalid.stdout == ""
    assert json.loads(invalid.stderr)["error"]["code"] == "invalid_arguments"

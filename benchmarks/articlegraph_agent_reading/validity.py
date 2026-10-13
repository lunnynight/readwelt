"""Fail-closed validity gates for matched ArticleGraph reading runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED_USAGE = {
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
}


def validate_pair(
    baseline: dict[str, Any], treatment: dict[str, Any], *, artifact_root: Path
) -> dict[str, list[str]]:
    """Return all failures; callers must exclude a pair when either list is non-empty."""
    failures = {
        "baseline": validate_run(baseline, artifact_root=artifact_root),
        "treatment": validate_run(treatment, artifact_root=artifact_root),
    }
    if baseline.get("matched_config_fingerprint") != treatment.get(
        "matched_config_fingerprint"
    ):
        failures["baseline"].append("matched_config_mismatch")
        failures["treatment"].append("matched_config_mismatch")
    if baseline.get("document_id") != treatment.get("document_id"):
        failures["baseline"].append("matched_document_mismatch")
        failures["treatment"].append("matched_document_mismatch")
    if not baseline.get("resolved_model") or baseline.get("resolved_model") != treatment.get(
        "resolved_model"
    ):
        failures["baseline"].append("resolved_model_mismatch")
        failures["treatment"].append("resolved_model_mismatch")
    return failures


def validate_run(record: dict[str, Any], *, artifact_root: Path) -> list[str]:
    failures: list[str] = []
    condition = record.get("condition")
    if condition not in {"baseline", "treatment"}:
        failures.append("unknown_condition")
    if record.get("exit_code") != 0:
        failures.append("agent_nonzero_exit")
    if not isinstance(record.get("wall_ms"), (int, float)):
        failures.append("missing_wall_clock_telemetry")
    usage = record.get("usage")
    if not isinstance(usage, dict) or any(
        key not in usage or not isinstance(usage[key], int) for key in REQUIRED_USAGE
    ):
        failures.append("incomplete_cost_telemetry")
    exposed = record.get("exposed_evidence")
    if not isinstance(exposed, dict) or not all(
        isinstance(exposed.get(key), int) for key in ("characters", "estimated_tokens")
    ):
        failures.append("incomplete_exposed_evidence_telemetry")
    if record.get("context_failure") is not False:
        failures.append("context_failure")
    answer = record.get("final_answer")
    if not isinstance(answer, dict) or not isinstance(answer.get("answers"), list):
        failures.append("unparseable_final_answer")

    commands = _bash_commands(record.get("trajectory"))
    if any(
        marker in command
        for command in commands
        for marker in ("pip install", "remove-item", "rm -", "del ", "git clean")
    ):
        failures.append("forbidden_tool_mutation")
    graph_commands = [command for command in commands if "articlegraph query" in command]
    if condition == "baseline" and graph_commands:
        failures.append("baseline_used_articlegraph")
    if condition == "treatment":
        if not graph_commands:
            failures.append("missing_treatment_use")
        failures.extend(_validate_receipts(record, artifact_root=artifact_root))
    return list(dict.fromkeys(failures))


def _bash_commands(trajectory: Any) -> list[str]:
    if not isinstance(trajectory, list):
        return []
    commands: list[str] = []
    for event in trajectory:
        if not isinstance(event, dict) or event.get("type") != "tool_use":
            continue
        if str(event.get("name", "")).lower() not in {"bash", "powershell"}:
            continue
        tool_input = event.get("input", {})
        if isinstance(tool_input, dict):
            commands.append(str(tool_input.get("command", "")).lower())
    return commands


def _validate_receipts(record: dict[str, Any], *, artifact_root: Path) -> list[str]:
    receipts = record.get("query_receipts")
    if not isinstance(receipts, list) or not receipts:
        return ["missing_query_receipts"]
    trajectory_ids = set(record.get("trajectory_receipt_ids", []))
    stored_ids: set[str] = set()
    failures: list[str] = []
    for entry in receipts:
        if not isinstance(entry, dict):
            failures.append("malformed_query_receipt")
            continue
        receipt_id = str(entry.get("receipt_id", ""))
        relative = Path(str(entry.get("artifact_path", "")))
        expected_digest = str(entry.get("artifact_sha256", ""))
        if not receipt_id or relative.is_absolute() or ".." in relative.parts:
            failures.append("malformed_query_receipt")
            continue
        path = artifact_root / relative
        try:
            raw = path.read_bytes()
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            failures.append("unreadable_query_receipt")
            continue
        actual_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        stored_receipt = payload.get("receipt", payload)
        if (
            actual_digest != expected_digest
            or not isinstance(stored_receipt, dict)
            or stored_receipt.get("receipt_id") != receipt_id
        ):
            failures.append("mismatched_query_receipt")
            continue
        stored_ids.add(receipt_id)
    if stored_ids != trajectory_ids:
        failures.append("mismatched_query_receipt_ids")
    answers = record.get("final_answer", {}).get("answers", [])
    answer_receipt_ids: set[str] = set()
    answers_have_receipts = bool(answers)
    for answer in answers:
        ids = answer.get("receipt_ids", []) if isinstance(answer, dict) else []
        if not isinstance(ids, list) or not ids:
            answers_have_receipts = False
            continue
        answer_receipt_ids.update(str(item) for item in ids)
    if not answers_have_receipts or not answer_receipt_ids.issubset(stored_ids):
        failures.append("final_answer_receipt_mismatch")
    return failures


__all__ = ["REQUIRED_USAGE", "validate_pair", "validate_run"]

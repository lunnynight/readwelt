from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.articlegraph_agent_reading.protocol import MatchedConfig, assert_matched_configs
from benchmarks.articlegraph_agent_reading.report import build_report
from benchmarks.articlegraph_agent_reading.runner import (
    normalize_trajectory,
    parse_events,
    persist_query_receipts,
)
from benchmarks.articlegraph_agent_reading.validity import validate_pair, validate_run


def _config(*, model: str = "claude-sonnet-4-5") -> MatchedConfig:
    return MatchedConfig(
        model=model,
        effort="medium",
        max_turns=12,
        max_budget_usd=1.0,
        agent_timeout_seconds=480,
        system_prompt_sha256="sha256:system",
        response_schema_sha256="sha256:schema",
        execution_policy="isolated-readonly.v1",
    )


def _record(condition: str) -> dict[str, object]:
    trajectory: list[dict[str, object]] = []
    if condition == "treatment":
        trajectory.append(
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "readwelt articlegraph query search doc --query x"},
            }
        )
    return {
        "condition": condition,
        "document_id": "d001",
        "matched_config_fingerprint": _config().fingerprint,
        "resolved_model": "resolved-test-model",
        "exit_code": 0,
        "wall_ms": 100.0 if condition == "baseline" else 80.0,
        "usage": {
            "input_tokens": 100 if condition == "baseline" else 60,
            "output_tokens": 20,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
        "trajectory": trajectory,
        "trajectory_receipt_ids": [],
        "query_receipts": [],
        "exposed_evidence": {"characters": 200, "estimated_tokens": 50},
        "context_failure": False,
        "final_answer": {"answers": [{"task_id": "t1", "answer": "x"}]},
        "scores": {"location": 1.0, "citation": 1.0, "comprehension_lexical_screen": 1.0},
        "reported_failures": [],
        "infrastructure_costs": {
            "cold_build_ms": 1000.0,
            "warm_query_ms": 20.0,
            "amortized_ms": 61.0,
        },
    }


def _attach_receipt(record: dict[str, object], root: Path) -> None:
    payload = {"receipt": {"receipt_id": "receipt-1"}, "results": []}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    path = root / "receipts" / "receipt-1.json"
    path.parent.mkdir()
    path.write_bytes(raw)
    record["trajectory_receipt_ids"] = ["receipt-1"]
    record["query_receipts"] = [
        {
            "receipt_id": "receipt-1",
            "artifact_path": "receipts/receipt-1.json",
            "artifact_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        }
    ]
    record["final_answer"] = {
        "answers": [{"task_id": "t1", "answer": "x", "receipt_ids": ["receipt-1"]}]
    }


def test_matched_configuration_fails_on_any_behavior_difference() -> None:
    assert_matched_configs(_config(), _config())
    with pytest.raises(ValueError, match="model"):
        assert_matched_configs(_config(), _config(model="claude-opus-4-1"))


def test_treatment_requires_direct_query_trajectory_and_matching_receipt(
    tmp_path: Path,
) -> None:
    treatment = _record("treatment")
    assert validate_run(treatment, artifact_root=tmp_path) == ["missing_query_receipts"]
    _attach_receipt(treatment, tmp_path)
    assert validate_run(treatment, artifact_root=tmp_path) == []
    treatment["trajectory"] = []
    assert "missing_treatment_use" in validate_run(treatment, artifact_root=tmp_path)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda item: item.update(final_answer="not-json"), "unparseable_final_answer"),
        (lambda item: item.update(context_failure=True), "context_failure"),
        (lambda item: item.update(usage={"input_tokens": 1}), "incomplete_cost_telemetry"),
    ],
)
def test_validity_gates_fail_closed(tmp_path: Path, mutation: object, expected: str) -> None:
    record = _record("baseline")
    mutation(record)  # type: ignore[operator]
    assert expected in validate_run(record, artifact_root=tmp_path)


def test_pair_rejects_mismatched_config_and_receipt_digest(tmp_path: Path) -> None:
    baseline = _record("baseline")
    treatment = _record("treatment")
    _attach_receipt(treatment, tmp_path)
    treatment["matched_config_fingerprint"] = "sha256:other"
    receipt = treatment["query_receipts"][0]  # type: ignore[index]
    receipt["artifact_sha256"] = "sha256:wrong"  # type: ignore[index]
    failures = validate_pair(baseline, treatment, artifact_root=tmp_path)
    assert "matched_config_mismatch" in failures["baseline"]
    assert "mismatched_query_receipt" in failures["treatment"]


def test_report_keeps_product_and_infrastructure_metrics_separate(tmp_path: Path) -> None:
    baseline = _record("baseline")
    treatment = _record("treatment")
    _attach_receipt(treatment, tmp_path)
    treatment["scores"] = {
        "location": 1.0,
        "citation": 1.0,
        "comprehension_lexical_screen": 1.5,
    }
    baseline["scores"] = {
        "location": 0.0,
        "citation": 0.5,
        "comprehension_lexical_screen": 1.0,
    }
    report = build_report([{"baseline": baseline, "treatment": treatment}], artifact_root=tmp_path)
    assert report["pair_validity"]["rate"] == 1.0
    assert report["quality"]["location"]["absolute_gain"] == 1.0
    assert report["quality"]["comprehension_lexical_screen"]["treatment"] == 1.5
    assert "comprehension" not in report["quality"]
    assert report["tokens"]["treatment"]["input_tokens"] == 60.0
    assert report["infrastructure"] == {
        "cold_build_ms": 1000.0,
        "warm_query_ms": 20.0,
        "amortized_ms": 61.0,
    }


def test_stream_trajectory_is_normalized_and_receipt_is_immutable(tmp_path: Path) -> None:
    query_payload = {"receipt": {"receipt_id": "receipt-trajectory"}, "hits": []}
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "Bash",
                        "input": {"command": "readwelt articlegraph query search doc"},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call-1",
                        "content": f"Exit code 0\n{json.dumps(query_payload)}",
                    }
                ]
            },
        },
    ]
    stdout = "\n".join(json.dumps(item) for item in events)
    trajectory = normalize_trajectory(parse_events(stdout))
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    receipts = persist_query_receipts(trajectory, run_dir=run_dir)
    assert [item["receipt_id"] for item in receipts] == ["receipt-trajectory"]
    assert receipts[0]["artifact_path"] == "run-1/receipts/receipt-trajectory.json"
    assert (run_dir / "receipts" / "receipt-trajectory.json").is_file()

"""Official-Claude matched runner for the ArticleGraph Agent Reading benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .protocol import (
    BASELINE,
    OFFICIAL_CLAUDE,
    TREATMENT,
    Condition,
    MatchedConfig,
    digest_json,
)
from .report import build_report
from .scoring import score_answers

SYSTEM_PROMPT = (
    "You are a controlled document-reading benchmark participant. "
    "Do not use subagents, networking, or file mutation. Use only the allowed "
    "read-only command access and return the requested JSON."
)
RUN_SCHEMA = "readwelt.articlegraph-agent-reading-run.v1"
DISABLED_PLUGINS = {
    plugin: False
    for plugin in (
        "context-mode@context-mode",
        "equity-research@financial-services-plugins",
        "financial-analysis@financial-services-plugins",
        "investment-banking@financial-services-plugins",
        "private-equity@financial-services-plugins",
        "wealth-management@financial-services-plugins",
        "understand-anything@understand-anything",
    )
}


def response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answers"],
        "properties": {
            "answers": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "task_id",
                        "answer",
                        "quote",
                        "page",
                        "source_locator",
                        "receipt_ids",
                    ],
                    "properties": {
                        "task_id": {"type": "string"},
                        "answer": {"type": "string"},
                        "quote": {"type": "string"},
                        "page": {"type": ["integer", "null"]},
                        "source_locator": {"type": "string"},
                        "receipt_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        },
    }


def matched_config(args: argparse.Namespace) -> MatchedConfig:
    return MatchedConfig(
        model=args.model,
        effort=args.effort,
        max_turns=args.max_turns,
        max_budget_usd=args.max_budget_usd,
        agent_timeout_seconds=args.agent_timeout_seconds,
        system_prompt_sha256=digest_json(SYSTEM_PROMPT),
        response_schema_sha256=digest_json(response_schema()),
        execution_policy="official-claude-isolated-readonly.v1",
    )


def build_prompt(
    document: dict[str, Any], condition: Condition, *, project: Path, repository: Path
) -> str:
    tasks = "\n".join(
        f"- {task['task_id']}: {task['question']}" for task in document["tasks"]
    )
    source = Path(document["source_path"]).resolve()
    access = [f"源 PDF：{source}"]
    if condition.articlegraph_enabled:
        readwelt = repository / ".venv" / "Scripts" / "readwelt.exe"
        access.extend(
            [
                f"Readwelt 项目：{project.resolve()}",
                f"ArticleGraph document_id：{document['prepared_document_id']}",
                "必须实际调用下面的只读命令族检索每个问题；仅复述命令或直接读取 PDF 均判无效：",
                f'"{readwelt}" articlegraph query search '
                f'"{document["prepared_document_id"]}" --query "QUERY_TEXT" '
                "--max-hits 5 --max-evidence-characters 4000 "
                "--max-estimated-tokens 1200 "
                f'--project "{project.resolve()}" --json',
                "每题最多一次 search，共最多三次；不得调用其他 ArticleGraph 子命令，"
                "不得 grep Claude 的 persisted-output 文件。",
                "回答中的 receipt_ids 必须抄录实际查询 JSON 的 receipt.receipt_id。",
            ]
        )
    else:
        access.extend(
            [
                f"只能用仓库虚拟环境 {repository / '.venv' / 'Scripts' / 'python.exe'} "
                "和其中已有的 PyMuPDF 只读读取源 PDF。",
                "禁止安装依赖；尽量在一个 Python 命令中抽取并回答三个任务。",
                "不得调用 Readwelt、ArticleGraph、其项目目录或任何预构建产物。",
                "receipt_ids 必须为空数组。",
            ]
        )
    return "\n".join(
        [
            "完成同一文档的三个受控任务。定位和引文必须给出可复核页码与最小充分原文。",
            *access,
            tasks,
            "只提交满足 JSON schema 的对象，不要添加 schema 外字段。",
        ]
    )


def build_agent_command(
    document: dict[str, Any],
    condition: Condition,
    config: MatchedConfig,
    *,
    project: Path,
    repository: Path,
    session_id: str,
) -> list[str]:
    if not OFFICIAL_CLAUDE.is_file():
        raise FileNotFoundError(f"official Claude launcher not found: {OFFICIAL_CLAUDE}")
    return [
        str(OFFICIAL_CLAUDE),
        "-p",
        "--model",
        config.model,
        "--effort",
        config.effort,
        "--max-turns",
        str(config.max_turns),
        "--max-budget-usd",
        str(config.max_budget_usd),
        "--output-format",
        "stream-json",
        "--verbose",
        "--json-schema",
        json.dumps(response_schema(), ensure_ascii=False, separators=(",", ":")),
        "--session-id",
        session_id,
        "--system-prompt",
        SYSTEM_PROMPT,
        "--tools",
        "Bash",
        "--settings",
        json.dumps({"enabledPlugins": DISABLED_PLUGINS}, separators=(",", ":")),
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--exclude-dynamic-system-prompt-sections",
        "--disable-slash-commands",
        "--add-dir",
        str(Path(document["source_path"]).resolve().parent),
    ]


def prepare_document(
    document: dict[str, Any], *, project: Path, repository: Path
) -> dict[str, float | str]:
    readwelt = repository / ".venv" / "Scripts" / "readwelt.exe"
    started = time.perf_counter_ns()
    imported = _run_json_command(
        [
            str(readwelt),
            "import",
            str(Path(document["source_path"]).resolve()),
            "--project",
            str(project.resolve()),
            "--json",
        ],
        cwd=repository,
    )
    document_id = str(imported["document_id"])
    _run_json_command(
        [
            str(readwelt),
            "prepare",
            document_id,
            "--project",
            str(project.resolve()),
            "--json",
        ],
        cwd=repository,
    )
    cold_build_ms = (time.perf_counter_ns() - started) / 1_000_000
    return {"prepared_document_id": document_id, "cold_build_ms": cold_build_ms}


def measure_warm_queries(
    document: dict[str, Any], *, project: Path, repository: Path, output: Path
) -> float:
    readwelt = repository / ".venv" / "Scripts" / "readwelt.exe"
    elapsed = 0.0
    output.mkdir(parents=True, exist_ok=True)
    for task in document["tasks"]:
        started = time.perf_counter_ns()
        payload = _run_json_command(
            [
                str(readwelt),
                "articlegraph",
                "query",
                "search",
                str(document["prepared_document_id"]),
                "--query",
                str(task["question"]),
                "--project",
                str(project.resolve()),
                "--json",
            ],
            cwd=repository,
        )
        elapsed += (time.perf_counter_ns() - started) / 1_000_000
        (output / f"{task['task_id']}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return elapsed


def execute_condition(
    document: dict[str, Any],
    condition: Condition,
    config: MatchedConfig,
    *,
    project: Path,
    repository: Path,
    run_dir: Path,
    infrastructure: dict[str, float],
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=False)
    command = build_agent_command(
        document,
        condition,
        config,
        project=project,
        repository=repository,
        session_id=str(uuid.uuid4()),
    )
    prompt = build_prompt(document, condition, project=project, repository=repository)
    started = time.perf_counter_ns()
    process = subprocess.Popen(
        command,
        cwd=run_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(
            input=prompt, timeout=config.agent_timeout_seconds
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/pid", str(process.pid), "/t", "/f"],
                capture_output=True,
                check=False,
            )
        else:
            process.kill()
        stdout, stderr = process.communicate()
    wall_ms = (time.perf_counter_ns() - started) / 1_000_000
    (run_dir / "trajectory.jsonl").write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    events = parse_events(stdout)
    trajectory = normalize_trajectory(events)
    receipts = persist_query_receipts(trajectory, run_dir=run_dir)
    result = next((item for item in reversed(events) if item.get("type") == "result"), {})
    final_answer = result.get("structured_output")
    usage = result.get("usage", {})
    record: dict[str, Any] = {
        "schema_version": RUN_SCHEMA,
        "run_id": run_dir.name,
        "created_at": datetime.now(UTC).isoformat(),
        "condition": condition.id,
        "document_id": document["document_id"],
        "source_sha256": document["source_sha256"],
        "matched_config_fingerprint": config.fingerprint,
        "resolved_model": _resolved_model(events),
        "exit_code": process.returncode,
        "wall_ms": round(wall_ms, 3),
        "usage": _normalized_usage(usage),
        "trajectory": trajectory,
        "trajectory_receipt_ids": sorted(item["receipt_id"] for item in receipts),
        "query_receipts": receipts,
        "exposed_evidence": _exposed_evidence(trajectory),
        "context_failure": _context_failed(stderr, events),
        "final_answer": final_answer,
        "reported_failures": ["agent_timeout"] if timed_out else [],
        "infrastructure_costs": infrastructure,
    }
    if isinstance(final_answer, dict):
        record["scores"] = score_answers(document, final_answer)
    (run_dir / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def parse_events(stdout: str) -> list[dict[str, Any]]:
    stripped = stdout.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    events: list[dict[str, Any]] = []
    for line in stripped.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def normalize_trajectory(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trajectory: list[dict[str, Any]] = []
    for event in events:
        message = event.get("message", {})
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                trajectory.append(
                    {
                        "type": "tool_use",
                        "tool_use_id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("input", {}),
                    }
                )
            elif block.get("type") == "tool_result":
                raw_result = event.get("tool_use_result", {})
                result_meta = raw_result if isinstance(raw_result, dict) else {}
                trajectory.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.get("tool_use_id"),
                        "is_error": bool(block.get("is_error", False)),
                        "content": str(block.get("content", "")),
                        "stdout": str(result_meta.get("stdout", "")),
                        "stderr": str(result_meta.get("stderr", "")),
                        "persisted_output_path": str(
                            result_meta.get("persistedOutputPath", "")
                        ),
                        "persisted_output_size": int(
                            result_meta.get("persistedOutputSize", 0) or 0
                        ),
                    }
                )
    return trajectory


def persist_query_receipts(
    trajectory: list[dict[str, Any]], *, run_dir: Path
) -> list[dict[str, str]]:
    receipt_dir = run_dir / "receipts"
    stored: dict[str, dict[str, str]] = {}
    for event in trajectory:
        if event.get("type") != "tool_result" or event.get("is_error"):
            continue
        payload = _parse_object(str(event.get("stdout", "")))
        if not payload:
            persisted = Path(str(event.get("persisted_output_path", "")))
            if persisted.is_file():
                payload = _parse_object(persisted.read_text(encoding="utf-8"))
        if not payload:
            payload = _parse_object(str(event.get("content", "")))
        receipt = payload.get("receipt") if isinstance(payload, dict) else None
        if not isinstance(receipt, dict) or not receipt.get("receipt_id"):
            continue
        receipt_id = str(receipt["receipt_id"])
        receipt_dir.mkdir(parents=True, exist_ok=True)
        local_relative = Path("receipts") / f"{receipt_id}.json"
        relative = Path(run_dir.name) / local_relative
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        (run_dir / local_relative).write_bytes(raw)
        stored[receipt_id] = {
            "receipt_id": receipt_id,
            "artifact_path": relative.as_posix(),
            "artifact_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        }
    return [stored[key] for key in sorted(stored)]


def run_experiment(args: argparse.Namespace) -> Path:
    repository = Path(__file__).parents[2].resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents = manifest["documents"][: args.limit or None]
    config = matched_config(args)
    result_root: Path = Path(args.output) / (
        f"{args.phase}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    result_root.mkdir(parents=True, exist_ok=False)
    project = result_root / "project"
    pairs: list[dict[str, dict[str, Any]]] = []
    for index, original in enumerate(documents):
        document = dict(original)
        prepared = prepare_document(document, project=project, repository=repository)
        document.update(prepared)
        infra_dir = result_root / "infrastructure" / document["document_id"]
        warm_ms = measure_warm_queries(
            document, project=project, repository=repository, output=infra_dir
        )
        cold_ms = float(prepared["cold_build_ms"])
        infrastructure = {
            "cold_build_ms": round(cold_ms, 3),
            "warm_query_ms": round(warm_ms, 3),
            "amortized_ms": round(warm_ms + cold_ms / args.amortization_reads, 3),
        }
        conditions = [BASELINE, TREATMENT]
        random.Random(args.seed + index).shuffle(conditions)
        pair: dict[str, dict[str, Any]] = {}
        for condition in conditions:
            run_id = f"{document['document_id']}-{condition.id}-{uuid.uuid4().hex[:8]}"
            pair[condition.id] = execute_condition(
                document,
                condition,
                config,
                project=project,
                repository=repository,
                run_dir=result_root / "runs" / run_id,
                infrastructure=infrastructure,
            )
        pairs.append(pair)
        (result_root / "pairs.json").write_text(
            json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    report = build_report(pairs, artifact_root=result_root / "runs")
    (result_root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    protocol = {
        "phase": args.phase,
        "scored": args.phase == "scored",
        "manifest_digest": manifest["manifest_digest"],
        "preregistration_sha256": _sha256_file(
            Path(args.manifest).with_name("preregistration.json")
        ),
        "protocol_correction_log_sha256": _sha256_file(
            Path(args.manifest).with_name("protocol-corrections.md")
        ),
        "matched_config": config.__dict__,
        "matched_config_fingerprint": config.fingerprint,
        "seed": args.seed,
        "amortization_reads": args.amortization_reads,
        "documents": len(documents),
    }
    (result_root / "protocol.json").write_text(
        json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result_root


def _run_json_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("command must return one JSON object")
    return payload


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _parse_object(content: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _normalized_usage(usage: Any) -> dict[str, int]:
    raw = usage if isinstance(usage, dict) else {}
    return {
        key: int(raw.get(key, 0))
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
    }


def _resolved_model(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        message = event.get("message", {})
        if isinstance(message, dict) and message.get("model"):
            return str(message["model"])
    return None


def _exposed_evidence(trajectory: list[dict[str, Any]]) -> dict[str, int]:
    characters = sum(
        int(event.get("persisted_output_size", 0))
        or len(str(event.get("stdout") or event.get("content", "")))
        for event in trajectory
        if event.get("type") == "tool_result"
    )
    return {"characters": characters, "estimated_tokens": (characters + 3) // 4}


def _context_failed(stderr: str, events: list[dict[str, Any]]) -> bool:
    text = stderr + json.dumps(events, ensure_ascii=False)
    return any(
        marker in text.lower()
        for marker in ("context window", "prompt is too long", "maximum context")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=Path(__file__).with_name("d1") / "manifest.json"
    )
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("results")
    )
    parser.add_argument("--phase", choices=("pilot", "scored"), required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model", default="claude-sonnet-4-5")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument("--max-budget-usd", type=float, default=1.5)
    parser.add_argument("--agent-timeout-seconds", type=int, default=480)
    parser.add_argument("--seed", type=int, default=20260729)
    parser.add_argument("--amortization-reads", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.phase == "pilot" and not args.limit:
        raise ValueError("pilot requires an explicit --limit")
    if args.phase == "scored" and args.limit:
        raise ValueError("scored phase must run the complete frozen manifest")
    print(run_experiment(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

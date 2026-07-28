"""Readwelt command-line adapter.

This module intentionally contains no reading workflow logic.  It translates
CLI arguments into calls on the shared application service.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Never, TextIO

from readwelt.cli.locking import ProjectBusyError, project_mutation_lock
from readwelt.providers.contracts import (
    ProviderContractError,
    ProviderSelection,
)
from readwelt.providers.external_agent import ExternalAgentAdapter
from readwelt.providers.projection import (
    ensure_within_project,
    resolve_project_root,
    to_jsonable,
)
from readwelt.providers.service_port import (
    ApplicationServiceUnavailable,
    invoke,
    invoke_read,
    load_application_service,
)


class CLIArgumentError(ValueError):
    code = "invalid_arguments"


class ReadweltArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CLIArgumentError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = ReadweltArgumentParser(prog="readwelt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read", help="Import and execute the reading pipeline")
    read_parser.add_argument("source", help="A file, URL, or existing document id")
    read_parser.add_argument("--purpose", default="完整逆向阅读")
    read_parser.add_argument("--token-budget", type=int)
    read_parser.add_argument("--idempotency-key")
    _add_common_options(read_parser)
    _add_provider_options(read_parser)

    import_parser = subparsers.add_parser(
        "import", help="Import a document without starting a reading run"
    )
    import_parser.add_argument("source", help="A file or URL")
    _add_common_options(import_parser)

    prepare_parser = subparsers.add_parser(
        "prepare", help="Prepare semantic artifacts for a document"
    )
    prepare_parser.add_argument("document_id")
    _add_common_options(prepare_parser)

    batch_parser = subparsers.add_parser(
        "batch-prepare",
        help="Import and semantically prepare many documents without model calls",
    )
    batch_parser.add_argument("sources", nargs="+", help="Document paths")
    batch_parser.add_argument("--concurrency", type=int, default=8)
    _add_common_options(batch_parser)

    show_parser = subparsers.add_parser("show", help="Show a reading run status")
    show_parser.add_argument("run_id")
    _add_common_options(show_parser)

    agent_start = subparsers.add_parser(
        "agent-start",
        help="Start a provider-free reading and return the first host-neutral Agent turn",
    )
    agent_start.add_argument("source")
    agent_start.add_argument("--purpose", default="完整逆向阅读")
    agent_start.add_argument("--token-budget", type=int)
    agent_start.add_argument("--idempotency-key")
    _add_common_options(agent_start)

    agent_turn = subparsers.add_parser(
        "agent-turn",
        help="Return the current actionable turn for an Agent-owned reading",
    )
    agent_turn.add_argument("run_id")
    _add_common_options(agent_turn)

    agent_submit = subparsers.add_parser(
        "agent-submit",
        help="Submit a stage candidate JSON payload and return the next Agent turn",
    )
    agent_submit.add_argument("run_id")
    agent_submit.add_argument("candidate_file")
    agent_submit.add_argument("--agent-name", required=True)
    agent_submit.add_argument("--model")
    _add_common_options(agent_submit)

    artifact_get = subparsers.add_parser(
        "artifact-get",
        help="Return bounded metadata for a content-addressed artifact",
    )
    artifact_get.add_argument("digest")
    artifact_get.add_argument(
        "--content",
        action="store_true",
        help="Include artifact content explicitly; metadata-only by default",
    )
    _add_common_options(artifact_get)

    doctor = subparsers.add_parser(
        "doctor",
        help="Check the short-lived CLI environment without starting a provider",
    )
    _add_common_options(doctor)
    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        default=".readwelt",
        help="Project directory, relative to the current directory by default",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", dest="as_json")
    output.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--lock-timeout",
        type=float,
        help="Seconds to wait for another project mutation; defaults to 30",
    )


def _add_provider_options(parser: argparse.ArgumentParser) -> None:
    provider_choices = ("local", "api", "agent", "claude-code")
    parser.add_argument("--provider", choices=provider_choices)
    parser.add_argument(
        "--provider-mode",
        choices=("primary", "compare", "fallback", "agent_takeover"),
        default="primary",
    )
    parser.add_argument(
        "--candidate-provider",
        action="append",
        default=[],
        choices=provider_choices,
        help="Additional provider for compare/fallback mode; repeatable",
    )


async def execute(
    args: argparse.Namespace,
    service: object,
    *,
    project_root: Path,
    stdin: TextIO,
) -> Any:
    if args.command == "import":
        return await invoke(service, "import_document", args.source)
    if args.command == "prepare":
        return await invoke(service, "prepare", args.document_id)
    if args.command == "batch-prepare":
        return await invoke(
            service,
            "batch_prepare",
            args.sources,
            concurrency=args.concurrency,
        )
    if args.command == "show":
        return await invoke(service, "get_run_status", args.run_id)
    if args.command == "agent-start":
        return await ExternalAgentAdapter(service).start(
            args.source,
            purpose=args.purpose,
            token_budget=args.token_budget,
            idempotency_key=args.idempotency_key,
        )
    if args.command == "agent-turn":
        return await ExternalAgentAdapter(service).current(args.run_id)
    if args.command == "agent-submit":
        if args.candidate_file == "-":
            candidate = json.load(stdin)
        else:
            with Path(args.candidate_file).open(encoding="utf-8") as candidate_stream:
                candidate = json.load(candidate_stream)
        if not isinstance(candidate, dict):
            raise ValueError("candidate file must contain a JSON object")
        return await ExternalAgentAdapter(service).advance(
            args.run_id,
            candidate,
            agent_name=args.agent_name,
            model=args.model,
        )
    if args.command == "artifact-get":
        result = to_jsonable(await invoke(service, "get_artifact", args.digest))
        if not isinstance(result, dict):
            raise ValueError("artifact projection must be a JSON object")
        path = result.get("path")
        if not isinstance(path, str):
            raise ValueError("artifact projection has no path")
        ensure_within_project(project_root, path)
        if not args.content:
            result.pop("content", None)
            result.pop("content_encoding", None)
        return {"schema_version": "readwelt.artifact.v1", **result}
    if args.command == "read":
        selection = ProviderSelection.build(
            mode=args.provider_mode,
            primary=args.provider,
            candidates=args.candidate_provider,
        )
        return await invoke_read(
            service,
            args.source,
            selection,
            purpose=args.purpose,
            token_budget=args.token_budget,
            idempotency_key=args.idempotency_key,
        )
    raise AssertionError(f"unsupported command: {args.command}")


def main(
    argv: Sequence[str] | None = None,
    *,
    service: object | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    input_stream = stdin or sys.stdin
    parser = build_parser()
    raw_arguments = tuple(sys.argv[1:] if argv is None else argv)
    args: argparse.Namespace | None = None

    try:
        args = parser.parse_args(raw_arguments)
        project_root = resolve_project_root(args.project)
        if args.command == "doctor":
            result = _doctor(project_root)
        elif args.command in _MUTATING_COMMANDS:
            with project_mutation_lock(project_root, timeout=args.lock_timeout):
                active_service = service or load_application_service(
                    project_root,
                    requested_provider=getattr(args, "provider", None),
                )
                result = asyncio.run(
                    execute(
                        args,
                        active_service,
                        project_root=project_root,
                        stdin=input_stream,
                    )
                )
        else:
            active_service = service or load_application_service(
                project_root,
                requested_provider=getattr(args, "provider", None),
            )
            result = asyncio.run(
                execute(
                    args,
                    active_service,
                    project_root=project_root,
                    stdin=input_stream,
                )
            )
        if not args.quiet:
            projected = to_jsonable(result)
            if args.as_json:
                print(json.dumps(projected, ensure_ascii=False, sort_keys=True), file=out)
            else:
                print(_human_output(args.command, projected), file=out)
        return 0
    except (
        OSError,
        ProjectBusyError,
        ProviderContractError,
        ApplicationServiceUnavailable,
        ValueError,
    ) as exc:
        code = getattr(exc, "code", "invalid_request")
        payload = {"error": {"code": code, "message": str(exc)}}
        if getattr(args, "as_json", False) or "--json" in raw_arguments:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=err)
        else:
            print(f"{code}: {exc}", file=err)
        return 2


_MUTATING_COMMANDS = frozenset(
    {
        "read",
        "import",
        "prepare",
        "batch-prepare",
        "agent-start",
        "agent-submit",
    }
)


def _doctor(project_root: Path) -> dict[str, object]:
    existing_directory = project_root if project_root.exists() else project_root.parent
    try:
        package_version = version("readwelt")
    except PackageNotFoundError:
        package_version = "source"
    writable = existing_directory.is_dir() and os.access(existing_directory, os.W_OK)
    return {
        "schema_version": "readwelt.doctor.v1",
        "version": package_version,
        "project_root": str(project_root),
        "project_exists": project_root.is_dir(),
        "writable": writable,
        "ready": writable,
        "process_model": "short_lived_cli",
        "mcp_required": False,
    }


def _human_output(command: str, value: Any) -> str:
    if isinstance(value, dict):
        preferred = (
            ("run_id", "status", "stage", "action")
            if command in ("read", "show", "agent-start", "agent-turn", "agent-submit")
            else ("document_id", "status")
        )
        visible = [f"{key}={value[key]}" for key in preferred if key in value]
        if visible:
            return " ".join(visible)
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())

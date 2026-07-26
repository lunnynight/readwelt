"""Readwelt command-line adapter.

This module intentionally contains no reading workflow logic.  It translates
CLI arguments into calls on the shared application service.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from readwelt.providers.contracts import (
    ProviderContractError,
    ProviderSelection,
)
from readwelt.providers.projection import resolve_project_root, to_jsonable
from readwelt.providers.service_port import (
    ApplicationServiceUnavailable,
    invoke,
    invoke_read,
    load_application_service,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="readwelt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read", help="Import and execute the reading pipeline")
    read_parser.add_argument("source", help="A file, URL, or existing document id")
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


def _add_provider_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=("local", "api", "agent"))
    parser.add_argument(
        "--provider-mode",
        choices=("primary", "compare", "fallback", "agent_takeover"),
        default="primary",
    )
    parser.add_argument(
        "--candidate-provider",
        action="append",
        default=[],
        choices=("local", "api", "agent"),
        help="Additional provider for compare/fallback mode; repeatable",
    )


async def execute(args: argparse.Namespace, service: object) -> Any:
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
    if args.command == "read":
        selection = ProviderSelection.build(
            mode=args.provider_mode,
            primary=args.provider,
            candidates=args.candidate_provider,
        )
        return await invoke_read(service, args.source, selection)
    raise AssertionError(f"unsupported command: {args.command}")


def main(
    argv: Sequence[str] | None = None,
    *,
    service: object | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        project_root = resolve_project_root(args.project)
        active_service = service or load_application_service(project_root)
        result = asyncio.run(execute(args, active_service))
        if not args.quiet:
            projected = to_jsonable(result)
            if args.as_json:
                print(json.dumps(projected, ensure_ascii=False, sort_keys=True), file=out)
            else:
                print(_human_output(args.command, projected), file=out)
        return 0
    except (ProviderContractError, ApplicationServiceUnavailable, ValueError) as exc:
        code = getattr(exc, "code", "invalid_request")
        payload = {"error": {"code": code, "message": str(exc)}}
        if getattr(args, "as_json", False):
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=err)
        else:
            print(f"{code}: {exc}", file=err)
        return 2


def _human_output(command: str, value: Any) -> str:
    if isinstance(value, dict):
        preferred = (
            ("run_id", "status", "stage")
            if command in ("read", "show")
            else ("document_id", "status")
        )
        visible = [f"{key}={value[key]}" for key in preferred if key in value]
        if visible:
            return " ".join(visible)
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())

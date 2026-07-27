"""Generate 100k+ ArticleGraph artifact-volume acceptance evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from benchmarks.articlegraph.run_long_document_acceptance import build_real_cases


async def run(
    manifest_path: Path,
    output_path: Path,
    *,
    case_ids: frozenset[str] | None = None,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="readwelt-artifact-volume-"
    ) as temporary:
        cases = await build_real_cases(
            manifest_path,
            workspace=Path(temporary),
            case_ids=case_ids,
        )
        documents = [
            {
                "case_id": case.case_id,
                "source_format": case.source_format,
                "language": case.language,
                "normalized_characters": len(case.normalized_text),
                "artifact_volume": case.artifact_volume.to_mapping(),
            }
            for case in cases
            if case.artifact_volume is not None
        ]
    if not documents:
        raise ValueError("artifact-volume report requires at least one 100k+ case")
    payload: dict[str, Any] = {
        "schema_version": "articlegraph-artifact-volume-report.v1",
        "documents": documents,
    }
    payload["content_digest"] = _digest(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("corpus_manifest.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/articlegraph-artifact-volume-2026-07-27.json"),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="measure only the named corpus case; repeat for multiple cases",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            args.manifest,
            args.output,
            case_ids=(
                frozenset(args.case_ids)
                if isinstance(args.case_ids, list)
                else None
            ),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

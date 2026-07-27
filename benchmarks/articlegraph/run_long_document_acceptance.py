"""Run the real corpus through Xberg, ArticleGraph, and bounded StageViews."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import tracemalloc
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from benchmarks.articlegraph.artifact_volume import measure_artifact_volume
from benchmarks.articlegraph.corpus import validate_corpus_manifest
from benchmarks.articlegraph.long_document import (
    LongDocumentCase,
    merge_long_document_reports,
    run_long_document_benchmark,
    validate_required_corpus,
)
from readwelt.article_graph import ArticleGraphBuilder
from readwelt.extraction import (
    BackendCapability,
    BackendDescriptor,
    DeterministicSemanticExtractionBackend,
    ExtractionInput,
    GraphExtraction,
    SemanticExtractionBackend,
    configured_argument_semantic_backend,
)
from readwelt.runner.xberg import XbergDocumentAdapter
from readwelt.storage import ArtifactStore, ProjectLayout


class _UnavailableSemanticBackend:
    """Produce an explicit failure artifact instead of semantic locating hints."""

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id="benchmark.semantic.unavailable",
            name="long-document semantic-unavailable control",
            version="1",
            model_revision=None,
            supported_capabilities=(BackendCapability.CLAIM,),
            deterministic=True,
        )

    def extract(self, inputs: Sequence[ExtractionInput]) -> GraphExtraction:
        del inputs
        raise RuntimeError("semantic backends intentionally absent in source-first control")


async def build_real_cases(
    manifest_path: Path,
    *,
    workspace: Path,
    case_ids: frozenset[str] | None = None,
    semantic_control: Literal["unavailable", "configured"] = "unavailable",
    semantic_request_token_budget: int = 16_384,
) -> tuple[LongDocumentCase, ...]:
    """Ingest every validated corpus file through the production Xberg seam."""

    manifest_path = manifest_path.resolve()
    validation = validate_corpus_manifest(manifest_path)
    if not validation.valid:
        problems = tuple(
            (issue.case_id, issue.code, issue.detail)
            for issue in (
                *validation.issues,
                *(issue for case in validation.case_results for issue in case.issues),
            )
        )
        raise ValueError(f"ArticleGraph corpus validation failed: {problems}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list):
        raise TypeError("validated corpus cases must be a list")

    layout = ProjectLayout.resolve(workspace)
    layout.initialize()
    artifacts = ArtifactStore(layout)
    adapter = XbergDocumentAdapter(artifacts)
    semantic_backends, semantic_label = _semantic_control(
        semantic_control,
        semantic_request_token_budget,
    )
    builder = ArticleGraphBuilder(
        linguistic_backends=(),
        semantic_backends=semantic_backends,
    )
    cases: list[LongDocumentCase] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise TypeError("validated corpus case must be an object")
        case_id = _required_text(raw_case, "id")
        if case_ids is not None and case_id not in case_ids:
            continue
        source = (manifest_path.parent / _required_text(raw_case, "path")).resolve()
        snapshot = await adapter.ingest(source)
        normalized_text = (layout.root / snapshot.normalized_text_ref).read_text(
            encoding="utf-8"
        )
        artifact_volume = None
        if len(normalized_text) >= 100_000:
            tracemalloc.start()
            try:
                build = builder.build(snapshot, normalized_text)
                _, build_peak_memory = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            rebuilt = builder.build(snapshot, normalized_text)
            artifact_volume = measure_artifact_volume(
                artifacts,
                build,
                rebuilt,
                build_peak_memory_bytes=build_peak_memory,
            )
        else:
            build = builder.build(snapshot, normalized_text)
        benchmark = raw_case.get("benchmark")
        if not isinstance(benchmark, dict):
            raise TypeError(f"benchmark annotation missing for {raw_case.get('id')!r}")
        queries = benchmark.get("must_hit_queries", ())
        if not isinstance(queries, list) or not all(
            isinstance(query, str) for query in queries
        ):
            raise TypeError("must_hit_queries must be a list of strings")
        structures = raw_case.get("structures")
        tags = raw_case.get("coverage_tags")
        if not (
            isinstance(structures, list)
            and structures
            and all(isinstance(item, str) for item in structures)
        ):
            raise TypeError("corpus structures must be non-empty strings")
        if not (
            isinstance(tags, list) and all(isinstance(item, str) for item in tags)
        ):
            raise TypeError("corpus coverage_tags must be strings")
        cases.append(
            LongDocumentCase(
                case_id=case_id,
                source_format=_required_text(raw_case, "format"),
                language=_required_text(benchmark, "language"),
                structure_kind=structures[0],
                backend_configuration=(
                    "xberg==1.0.0rc38+docling-local-explicit+"
                    f"{semantic_label}"
                ),
                normalized_text=normalized_text,
                build=build,
                must_hit_queries=tuple(queries),
                corpus_tags=tuple(tags),
                artifact_volume=artifact_volume,
            )
        )
    missing = validate_required_corpus(cases) if case_ids is None else ()
    if missing:
        raise ValueError(f"real ArticleGraph corpus is incomplete: {missing}")
    if case_ids is not None:
        observed = frozenset(case.case_id for case in cases)
        if observed != case_ids:
            raise ValueError(f"unknown corpus case ids: {tuple(sorted(case_ids - observed))}")
    return tuple(cases)


async def run(
    manifest_path: Path,
    output_path: Path,
    *,
    token_budget: int,
    hard_serialized_token_budget: int,
    max_pages: int,
    case_ids: frozenset[str] | None = None,
    semantic_control: Literal["unavailable", "configured"] = "unavailable",
) -> None:
    with tempfile.TemporaryDirectory(prefix="readwelt-articlegraph-benchmark-") as temporary:
        if case_ids is not None:
            cases = await build_real_cases(
                manifest_path,
                workspace=Path(temporary),
                case_ids=case_ids,
                semantic_control=semantic_control,
                semantic_request_token_budget=hard_serialized_token_budget,
            )
            report = run_long_document_benchmark(
                cases,
                token_budget=token_budget,
                hard_serialized_token_budget=hard_serialized_token_budget,
                max_pages=max_pages,
            )
        else:
            reports = []
            for case_id in _manifest_case_ids(manifest_path):
                cases = await build_real_cases(
                    manifest_path,
                    workspace=Path(temporary),
                    case_ids=frozenset((case_id,)),
                    semantic_control=semantic_control,
                    semantic_request_token_budget=hard_serialized_token_budget,
                )
                reports.append(
                    run_long_document_benchmark(
                        cases,
                        token_budget=token_budget,
                        hard_serialized_token_budget=hard_serialized_token_budget,
                        max_pages=max_pages,
                    )
                )
            report = merge_long_document_reports(reports)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_json() + "\n", encoding="utf-8")
    output_path.with_suffix(".md").write_text(
        report.to_markdown(),
        encoding="utf-8",
    )


def _required_text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return item


def _manifest_case_ids(manifest_path: Path) -> tuple[str, ...]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise TypeError("corpus manifest cases must be a list")
    return tuple(
        _required_text(raw_case, "id")
        for raw_case in raw_cases
        if isinstance(raw_case, dict)
    )


def _semantic_control(
    mode: Literal["unavailable", "configured"],
    request_token_budget: int,
) -> tuple[
    tuple[SemanticExtractionBackend, ...],
    str,
]:
    if mode == "unavailable":
        return (
            (_UnavailableSemanticBackend(),),
            "semantic-control-unavailable",
        )
    backend = configured_argument_semantic_backend()
    if backend is None:
        raise RuntimeError(
            "configured semantic control requires READWELT_ARGUMENT_MODEL"
        )
    backend.max_request_tokens = request_token_budget
    return (
        (backend, DeterministicSemanticExtractionBackend()),
        f"semantic-control-configured:{backend.descriptor.backend_id}:{backend.model}",
    )


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
        default=Path("reports/articlegraph-long-document-acceptance-2026-07-27.json"),
    )
    parser.add_argument("--token-budget", type=int, default=512)
    parser.add_argument("--hard-serialized-token-budget", type=int, default=4096)
    parser.add_argument("--max-pages", type=int, default=10_000)
    parser.add_argument(
        "--semantic-control",
        choices=("unavailable", "configured"),
        default="unavailable",
        help=(
            "run the source-first unavailable control or an explicitly "
            "configured OpenAI-compatible semantic locating backend"
        ),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="run only the named corpus case; repeat for multiple cases",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            args.manifest,
            args.output,
            token_budget=args.token_budget,
            hard_serialized_token_budget=args.hard_serialized_token_budget,
            max_pages=args.max_pages,
            case_ids=(
                frozenset(args.case_ids)
                if isinstance(args.case_ids, list)
                else None
            ),
            semantic_control=args.semantic_control,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

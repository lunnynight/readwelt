from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.articlegraph.long_document import (
    LongDocumentCase,
    load_long_document_report_payload,
    merge_long_document_reports,
    run_long_document_benchmark,
    validate_required_corpus,
)
from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import ReadingStage
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.stage_views import StageContext, StageViewProjector
from readwelt.stage_views import serialization as stage_view_serialization
from readwelt.storage import ArtifactStore, ProjectLayout


def test_authoritative_long_document_report_is_accepted() -> None:
    report_path = (
        Path(__file__).parents[2]
        / "reports"
        / "articlegraph-long-document-acceptance-2026-07-27.json"
    )
    payload = load_long_document_report_payload(str(report_path))

    assert payload["acceptance_passed"] is True, payload["acceptance_failures"]
    assert payload["acceptance_failures"] == []
    assert payload["hard_serialized_token_budget"] == 16_384
    assert len(payload["documents"]) == 7
    assert all(document["traversal_complete"] for document in payload["documents"])


def _case(
    tmp_path: Path,
    *,
    case_id: str = "bounded",
    source_format: str = "txt",
    language: str = "en",
    structure_kind: str = "argument",
    text: str | None = None,
    queries: tuple[str, ...] = ("critical anchor", "ending anchor"),
    tags: tuple[str, ...] = (),
) -> LongDocumentCase:
    normalized = text or "\n\n".join(
        (
            "Opening claim introduces the bounded argument.",
            *(f"Evidence paragraph {index} has number {index}." for index in range(40)),
            "A critical anchor identifies the necessary counterexample.",
            "The ending anchor states the qualified conclusion.",
        )
    )
    layout = ProjectLayout.resolve(tmp_path / case_id)
    layout.initialize()
    artifacts = ArtifactStore(layout)
    snapshot = snapshot_from_text(
        source=tmp_path / f"{case_id}.{source_format}",
        text=normalized,
        source_kind="text/plain",
        artifacts=artifacts,
        adapter_finding="benchmark-test",
        language=language,
        raw_source_content=normalized.encode(),
    )
    return LongDocumentCase(
        case_id=case_id,
        source_format=source_format,
        language=language,
        structure_kind=structure_kind,
        backend_configuration="deterministic-test",
        normalized_text=normalized,
        build=ArticleGraphBuilder().build(snapshot, normalized),
        must_hit_queries=queries,
        corpus_tags=tags,
    )


def test_long_document_report_proves_bounded_complete_traversal(tmp_path: Path) -> None:
    report = run_long_document_benchmark(
        (_case(tmp_path),),
        token_budget=64,
        hard_serialized_token_budget=8_000,
    )

    document = report.documents[0]
    assert document.source_unit_coverage == 1.0
    assert document.source_range_coverage == 1.0
    assert document.source_element_coverage == 1.0
    assert document.source_root_coverage == 1.0
    assert document.structural_reference_closure
    assert document.structural_reference_failures == ()
    assert document.traversal_source_root_visited_coverage == 1.0
    assert document.traversal_source_root_presented_coverage == 1.0
    assert document.traversal_complete
    assert document.hard_budget_respected
    assert not document.cursor_loop_detected
    assert document.traversal_page_count > 1
    assert document.traversal_input_tokens > 0
    assert document.traversal_p95_latency_ms >= document.traversal_p50_latency_ms
    strategies = {item.strategy: item for item in document.strategies}
    assert strategies["lexical"].must_hit_recall == 1.0
    assert strategies["source_coverage_rescue"].must_hit_recall == 1.0
    assert strategies["source_coverage_rescue"].page_count == document.traversal_page_count
    assert not strategies["dense"].enabled
    assert strategies["dense"].reason == "dense_backend_not_enabled"
    assert not strategies["reranking"].enabled
    assert report.schema_version == "articlegraph-long-document-benchmark.v2"
    assert report.token_counter_id
    assert report.token_count_mode == "conservative_upper_bound"
    assert report.token_count_guarantee
    assert report.acceptance_passed
    assert report.acceptance_failures == ()
    assert report.content_digest.startswith("sha256:")
    markdown = report.to_markdown()
    assert "# ArticleGraph Long-document Acceptance" in markdown
    assert "| bounded | txt | 1.000 | 1.000 | 1.000 | 1.000 | True |" in markdown
    assert "dense_backend_not_enabled" in markdown


def test_image_only_source_traverses_raw_root_without_phantom_text_unit(
    tmp_path: Path,
) -> None:
    layout = ProjectLayout.resolve(tmp_path / "image-only")
    layout.initialize()
    artifacts = ArtifactStore(layout)
    snapshot = snapshot_from_text(
        source=tmp_path / "image-only.pdf",
        text="",
        source_kind="application/pdf",
        artifacts=artifacts,
        adapter_finding="xberg_text_unsupported:empty_extraction",
        raw_source_content=b"%PDF-image-only",
    )
    build = ArticleGraphBuilder().build(snapshot, "")
    case = LongDocumentCase(
        case_id="image-only",
        source_format="scanned_pdf",
        language="en",
        structure_kind="exposition",
        backend_configuration="deterministic-image-only-control",
        normalized_text="",
        build=build,
        must_hit_queries=(),
    )

    report = run_long_document_benchmark(
        (case,),
        token_budget=64,
        hard_serialized_token_budget=8_000,
    )
    document = report.documents[0]

    assert build.unitization.units == ()
    assert document.traversal_visited_coverage == 1.0
    assert document.traversal_presented_coverage == 1.0
    assert document.traversal_source_root_visited_coverage == 1.0
    assert document.traversal_source_root_presented_coverage == 1.0
    assert document.traversal_complete


def test_required_corpus_validator_does_not_accept_missing_dimensions(
    tmp_path: Path,
) -> None:
    missing = validate_required_corpus((_case(tmp_path),))

    assert "format:html" in missing
    assert "format:scanned_pdf" in missing
    assert "language:zh" in missing
    assert "structure:narrative" in missing
    assert "tag:tables" in missing
    assert "length:100k_plus" in missing


def test_sequential_report_merge_preserves_acceptance_and_policy(
    tmp_path: Path,
) -> None:
    first = run_long_document_benchmark(
        (_case(tmp_path, case_id="first"),),
        token_budget=64,
        hard_serialized_token_budget=8_000,
    )
    second = run_long_document_benchmark(
        (_case(tmp_path, case_id="second"),),
        token_budget=64,
        hard_serialized_token_budget=8_000,
    )

    merged = merge_long_document_reports((first, second))

    assert tuple(document.case_id for document in merged.documents) == (
        "first",
        "second",
    )
    assert merged.acceptance_passed
    assert merged.acceptance_failures == ()
    assert merged.content_digest not in {
        first.content_digest,
        second.content_digest,
    }


def test_unresolved_structural_reference_is_a_hard_acceptance_failure(
    tmp_path: Path,
) -> None:
    report = run_long_document_benchmark(
        (_case(tmp_path, case_id="broken-structure"),),
        token_budget=64,
        hard_serialized_token_budget=8_000,
    )
    broken = replace(
        report.documents[0],
        structural_reference_closure=False,
        structural_reference_failures=("source_element_parent_unresolved:1",),
    )

    merged = merge_long_document_reports((replace(report, documents=(broken,)),))

    assert not merged.acceptance_passed
    assert merged.acceptance_failures == (
        "broken-structure:structural_reference_closure:source_element_parent_unresolved:1",
    )


def test_lexical_must_hit_recall_is_a_hard_acceptance_gate(
    tmp_path: Path,
) -> None:
    report = run_long_document_benchmark(
        (_case(tmp_path, case_id="lexical-miss"),),
        token_budget=64,
        hard_serialized_token_budget=8_000,
    )
    document = report.documents[0]
    strategies = tuple(
        replace(
            strategy,
            must_hit_recall=0.5,
            critical_anchor_miss_rate=0.5,
        )
        if strategy.strategy == "lexical"
        else strategy
        for strategy in document.strategies
    )

    merged = merge_long_document_reports(
        (
            replace(
                report,
                documents=(replace(document, strategies=strategies),),
            ),
        )
    )

    assert not merged.acceptance_passed
    assert merged.acceptance_failures == ("lexical-miss:lexical_must_hit_gate_failed",)


@pytest.mark.parametrize(
    ("case_id", "text", "query"),
    (
        (
            "long-english-lexical",
            ("opening context " * 2_000) + "critical lexical anchor" + (" closing context" * 2_000),
            "critical lexical anchor",
        ),
        (
            "long-chinese-lexical",
            ("前置语境" * 3_000) + "关键检索锚点" + ("后续语境" * 3_000),
            "关键检索锚点",
        ),
    ),
    ids=("english", "chinese"),
)
def test_lexical_long_candidate_is_fragmented_to_fit_the_final_envelope(
    tmp_path: Path,
    case_id: str,
    text: str,
    query: str,
) -> None:
    hard_budget = 8_000
    report = run_long_document_benchmark(
        (
            _case(
                tmp_path,
                case_id=case_id,
                text=text,
                queries=(query,),
            ),
        ),
        token_budget=256,
        hard_serialized_token_budget=hard_budget,
    )

    lexical = next(
        strategy for strategy in report.documents[0].strategies if strategy.strategy == "lexical"
    )
    assert lexical.enabled
    assert lexical.must_hit_recall == 1.0
    assert lexical.critical_anchor_miss_rate == 0.0
    assert lexical.selected_unit_ids
    assert 0 < lexical.input_tokens <= hard_budget
    assert lexical.reason is None


def test_hard_budget_fitting_does_not_rehash_full_coverage_per_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Budget fitting must not repeat full-manifest hashing for every removed unit."""

    case = _case(
        tmp_path,
        case_id="budget-complexity",
        text="\n\n".join(
            f"Source paragraph {index:04d} preserves complete evidence." for index in range(320)
        ),
        queries=("Source paragraph 0000",),
    )
    original_digest = stage_view_serialization.content_digest
    digest_calls = 0
    # Logarithmic budget probes may each hash their distinct coverage state,
    # but the former one-unit-at-a-time retry loop required thousands of
    # serialization digests for this input.
    maximum_digest_calls = 512

    def counted_digest(value: object) -> str:
        nonlocal digest_calls
        digest_calls += 1
        if digest_calls > maximum_digest_calls:
            pytest.fail(
                "hard-budget fitting repeatedly rehashed the complete coverage "
                "manifest instead of reusing compact summary state"
            )
        return original_digest(value)

    monkeypatch.setattr(stage_view_serialization, "content_digest", counted_digest)
    view = StageViewProjector().project(
        case.build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="verify bounded StageView fitting complexity",
            token_budget=512,
            hard_serialized_token_budget=8_000,
            rescue_level="section",
        ),
    )

    assert view.to_mapping()["estimated_serialized_tokens"] <= 8_000
    assert digest_calls <= maximum_digest_calls

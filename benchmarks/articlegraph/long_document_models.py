"""Stable data contracts for the long-document ArticleGraph benchmark."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from benchmarks.articlegraph.artifact_volume import ArtifactVolumeMeasurement
from readwelt.article_graph import ArticleGraphBuildResult

RetrievalStrategy = Literal[
    "full_text",
    "lexical",
    "dense",
    "hybrid",
    "reranking",
    "source_coverage_rescue",
]

STRATEGIES: tuple[RetrievalStrategy, ...] = (
    "full_text",
    "lexical",
    "dense",
    "hybrid",
    "reranking",
    "source_coverage_rescue",
)


def load_long_document_report_payload(path: str) -> dict[str, Any]:
    """Load a persisted benchmark report without duplicating JSON policy in callers."""

    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise TypeError("long-document report root must be an object")
    return payload


@dataclass(frozen=True, slots=True)
class LongDocumentCase:
    """One already-ingested corpus document and its benchmark annotations."""

    case_id: str
    source_format: str
    language: str
    structure_kind: str
    backend_configuration: str
    normalized_text: str
    build: ArticleGraphBuildResult
    must_hit_queries: tuple[str, ...]
    corpus_tags: tuple[str, ...] = ()
    artifact_volume: ArtifactVolumeMeasurement | None = None

    def __post_init__(self) -> None:
        if not all(
            (
                self.case_id.strip(),
                self.source_format.strip(),
                self.language.strip(),
                self.structure_kind.strip(),
                self.backend_configuration.strip(),
            )
        ):
            raise ValueError("long-document case metadata is required")
        if not self.normalized_text and self.source_format != "scanned_pdf":
            raise ValueError("long-document case requires normalized text")
        if self.build.unitization.coverage.source_length != len(self.normalized_text):
            raise ValueError("benchmark text differs from the built Source Plane")
        if self.build.snapshot_id != self.build.unitization.snapshot_id:
            raise ValueError("benchmark build has inconsistent snapshot identity")
        if any(not query.strip() for query in self.must_hit_queries):
            raise ValueError("benchmark case requires non-empty must-hit queries")
        if not self.must_hit_queries and self.source_format != "scanned_pdf":
            raise ValueError("non-scanned benchmark cases require must-hit queries")

    @property
    def length_class(self) -> str:
        length = len(self.normalized_text)
        if length >= 100_000:
            return "100k_plus"
        if length >= 20_000:
            return "20k_to_100k"
        return "under_20k"


@dataclass(frozen=True, slots=True)
class StrategyMeasurement:
    strategy: RetrievalStrategy
    enabled: bool
    must_hit_recall: float
    critical_anchor_miss_rate: float
    input_tokens: int
    full_text_fallback_rate: float
    page_count: int
    latency_ms: float
    peak_memory_bytes: int
    selected_unit_ids: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentMeasurement:
    case_id: str
    source_format: str
    language: str
    length_class: str
    structure_kind: str
    backend_configuration: str
    source_unit_coverage: float
    source_range_coverage: float
    source_element_coverage: float
    source_root_coverage: float
    structural_reference_closure: bool
    structural_reference_failures: tuple[str, ...]
    traversal_visited_coverage: float
    traversal_presented_coverage: float
    traversal_range_visited_coverage: float
    traversal_range_presented_coverage: float
    traversal_element_visited_coverage: float
    traversal_element_presented_coverage: float
    traversal_source_root_visited_coverage: float
    traversal_source_root_presented_coverage: float
    traversal_complete: bool
    hard_budget_respected: bool
    cursor_loop_detected: bool
    traversal_page_count: int
    traversal_input_tokens: int
    traversal_p50_latency_ms: float
    traversal_p95_latency_ms: float
    peak_memory_bytes: int
    backend_failures: tuple[str, ...]
    unresolved_projections: int
    strategies: tuple[StrategyMeasurement, ...]


@dataclass(frozen=True, slots=True)
class LongDocumentBenchmarkReport:
    schema_version: str
    token_budget: int
    hard_serialized_token_budget: int
    token_counter_id: str
    token_count_mode: str
    token_count_guarantee: str
    documents: tuple[DocumentMeasurement, ...]
    corpus_tags: tuple[str, ...]
    acceptance_passed: bool
    acceptance_failures: tuple[str, ...]
    content_digest: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "token_budget": self.token_budget,
            "hard_serialized_token_budget": self.hard_serialized_token_budget,
            "token_counter_id": self.token_counter_id,
            "token_count_mode": self.token_count_mode,
            "token_count_guarantee": self.token_count_guarantee,
            "documents": [asdict(document) for document in self.documents],
            "corpus_tags": list(self.corpus_tags),
            "acceptance_passed": self.acceptance_passed,
            "acceptance_failures": list(self.acceptance_failures),
            "content_digest": self.content_digest,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_mapping(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    def to_markdown(self) -> str:
        lines = [
            "# ArticleGraph Long-document Acceptance",
            "",
            f"- Acceptance: {'PASS' if self.acceptance_passed else 'FAIL'}",
            f"- Token budget: {self.token_budget}",
            f"- Hard serialized budget: {self.hard_serialized_token_budget}",
            f"- Counter: `{self.token_counter_id}` ({self.token_count_mode})",
            f"- Report digest: `{self.content_digest}`",
            "",
            "The input-token values are measured with the declared counter. "
            "This run uses a conservative upper bound, not a provider tokenizer.",
            "",
            "## Source reachability and traversal",
            "",
            "| Case | Format | Units | Ranges | Elements | Source root | "
            "Structure closed | Complete | Pages | Input tokens | p50 ms | "
            "p95 ms | Peak bytes | "
            "Backend failures | Unresolved |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for document in self.documents:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _markdown_cell(document.case_id),
                        document.source_format,
                        f"{document.source_unit_coverage:.3f}",
                        f"{document.source_range_coverage:.3f}",
                        f"{document.source_element_coverage:.3f}",
                        f"{document.source_root_coverage:.3f}",
                        str(document.structural_reference_closure),
                        str(document.traversal_complete),
                        str(document.traversal_page_count),
                        str(document.traversal_input_tokens),
                        f"{document.traversal_p50_latency_ms:.3f}",
                        f"{document.traversal_p95_latency_ms:.3f}",
                        str(document.peak_memory_bytes),
                        str(len(document.backend_failures)),
                        str(document.unresolved_projections),
                    )
                )
                + " |"
            )
        lines.extend(
            (
                "",
                "## Equal-budget retrieval controls",
                "",
                "| Case | Strategy | Enabled | Recall | Critical miss | "
                "Input tokens | Pages | Latency ms | Peak bytes | Fallback | Reason |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            )
        )
        for document in self.documents:
            for strategy in document.strategies:
                lines.append(
                    "| "
                    + " | ".join(
                        (
                            _markdown_cell(document.case_id),
                            strategy.strategy,
                            str(strategy.enabled),
                            f"{strategy.must_hit_recall:.3f}",
                            f"{strategy.critical_anchor_miss_rate:.3f}",
                            str(strategy.input_tokens),
                            str(strategy.page_count),
                            f"{strategy.latency_ms:.3f}",
                            str(strategy.peak_memory_bytes),
                            f"{strategy.full_text_fallback_rate:.3f}",
                            _markdown_cell(strategy.reason or ""),
                        )
                    )
                    + " |"
                )
        if self.acceptance_failures:
            lines.extend(("", "## Acceptance failures", ""))
            lines.extend(f"- `{failure}`" for failure in self.acceptance_failures)
        return "\n".join(lines) + "\n"


CandidateProvider = Callable[[LongDocumentCase, str], Sequence[str]]


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")

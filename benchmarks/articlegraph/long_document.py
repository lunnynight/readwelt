"""Stable public facade for long-document ArticleGraph acceptance.

The implementation is split by responsibility so benchmark data contracts,
measurements, and acceptance policy can evolve without forming another god file.
"""

from benchmarks.articlegraph.long_document_acceptance import validate_required_corpus
from benchmarks.articlegraph.long_document_core import (
    merge_long_document_reports,
    run_long_document_benchmark,
)
from benchmarks.articlegraph.long_document_models import (
    CandidateProvider,
    DocumentMeasurement,
    LongDocumentBenchmarkReport,
    LongDocumentCase,
    RetrievalStrategy,
    StrategyMeasurement,
    load_long_document_report_payload,
)

__all__ = [
    "CandidateProvider",
    "DocumentMeasurement",
    "LongDocumentBenchmarkReport",
    "LongDocumentCase",
    "RetrievalStrategy",
    "StrategyMeasurement",
    "load_long_document_report_payload",
    "merge_long_document_reports",
    "run_long_document_benchmark",
    "validate_required_corpus",
]

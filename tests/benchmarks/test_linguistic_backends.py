from __future__ import annotations

from benchmarks.articlegraph.linguistic_backends import benchmark_linguistic_backend
from readwelt.extraction import DeterministicLinguisticBackend, ExtractionInput
from readwelt.extraction.models import SourceReference


def test_linguistic_benchmark_reports_grounding_and_adoption_gaps() -> None:
    source_ref = SourceReference(
        unit_id="unit-1",
        reference_id="ref-1",
        start_offset=0,
        end_offset=5,
        exact_text="第一句。",
    )
    result = benchmark_linguistic_backend(
        DeterministicLinguisticBackend(),
        (
            ExtractionInput(
                document_id="document-1",
                snapshot_id="snapshot-1",
                unit_id="unit-1",
                text="第一句。",
                source_references=(source_ref,),
            ),
        ),
        must_hit_unit_ids=("unit-1",),
    )

    assert result.input_unit_count == 1
    assert result.must_hit_recall == 1.0
    assert result.grounding_reference_count > 0
    assert result.offset_recovery_rate == 1.0
    assert not result.gate_passed
    assert "model_revision_missing" in result.gate_failures
    assert result.content_digest.startswith("sha256:")


def test_linguistic_benchmark_exposes_missing_must_hit_coverage() -> None:
    result = benchmark_linguistic_backend(
        DeterministicLinguisticBackend(),
        (
            ExtractionInput(
                document_id="document-1",
                snapshot_id="snapshot-1",
                unit_id="unit-1",
                text="第一句。",
            ),
        ),
        must_hit_unit_ids=("missing-unit",),
    )

    assert result.must_hit_recall == 0.0
    assert "must_hit_recall_below_threshold" in result.gate_failures

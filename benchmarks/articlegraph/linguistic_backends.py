"""Comparable, source-grounded benchmark harness for linguistic backends."""

from __future__ import annotations

import hashlib
import json
import time
import tracemalloc
from dataclasses import asdict, dataclass

from readwelt.extraction import ExtractionInput, LinguisticBackend
from readwelt.extraction.models import GraphExtraction, SourceReference

LINGUISTIC_BENCHMARK_SCHEMA = "linguistic-backend-benchmark.v1"


@dataclass(frozen=True, slots=True)
class LinguisticBenchmarkResult:
    schema_version: str
    backend_id: str
    backend_version: str
    model_revision: str | None
    code_license: str | None
    input_unit_count: int
    input_characters: int
    must_hit_unit_ids: tuple[str, ...]
    covered_must_hit_unit_ids: tuple[str, ...]
    must_hit_recall: float
    grounding_reference_count: int
    recovered_reference_count: int
    offset_recovery_rate: float | None
    latency_ms: float
    throughput_characters_per_second: float
    peak_memory_bytes: int
    extraction_digest: str
    gate_passed: bool
    gate_failures: tuple[str, ...]
    content_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != LINGUISTIC_BENCHMARK_SCHEMA:
            raise ValueError(f"unsupported linguistic benchmark schema: {self.schema_version}")
        if not 0.0 <= self.must_hit_recall <= 1.0:
            raise ValueError("must_hit_recall must be between zero and one")
        if self.offset_recovery_rate is not None and not (
            0.0 <= self.offset_recovery_rate <= 1.0
        ):
            raise ValueError("offset_recovery_rate must be between zero and one")
        expected = _digest(self)
        if self.content_digest and self.content_digest != expected:
            raise ValueError("linguistic benchmark digest mismatch")
        object.__setattr__(self, "content_digest", expected)


def benchmark_linguistic_backend(
    backend: LinguisticBackend,
    inputs: tuple[ExtractionInput, ...],
    *,
    must_hit_unit_ids: tuple[str, ...] = (),
    minimum_must_hit_recall: float = 1.0,
    minimum_offset_recovery: float = 1.0,
) -> LinguisticBenchmarkResult:
    """Measure one backend without changing the ArticleGraph extraction contract."""

    if not 0.0 <= minimum_must_hit_recall <= 1.0:
        raise ValueError("minimum_must_hit_recall must be between zero and one")
    if not 0.0 <= minimum_offset_recovery <= 1.0:
        raise ValueError("minimum_offset_recovery must be between zero and one")
    descriptor = backend.descriptor
    started = time.perf_counter()
    tracemalloc.start()
    try:
        extraction = backend.extract(inputs)
        _, peak_memory = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    elapsed = max(time.perf_counter() - started, 1e-9)

    covered_units = {
        unit_id
        for outcome in extraction.outcomes
        for unit_id in outcome.covered_unit_ids
    }
    required = tuple(dict.fromkeys(must_hit_unit_ids))
    covered_required = tuple(unit_id for unit_id in required if unit_id in covered_units)
    recall = len(covered_required) / len(required) if required else 1.0
    grounding_refs = _grounding_references(extraction)
    recovered = tuple(
        reference
        for reference in grounding_refs
        if _reference_resolves(reference, inputs)
    )
    offset_recovery = (
        len(recovered) / len(grounding_refs) if grounding_refs else None
    )
    failures: list[str] = []
    if descriptor.license_name is None:
        failures.append("code_license_missing")
    if descriptor.model_revision is None:
        failures.append("model_revision_missing")
    if recall < minimum_must_hit_recall:
        failures.append("must_hit_recall_below_threshold")
    if (
        offset_recovery is not None
        and offset_recovery < minimum_offset_recovery
    ):
        failures.append("offset_recovery_below_threshold")
    input_characters = sum(len(item.text) for item in inputs)
    return LinguisticBenchmarkResult(
        schema_version=LINGUISTIC_BENCHMARK_SCHEMA,
        backend_id=descriptor.backend_id,
        backend_version=descriptor.version,
        model_revision=descriptor.model_revision,
        code_license=descriptor.license_name,
        input_unit_count=len(inputs),
        input_characters=input_characters,
        must_hit_unit_ids=required,
        covered_must_hit_unit_ids=covered_required,
        must_hit_recall=recall,
        grounding_reference_count=len(grounding_refs),
        recovered_reference_count=len(recovered),
        offset_recovery_rate=offset_recovery,
        latency_ms=elapsed * 1000,
        throughput_characters_per_second=input_characters / elapsed,
        peak_memory_bytes=peak_memory,
        extraction_digest=extraction.content_digest,
        gate_passed=not failures,
        gate_failures=tuple(failures),
    )


def _grounding_references(extraction: GraphExtraction) -> tuple[SourceReference, ...]:
    node_references = [
        reference
        for candidate in extraction.candidate_nodes
        for reference in candidate.grounding.source_references
    ]
    edge_references = [
        reference
        for candidate in extraction.candidate_edges
        for reference in candidate.grounding.source_references
    ]
    references = [*node_references, *edge_references]
    return tuple(
        {
            (
                reference.unit_id,
                reference.reference_id,
                reference.start_offset,
                reference.end_offset,
                reference.exact_text,
            ): reference
            for reference in references
        }.values()
    )


def _reference_resolves(
    reference: SourceReference,
    inputs: tuple[ExtractionInput, ...],
) -> bool:
    source_refs = tuple(
        item
        for input_item in inputs
        if input_item.unit_id == reference.unit_id
        for item in input_item.source_references
    )
    input_item = next(
        (item for item in inputs if item.unit_id == reference.unit_id),
        None,
    )
    if input_item is None:
        return False
    for source_ref in source_refs:
        if (
            reference.reference_id is not None
            and source_ref.reference_id != reference.reference_id
        ):
            continue
        if (
            reference.start_offset is None
            or reference.end_offset is None
            or source_ref.start_offset is None
            or source_ref.end_offset is None
        ):
            if reference.exact_text == source_ref.exact_text:
                return True
            continue
        if not (
            source_ref.start_offset
            <= reference.start_offset
            <= reference.end_offset
            <= source_ref.end_offset
        ):
            continue
        relative_start = reference.start_offset - source_ref.start_offset
        relative_end = reference.end_offset - source_ref.start_offset
        if input_item.text[relative_start:relative_end] == reference.exact_text:
            return True
    return False


def _digest(value: LinguisticBenchmarkResult) -> str:
    content = asdict(value)
    content["content_digest"] = ""
    payload = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"

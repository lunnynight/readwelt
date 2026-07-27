"""Artifact volume, CAS reuse, and bounded-read measurements."""

from __future__ import annotations

import json
import tracemalloc
from dataclasses import asdict, dataclass

from readwelt.article_graph import ArticleGraphBuildArtifact, ArticleGraphBuildResult
from readwelt.domain import ArtifactRef
from readwelt.storage import ArtifactStore
from readwelt.storage.serialization import canonical_json_bytes

ARTIFACT_VOLUME_SCHEMA_VERSION = "articlegraph-artifact-volume.v1"
_MEASURED_ROLES = frozenset(
    {"source_plane", "graph", "source_index", "provenance_ledger", "aggregate"}
)


@dataclass(frozen=True, slots=True)
class ArtifactByteMeasurement:
    role: str
    artifact_type: str
    schema_version: str
    content_digest: str
    bytes: int
    bounded_read_offset: int
    bounded_read_bytes: int
    bounded_read_peak_memory_bytes: int
    stream_chunk_bytes: int
    stream_max_chunk_bytes: int
    stream_total_bytes: int
    stream_digest_verified: bool


@dataclass(frozen=True, slots=True)
class ArtifactVolumeMeasurement:
    schema_version: str
    artifacts: tuple[ArtifactByteMeasurement, ...]
    child_artifact_bytes: int
    aggregate_artifact_bytes: int
    naive_embedded_bytes: int
    naive_stored_bytes: int
    cas_unique_bytes: int
    deduplication_ratio: float
    aggregate_reference_only: bool
    rebuild_build_digest_equal: bool
    rebuild_reused_artifact_count: int
    rebuild_artifact_count: int
    rebuild_new_unique_bytes: int
    cas_bytes_before: int
    cas_bytes_after_first_build: int
    cas_bytes_after_rebuild: int
    build_peak_memory_bytes: int
    bounded_page_bytes: int

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)


def measure_artifact_volume(
    artifacts: ArtifactStore,
    build: ArticleGraphBuildResult,
    rebuilt: ArticleGraphBuildResult,
    *,
    build_peak_memory_bytes: int,
    bounded_page_bytes: int = 4_096,
) -> ArtifactVolumeMeasurement:
    """Persist the same build twice and measure immutable CAS reuse."""

    if bounded_page_bytes < 1:
        raise ValueError("bounded artifact page size must be positive")
    cas_bytes_before = _cas_bytes(artifacts)
    first = _persist_build(artifacts, build)
    cas_bytes_after_first = _cas_bytes(artifacts)
    second = _persist_build(artifacts, rebuilt)
    cas_bytes_after_rebuild = _cas_bytes(artifacts)

    first_by_role = dict(first)
    first_digests = {reference.content_digest for _, reference in first}
    rebuild_new_unique_bytes = sum(
        reference.size
        for _, reference in second
        if reference.content_digest not in first_digests
    )
    reused = sum(
        first_by_role[role].content_digest == reference.content_digest
        for role, reference in second
        if role in first_by_role
    )

    measured = tuple(
        _measure_reference(
            artifacts,
            role,
            reference,
            bounded_page_bytes=bounded_page_bytes,
        )
        for role, reference in first
        if role in _MEASURED_ROLES
    )
    aggregate = first_by_role["aggregate"]
    child_references = tuple(
        reference for role, reference in first if role != "aggregate"
    )
    child_bytes = sum(reference.size for reference in child_references)
    naive_embedded_bytes = len(canonical_json_bytes(build))
    naive_stored_bytes = child_bytes + naive_embedded_bytes
    unique_by_digest = {
        reference.content_digest: reference for _, reference in first
    }
    cas_unique_bytes = sum(reference.size for reference in unique_by_digest.values())
    aggregate_payload = json.loads(artifacts.read_text(aggregate))
    reference_only = (
        isinstance(aggregate_payload, dict)
        and isinstance(aggregate_payload.get("references"), list)
        and not {"graph", "unitization", "extractions"}.intersection(aggregate_payload)
    )
    return ArtifactVolumeMeasurement(
        schema_version=ARTIFACT_VOLUME_SCHEMA_VERSION,
        artifacts=measured,
        child_artifact_bytes=child_bytes,
        aggregate_artifact_bytes=aggregate.size,
        naive_embedded_bytes=naive_embedded_bytes,
        naive_stored_bytes=naive_stored_bytes,
        cas_unique_bytes=cas_unique_bytes,
        deduplication_ratio=(
            naive_stored_bytes / cas_unique_bytes if cas_unique_bytes else 1.0
        ),
        aggregate_reference_only=reference_only,
        rebuild_build_digest_equal=build.content_digest == rebuilt.content_digest,
        rebuild_reused_artifact_count=reused,
        rebuild_artifact_count=len(second),
        rebuild_new_unique_bytes=rebuild_new_unique_bytes,
        cas_bytes_before=cas_bytes_before,
        cas_bytes_after_first_build=cas_bytes_after_first,
        cas_bytes_after_rebuild=cas_bytes_after_rebuild,
        build_peak_memory_bytes=build_peak_memory_bytes,
        bounded_page_bytes=bounded_page_bytes,
    )


def _persist_build(
    artifacts: ArtifactStore,
    build: ArticleGraphBuildResult,
) -> tuple[tuple[str, ArtifactRef], ...]:
    components = (
        (
            "source_plane",
            artifacts.put_json(
                build.unitization,
                artifact_type="anchored_text_unitization",
                schema_version=build.unitization.schema_version,
            ),
        ),
        *(
            (
                f"extraction:{extraction.backend.backend_id}",
                artifacts.put_json(
                    extraction,
                    artifact_type="graph_extraction",
                    schema_version=extraction.schema_version,
                ),
            )
            for extraction in build.extractions
        ),
        (
            "merge_report",
            artifacts.put_json(
                build.merge_report,
                artifact_type="article_graph_merge_report",
                schema_version=build.merge_report.schema_version,
            ),
        ),
        (
            "provenance_ledger",
            artifacts.put_json(
                build.provenance_ledger,
                artifact_type="article_graph_provenance_ledger",
                schema_version=build.provenance_ledger.schema_version,
            ),
        ),
        (
            "source_index",
            artifacts.put_json(
                build.source_index,
                artifact_type="article_graph_source_index",
                schema_version=build.source_index.schema_version,
            ),
        ),
        (
            "graph",
            artifacts.put_json(
                build.graph,
                artifact_type="article_graph",
                schema_version=build.graph.schema_version,
            ),
        ),
    )
    aggregate = ArticleGraphBuildArtifact.from_build(
        build,
        tuple(reference for _, reference in components),
    )
    return (
        *components,
        (
            "aggregate",
            artifacts.put_json(
                aggregate,
                artifact_type="article_graph_build",
                schema_version=aggregate.schema_version,
            ),
        ),
    )


def _measure_reference(
    artifacts: ArtifactStore,
    role: str,
    reference: ArtifactRef,
    *,
    bounded_page_bytes: int,
) -> ArtifactByteMeasurement:
    offset = min(reference.size // 2, bounded_page_bytes)
    tracemalloc.start()
    try:
        page = artifacts.read_range(
            reference,
            offset=offset,
            length=bounded_page_bytes,
        )
        _, bounded_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    max_chunk = 0
    streamed = 0
    for chunk in artifacts.iter_bytes(reference, chunk_size=bounded_page_bytes):
        max_chunk = max(max_chunk, len(chunk))
        streamed += len(chunk)
    return ArtifactByteMeasurement(
        role=role,
        artifact_type=reference.artifact_type,
        schema_version=reference.schema_version,
        content_digest=reference.content_digest,
        bytes=reference.size,
        bounded_read_offset=offset,
        bounded_read_bytes=len(page),
        bounded_read_peak_memory_bytes=bounded_peak,
        stream_chunk_bytes=bounded_page_bytes,
        stream_max_chunk_bytes=max_chunk,
        stream_total_bytes=streamed,
        stream_digest_verified=streamed == reference.size,
    )


def _cas_bytes(artifacts: ArtifactStore) -> int:
    return artifacts.total_stored_bytes()

from __future__ import annotations

from pathlib import Path

from benchmarks.articlegraph.artifact_volume import measure_artifact_volume
from readwelt.article_graph import ArticleGraphBuilder
from readwelt.extraction import DeterministicSemanticExtractionBackend
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


def test_100k_build_reports_reference_dedup_and_bounded_reads(tmp_path: Path) -> None:
    text = "可追溯的长文定位记录。" * 10_500
    assert len(text) >= 100_000
    layout = ProjectLayout.resolve(tmp_path / "project")
    layout.initialize()
    artifacts = ArtifactStore(layout)
    snapshot = snapshot_from_text(
        source=tmp_path / "long.txt",
        text=text,
        source_kind="text/plain",
        artifacts=artifacts,
        adapter_finding="artifact-volume-test",
        language="zh",
    )
    builder = ArticleGraphBuilder(
        linguistic_backends=(),
        semantic_backends=(DeterministicSemanticExtractionBackend(),),
    )

    build = builder.build(snapshot, text)
    rebuilt = builder.build(snapshot, text)
    measurement = measure_artifact_volume(
        artifacts,
        build,
        rebuilt,
        build_peak_memory_bytes=123_456,
        bounded_page_bytes=4_096,
    )

    by_role = {item.role: item for item in measurement.artifacts}
    assert set(by_role) == {
        "source_plane",
        "graph",
        "source_index",
        "provenance_ledger",
        "aggregate",
    }
    assert by_role["source_plane"].bytes > 100_000
    assert all(item.bounded_read_bytes <= 4_096 for item in by_role.values())
    assert all(item.stream_max_chunk_bytes <= 4_096 for item in by_role.values())
    assert all(item.stream_total_bytes == item.bytes for item in by_role.values())
    assert all(item.stream_digest_verified for item in by_role.values())
    assert measurement.aggregate_reference_only
    assert measurement.aggregate_artifact_bytes < measurement.naive_embedded_bytes
    assert measurement.naive_stored_bytes > measurement.cas_unique_bytes
    assert measurement.deduplication_ratio > 1.0
    assert measurement.rebuild_build_digest_equal
    assert measurement.rebuild_reused_artifact_count == measurement.rebuild_artifact_count
    assert measurement.rebuild_new_unique_bytes == 0
    assert measurement.cas_bytes_after_rebuild == measurement.cas_bytes_after_first_build
    assert measurement.build_peak_memory_bytes == 123_456

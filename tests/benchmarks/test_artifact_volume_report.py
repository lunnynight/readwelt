from __future__ import annotations

import json
from pathlib import Path


def test_real_100k_artifact_volume_report_proves_cas_reuse() -> None:
    payload = json.loads(
        Path("reports/articlegraph-artifact-volume-2026-07-27.json").read_text(encoding="utf-8")
    )
    document = payload["documents"][0]
    volume = document["artifact_volume"]
    artifacts = {item["role"]: item for item in volume["artifacts"]}

    assert document["normalized_characters"] >= 100_000
    assert set(artifacts) == {
        "source_plane",
        "graph",
        "source_index",
        "provenance_ledger",
        "aggregate",
    }
    assert volume["aggregate_reference_only"]
    assert volume["aggregate_artifact_bytes"] < volume["naive_embedded_bytes"]
    assert volume["deduplication_ratio"] > 1.0
    assert volume["rebuild_build_digest_equal"]
    assert volume["rebuild_reused_artifact_count"] == volume["rebuild_artifact_count"]
    assert volume["rebuild_new_unique_bytes"] == 0
    assert volume["cas_bytes_after_rebuild"] == volume["cas_bytes_after_first_build"]
    assert volume["build_peak_memory_bytes"] > 0
    assert all(
        item["bounded_read_bytes"] <= volume["bounded_page_bytes"]
        and item["stream_max_chunk_bytes"] <= volume["bounded_page_bytes"]
        and item["stream_total_bytes"] == item["bytes"]
        and item["stream_digest_verified"]
        for item in artifacts.values()
    )

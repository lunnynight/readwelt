from __future__ import annotations

from pathlib import Path

from readwelt.article_ir import unitize_snapshot
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


def _artifacts(tmp_path: Path) -> ArtifactStore:
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    return ArtifactStore(layout)


def test_unitization_addresses_every_normalized_range_including_gaps(
    tmp_path: Path,
) -> None:
    text = "甲\n\n乙"
    snapshot = snapshot_from_text(
        source=tmp_path / "source.txt",
        text=text,
        source_kind="text/plain",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
    )

    result = unitize_snapshot(snapshot, text)

    assert result.source_ranges
    assert result.source_ranges[0].start_offset == 0
    assert result.source_ranges[-1].end_offset == len(text)
    assert all(
        left.end_offset == right.start_offset
        for left, right in zip(
            result.source_ranges,
            result.source_ranges[1:],
            strict=False,
        )
    )
    gap = result.range_at(1)
    assert gap is not None
    assert gap.kind == "gap"
    assert (gap.start_offset, gap.end_offset) == (1, 3)
    assert result.coverage.has_complete_text_coverage
    reconstructed = "".join(
        text[item.start_offset : item.end_offset] for item in result.source_ranges
    )
    assert reconstructed == text


def test_source_ranges_remain_complete_without_semantic_candidates(
    tmp_path: Path,
) -> None:
    text = "只有原文，也必须能够完整定位。"
    snapshot = snapshot_from_text(
        source=tmp_path / "source.txt",
        text=text,
        source_kind="text/plain",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
    )

    result = unitize_snapshot(snapshot, text)

    assert result.coverage.has_complete_text_coverage
    assert tuple(item.kind for item in result.source_ranges) == ("unit",)
    assert result.range_at(len(text) - 1) is not None

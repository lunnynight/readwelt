from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from readwelt.runner.document import DocumentRunner
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


class _SequenceAdapter:
    def __init__(self, snapshots: tuple[Any, ...]) -> None:
        self._snapshots = iter(snapshots)

    async def ingest(self, source: Path) -> Any:
        del source
        return next(self._snapshots)


def test_parser_policy_upgrade_links_new_snapshot_to_previous_snapshot(
    tmp_path: Path,
) -> None:
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    artifacts = ArtifactStore(layout)
    first = snapshot_from_text(
        source=tmp_path / "book.epub",
        text="相同正文",
        source_kind="application/epub+zip",
        artifacts=artifacts,
        adapter_finding="test",
        snapshot_policy_version="parser-v1",
    )
    second = snapshot_from_text(
        source=tmp_path / "book.epub",
        text="相同正文",
        source_kind="application/epub+zip",
        artifacts=artifacts,
        adapter_finding="test",
        snapshot_policy_version="parser-v2",
    )
    runner = DocumentRunner(layout, adapter=_SequenceAdapter((first, second)))

    persisted_first = asyncio.run(runner.ingest(tmp_path / "book.epub"))
    persisted_second = asyncio.run(runner.ingest(tmp_path / "book.epub"))

    assert persisted_first.document_id == persisted_second.document_id
    assert persisted_first.snapshot_id != persisted_second.snapshot_id
    assert persisted_second.parent_snapshot_id == persisted_first.snapshot_id

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from readwelt.batch import LocalBatchPipeline
from readwelt.storage import ProjectLayout


@dataclass
class Snapshot:
    document_id: str
    snapshot_id: str


class FakeApplication:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0
        self.imported: list[str] = []

    async def import_document_async(self, source: str | Path) -> Snapshot:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        name = Path(source).name
        self.imported.append(name)
        if name == "bad.txt":
            raise ValueError("broken")
        return Snapshot(f"document-{name}", f"snapshot-{name}")

    async def prepare_async(self, document_id: str) -> dict[str, str]:
        await asyncio.sleep(0)
        return {"document_id": document_id}


def test_batch_is_bounded_deduplicated_and_failure_isolated(tmp_path) -> None:
    layout = ProjectLayout.resolve(".readwelt", base_directory=tmp_path)
    layout.initialize()
    application = FakeApplication()
    sources = [tmp_path / f"{index}.txt" for index in range(2_000)]
    sources.extend((tmp_path / "bad.txt", tmp_path / "0.txt"))
    pipeline = LocalBatchPipeline(application, layout, concurrency=7)

    result = asyncio.run(pipeline.run(sources))

    assert result.completed == 2_001
    assert result.failed == 1
    assert application.maximum <= 7
    assert application.imported.count("0.txt") == 1
    assert [item.index for item in result.items] == list(range(2_002))


def test_batch_resume_skips_completed_items(tmp_path) -> None:
    layout = ProjectLayout.resolve(".readwelt", base_directory=tmp_path)
    layout.initialize()
    sources = [tmp_path / "a.txt", tmp_path / "b.txt"]
    first_application = FakeApplication()
    first = asyncio.run(LocalBatchPipeline(first_application, layout, concurrency=2).run(sources))
    second_application = FakeApplication()

    second = asyncio.run(LocalBatchPipeline(second_application, layout, concurrency=2).run(sources))

    assert second == first
    assert second_application.imported == []

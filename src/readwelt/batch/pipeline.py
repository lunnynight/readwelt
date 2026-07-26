"""Database-free batch import and semantic preparation."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from readwelt.domain import stable_id
from readwelt.storage import ManifestStore, ProjectLayout


class BatchApplication(Protocol):
    async def import_document_async(self, source: str | Path) -> Any: ...

    async def prepare_async(self, document_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class BatchItem:
    index: int
    source: str
    status: str = "pending"
    document_id: str | None = None
    snapshot_id: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BatchResult:
    batch_id: str
    items: tuple[BatchItem, ...]

    @property
    def completed(self) -> int:
        return sum(item.status == "completed" for item in self.items)

    @property
    def failed(self) -> int:
        return sum(item.status == "failed" for item in self.items)


class LocalBatchPipeline:
    """Use a bounded queue and atomic manifest instead of a workflow database."""

    def __init__(
        self,
        application: BatchApplication,
        layout: ProjectLayout,
        *,
        concurrency: int = 8,
        checkpoint_interval: int = 25,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least one")
        if checkpoint_interval < 1:
            raise ValueError("checkpoint_interval must be at least one")
        self._application = application
        self._layout = layout
        self._concurrency = concurrency
        self._checkpoint_interval = checkpoint_interval
        self._manifests = ManifestStore()

    async def run(
        self,
        sources: Sequence[str | Path],
        *,
        prepare: bool = True,
    ) -> BatchResult:
        canonical = tuple(str(Path(source).resolve()) for source in sources)
        batch_id = stable_id("batch", "prepare" if prepare else "import", *canonical)
        path = self._layout.root / "batches" / batch_id / "manifest.json"
        items = self._load_or_create(path, batch_id, canonical)
        lock = asyncio.Lock()
        completed_since_checkpoint = 0
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self._concurrency * 2)
        source_to_indexes: dict[str, list[int]] = {}
        for index, source in enumerate(canonical):
            source_to_indexes.setdefault(source, []).append(index)

        async def persist() -> None:
            self._manifests.write(path, BatchResult(batch_id, tuple(items)))

        async def producer() -> None:
            for source, indexes in source_to_indexes.items():
                if all(items[index].status == "completed" for index in indexes):
                    continue
                await queue.put(source)
            for _ in range(self._concurrency):
                await queue.put(None)

        async def worker() -> None:
            nonlocal completed_since_checkpoint
            while True:
                source = await queue.get()
                try:
                    if source is None:
                        return
                    indexes = source_to_indexes[source]
                    async with lock:
                        for index in indexes:
                            items[index] = replace(
                                items[index],
                                status="running",
                                error=None,
                            )
                    outcome = await self._process(source, prepare=prepare)
                    async with lock:
                        for index in indexes:
                            items[index] = replace(items[index], **outcome)
                        completed_since_checkpoint += 1
                        if completed_since_checkpoint >= self._checkpoint_interval:
                            await persist()
                            completed_since_checkpoint = 0
                finally:
                    queue.task_done()

        await persist()
        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(self._concurrency):
                group.create_task(worker())
        await persist()
        return BatchResult(batch_id=batch_id, items=tuple(items))

    async def _process(self, source: str, *, prepare: bool) -> dict[str, Any]:
        try:
            snapshot = await self._application.import_document_async(source)
            document_id = _field(snapshot, "document_id")
            snapshot_id = _field(snapshot, "snapshot_id")
            if prepare:
                await self._application.prepare_async(document_id)
            return {
                "status": "completed",
                "document_id": document_id,
                "snapshot_id": snapshot_id,
                "error": None,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

    def _load_or_create(
        self,
        path: Path,
        batch_id: str,
        sources: tuple[str, ...],
    ) -> list[BatchItem]:
        if not path.exists():
            return [BatchItem(index=index, source=source) for index, source in enumerate(sources)]
        value = self._manifests.read(path)
        if value.get("batch_id") != batch_id:
            raise ValueError("batch manifest id mismatch")
        raw_items = value.get("items")
        if not isinstance(raw_items, list) or len(raw_items) != len(sources):
            raise ValueError("batch manifest inputs do not match")
        decoded = [_decode_item(item) for item in raw_items]
        if tuple(item.source for item in decoded) != sources:
            raise ValueError("batch manifest source order does not match")
        return [
            replace(item, status="pending") if item.status == "running" else item
            for item in decoded
        ]


def _field(value: Any, name: str) -> str:
    raw = value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"application result has no {name}")
    return raw


def _decode_item(value: Any) -> BatchItem:
    if not isinstance(value, Mapping):
        raise ValueError("batch item must be an object")
    return BatchItem(
        index=int(value["index"]),
        source=str(value["source"]),
        status=str(value["status"]),
        document_id=(str(value["document_id"]) if value.get("document_id") is not None else None),
        snapshot_id=(str(value["snapshot_id"]) if value.get("snapshot_id") is not None else None),
        error=str(value["error"]) if value.get("error") is not None else None,
    )

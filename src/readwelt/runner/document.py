"""Recoverable single-document runtime."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from readwelt.domain import (
    ArtifactRef,
    ArtifactStatus,
    EpistemicStatus,
    ExecutionStatus,
    ModelStatus,
    PublicationStatus,
    ReadingRun,
    SourceDocumentSnapshot,
)
from readwelt.runner.adapters import DocumentAdapter
from readwelt.runner.text import PlainTextAdapter
from readwelt.runner.xberg import XbergDocumentAdapter
from readwelt.storage import ArtifactStore, ManifestStore, ProjectLayout


class DocumentRunner:
    """Ingest documents and decode persisted document/run manifests."""

    def __init__(
        self,
        layout: ProjectLayout,
        *,
        adapter: DocumentAdapter | None = None,
    ) -> None:
        self._layout = layout
        self._artifacts = ArtifactStore(layout)
        self._manifests = ManifestStore()
        self._adapter = adapter or XbergDocumentAdapter(self._artifacts)

    @classmethod
    def with_plain_text_fallback(cls, layout: ProjectLayout) -> DocumentRunner:
        artifacts = ArtifactStore(layout)
        return cls(layout, adapter=PlainTextAdapter(artifacts))

    async def ingest(self, source: Path) -> SourceDocumentSnapshot:
        snapshot = await self._adapter.ingest(source.resolve())
        manifest_path = self._layout.document_manifest(snapshot.document_id)
        if manifest_path.exists():
            existing = self._manifests.read(manifest_path)
            existing_snapshot = existing.get("snapshot")
            if isinstance(existing_snapshot, dict):
                existing_snapshot_id = existing_snapshot.get("snapshot_id")
                if existing_snapshot_id == snapshot.snapshot_id:
                    return self._decode_snapshot(existing_snapshot)
                if snapshot.parent_snapshot_id is None and isinstance(existing_snapshot_id, str):
                    snapshot = replace(
                        snapshot,
                        parent_snapshot_id=existing_snapshot_id,
                    )
        snapshot_ref = self._artifacts.put_json(snapshot, artifact_type="source_snapshot")
        self._manifests.write(
            manifest_path,
            {
                "schema_version": "1",
                "document_id": snapshot.document_id,
                "latest_snapshot_id": snapshot.snapshot_id,
                "snapshot": snapshot,
                "snapshot_artifact": snapshot_ref,
            },
        )
        return snapshot

    def get(self, run_id: str) -> ReadingRun:
        return self._read_run(run_id)

    def get_snapshot(self, document_id: str) -> SourceDocumentSnapshot:
        manifest = self._manifests.read(self._layout.document_manifest(document_id))
        snapshot = manifest.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError(f"document manifest has no snapshot: {document_id}")
        return self._decode_snapshot(snapshot)

    def get_snapshot_by_id(self, snapshot_id: str) -> SourceDocumentSnapshot:
        return self._snapshot_for(snapshot_id)

    def _snapshot_for(self, snapshot_id: str) -> SourceDocumentSnapshot:
        for manifest_path in (self._layout.root / "documents").glob("*/manifest.json"):
            manifest = self._manifests.read(manifest_path)
            snapshot = manifest.get("snapshot")
            if isinstance(snapshot, dict) and snapshot.get("snapshot_id") == snapshot_id:
                return self._decode_snapshot(snapshot)
        raise FileNotFoundError(f"snapshot not found: {snapshot_id}")

    def _read_run(self, run_id: str) -> ReadingRun:
        return self._decode_run(self._manifests.read(self._layout.run_manifest(run_id)))

    @staticmethod
    def _decode_artifact(value: dict[str, Any]) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=str(value["artifact_id"]),
            artifact_type=str(value["artifact_type"]),
            schema_version=str(value["schema_version"]),
            content_digest=str(value["content_digest"]),
            path=str(value["path"]),
            size=int(value["size"]),
            status=ArtifactStatus(str(value["status"])),
        )

    @classmethod
    def _decode_run(cls, value: dict[str, Any]) -> ReadingRun:
        completed_at = value.get("completed_at")
        return ReadingRun(
            run_id=str(value["run_id"]),
            schema_version=str(value["schema_version"]),
            snapshot_id=str(value["snapshot_id"]),
            execution_status=ExecutionStatus(str(value["execution_status"])),
            epistemic_status=EpistemicStatus(str(value["epistemic_status"])),
            model_status=ModelStatus(str(value["model_status"])),
            publication_status=PublicationStatus(str(value["publication_status"])),
            current_task=str(value["current_task"]),
            artifacts=tuple(
                cls._decode_artifact(item) for item in value["artifacts"] if isinstance(item, dict)
            ),
            warnings=tuple(str(item) for item in value["warnings"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            completed_at=(
                datetime.fromisoformat(str(completed_at)) if completed_at is not None else None
            ),
            parent_run_id=(
                str(value["parent_run_id"]) if value.get("parent_run_id") is not None else None
            ),
            content_digest=(
                str(value["content_digest"]) if value.get("content_digest") is not None else None
            ),
        )

    @staticmethod
    def _decode_snapshot(value: dict[str, Any]) -> SourceDocumentSnapshot:
        from readwelt.domain import DocumentSection, SourceElement, SpanAnchor

        sections = []
        for section_value in value["sections"]:
            anchor_value = section_value["anchor"]
            anchor = SpanAnchor(
                anchor_id=str(anchor_value["anchor_id"]),
                snapshot_id=str(anchor_value["snapshot_id"]),
                section_id=str(anchor_value["section_id"]),
                start_offset=int(anchor_value["start_offset"]),
                end_offset=int(anchor_value["end_offset"]),
                exact_text=str(anchor_value["exact_text"]),
                prefix=str(anchor_value["prefix"]),
                suffix=str(anchor_value["suffix"]),
                page=int(anchor_value["page"]) if anchor_value.get("page") is not None else None,
            )
            sections.append(
                DocumentSection(
                    section_id=str(section_value["section_id"]),
                    title=(
                        str(section_value["title"])
                        if section_value.get("title") is not None
                        else None
                    ),
                    start_offset=int(section_value["start_offset"]),
                    end_offset=int(section_value["end_offset"]),
                    anchor=anchor,
                    kind=(
                        str(section_value["kind"])
                        if section_value.get("kind") is not None
                        else None
                    ),
                    parent_element_id=(
                        str(section_value["parent_element_id"])
                        if section_value.get("parent_element_id") is not None
                        else None
                    ),
                    heading_trail=tuple(
                        str(item) for item in section_value.get("heading_trail", ())
                    ),
                    element_id=(
                        str(section_value["element_id"])
                        if section_value.get("element_id") is not None
                        else None
                    ),
                    page=(
                        int(section_value["page"])
                        if section_value.get("page") is not None
                        else None
                    ),
                    bounding_box=(
                        _decode_bbox(section_value["bounding_box"])
                        if section_value.get("bounding_box") is not None
                        else None
                    ),
                )
            )
        source_elements = tuple(
            SourceElement(
                element_id=str(item["element_id"]),
                snapshot_id=str(item["snapshot_id"]),
                schema_version=str(item.get("schema_version", "source-element.v1")),
                ordinal=int(item["ordinal"]),
                reading_order=int(item.get("reading_order", item["ordinal"])),
                projection_status=str(item["projection_status"]),  # type: ignore[arg-type]
                kind=str(item["kind"]) if item.get("kind") is not None else None,
                content_layer=(
                    str(item["content_layer"]) if item.get("content_layer") is not None else None
                ),
                exact_text=(
                    str(item["exact_text"]) if item.get("exact_text") is not None else None
                ),
                start_offset=(
                    int(item["start_offset"]) if item.get("start_offset") is not None else None
                ),
                end_offset=(
                    int(item["end_offset"]) if item.get("end_offset") is not None else None
                ),
                parent_element_id=(
                    str(item["parent_element_id"])
                    if item.get("parent_element_id") is not None
                    else None
                ),
                child_element_ids=tuple(
                    str(child_id) for child_id in item.get("child_element_ids", ())
                ),
                previous_element_id=(
                    str(item["previous_element_id"])
                    if item.get("previous_element_id") is not None
                    else None
                ),
                next_element_id=(
                    str(item["next_element_id"])
                    if item.get("next_element_id") is not None
                    else None
                ),
                structural_relations=tuple(
                    (str(relation), str(target_id))
                    for relation, target_id in item.get("structural_relations", ())
                ),
                heading_trail=tuple(str(heading) for heading in item.get("heading_trail", ())),
                page=int(item["page"]) if item.get("page") is not None else None,
                bounding_box=(
                    _decode_bbox(item["bounding_box"])
                    if item.get("bounding_box") is not None
                    else None
                ),
                native_reference=(
                    str(item["native_reference"])
                    if item.get("native_reference") is not None
                    else None
                ),
                raw_payload_ref=(
                    str(item["raw_payload_ref"])
                    if item.get("raw_payload_ref") is not None
                    else None
                ),
            )
            for item in value.get("source_elements", ())
        )
        published_at = value.get("published_at")
        return SourceDocumentSnapshot(
            snapshot_id=str(value["snapshot_id"]),
            document_id=str(value["document_id"]),
            schema_version=str(value["schema_version"]),
            source_kind=str(value["source_kind"]),
            source_locator=str(value["source_locator"]),
            content_digest=str(value["content_digest"]),
            captured_at=datetime.fromisoformat(str(value["captured_at"])),
            language=str(value["language"]),
            normalized_text_ref=str(value["normalized_text_ref"]),
            sections=tuple(sections),
            source_elements=source_elements,
            attachments=tuple(str(item) for item in value["attachments"]),
            parse_findings=tuple(str(item) for item in value["parse_findings"]),
            published_at=(
                datetime.fromisoformat(str(published_at)) if published_at is not None else None
            ),
            author=str(value["author"]) if value.get("author") is not None else None,
            title=str(value["title"]) if value.get("title") is not None else None,
            parent_snapshot_id=(
                str(value["parent_snapshot_id"])
                if value.get("parent_snapshot_id") is not None
                else None
            ),
        )


def _decode_bbox(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("bounding_box must contain four coordinates")
    first, second, third, fourth = value
    return float(first), float(second), float(third), float(fourth)

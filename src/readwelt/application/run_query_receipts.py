"""Immutable ArticleGraph query-receipt persistence for reading runs."""

from __future__ import annotations

import json
from collections.abc import Mapping

from readwelt.article_graph import QueryReceipt
from readwelt.domain import ArtifactRef, ReadingStage
from readwelt.storage import ArtifactStore, ManifestStore, ProjectLayout

from .run_store_codec import decode_artifact_ref

QUERY_RECEIPTS_KEY = "articlegraph_query_receipts"


def append_query_receipt(
    layout: ProjectLayout,
    artifacts: ArtifactStore,
    manifests: ManifestStore,
    run_id: str,
    stage: ReadingStage,
    receipt: QueryReceipt,
) -> ArtifactRef:
    if receipt.consumer_stage != stage.value:
        raise ValueError("query receipt consumer_stage must match the reading stage")
    path = layout.run_manifest(run_id)
    manifest = manifests.read(path)
    raw_receipts = manifest.get(QUERY_RECEIPTS_KEY, [])
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_receipts, list):
        raise ValueError("articlegraph_query_receipts must be an array")
    if not isinstance(raw_artifacts, list):
        raise ValueError("run manifest artifacts must be an array")
    reference = artifacts.put_json(
        receipt.to_dict(),
        artifact_type="articlegraph_query_receipt",
        schema_version=receipt.schema_version,
    )
    if not any(
        isinstance(item, Mapping) and item.get("receipt_id") == receipt.receipt_id
        for item in raw_receipts
    ):
        raw_receipts = [
            *raw_receipts,
            {"stage": stage.value, "receipt_id": receipt.receipt_id, "artifact": reference},
        ]
    if not any(
        isinstance(item, Mapping) and item.get("artifact_id") == reference.artifact_id
        for item in raw_artifacts
    ):
        raw_artifacts = [*raw_artifacts, reference]
    manifest[QUERY_RECEIPTS_KEY] = raw_receipts
    manifest["artifacts"] = raw_artifacts
    manifests.write(path, manifest)
    return reference


def load_query_receipts(
    layout: ProjectLayout,
    artifacts: ArtifactStore,
    manifests: ManifestStore,
    run_id: str,
    stage: ReadingStage | None = None,
) -> tuple[QueryReceipt, ...]:
    path = layout.run_manifest(run_id)
    if not path.exists():
        return ()
    manifest = manifests.read(path)
    raw_receipts = manifest.get(QUERY_RECEIPTS_KEY, [])
    if not isinstance(raw_receipts, list):
        raise ValueError("articlegraph_query_receipts must be an array")
    receipts: list[QueryReceipt] = []
    for raw in raw_receipts:
        if not isinstance(raw, Mapping):
            raise ValueError("query receipt record must be an object")
        if stage is not None and raw.get("stage") != stage.value:
            continue
        raw_reference = raw.get("artifact")
        if not isinstance(raw_reference, Mapping):
            raise ValueError("query receipt record has no artifact reference")
        reference = decode_artifact_ref(raw_reference)
        payload = json.loads(artifacts.read_text(reference))
        if not isinstance(payload, Mapping):
            raise ValueError("query receipt artifact must contain an object")
        receipt = QueryReceipt.from_dict(payload)
        if raw.get("receipt_id") != receipt.receipt_id:
            raise ValueError("query receipt record identity disagrees with its artifact")
        receipts.append(receipt)
    return tuple(receipts)


__all__ = ["QUERY_RECEIPTS_KEY", "append_query_receipt", "load_query_receipts"]

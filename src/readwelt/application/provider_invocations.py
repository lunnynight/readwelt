"""Immutable request/candidate audit records stored through the run manifest."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from readwelt.domain import stable_id
from readwelt.providers import StageCandidate, StageRequest
from readwelt.storage import ArtifactStore, ManifestStore, ProjectLayout

_PROVIDER_INVOCATIONS = "provider_invocations"
_STAGE_NAVIGATION = "stage_navigation"


def begin_provider_invocation(
    layout: ProjectLayout,
    artifacts: ArtifactStore,
    manifests: ManifestStore,
    request: StageRequest,
    *,
    provider: str,
    model: str,
) -> str:
    path = layout.run_manifest(request.run_id)
    manifest = manifests.read(path)
    raw_invocations = manifest.get(_PROVIDER_INVOCATIONS, [])
    if not isinstance(raw_invocations, list):
        raise ValueError("provider_invocations must be an array")
    request_ref = artifacts.put_json(
        request,
        artifact_type="stage_request",
        schema_version=request.schema_version,
    )
    _bind_navigation_request_digest(
        manifest,
        request.stage,
        request.provenance.get("request_digest"),
    )
    attempt = sum(
        isinstance(item, Mapping) and item.get("stage") == request.stage for item in raw_invocations
    )
    invocation_id = stable_id(
        "provider_invocation",
        request.run_id,
        request.stage,
        request_ref.content_digest,
        str(attempt),
    )
    metadata_ref = artifacts.put_json(
        {
            "schema_version": "1",
            "invocation_id": invocation_id,
            "run_id": request.run_id,
            "stage": request.stage,
            "provider": provider,
            "model": model,
            "status": "started",
            "request_digest": request_ref.content_digest,
            "raw_http_body": "unavailable_at_candidate_provider_boundary",
            "recorded_at": datetime.now(UTC),
        },
        artifact_type="provider_invocation",
    )
    manifest[_PROVIDER_INVOCATIONS] = [
        *raw_invocations,
        {
            "invocation_id": invocation_id,
            "stage": request.stage,
            "request": request_ref,
            "request_digest": request_ref.content_digest,
            "candidate": None,
            "metadata": [metadata_ref],
            "status": "started",
        },
    ]
    manifests.write(path, manifest)
    return invocation_id


def finish_provider_invocation(
    layout: ProjectLayout,
    artifacts: ArtifactStore,
    manifests: ManifestStore,
    run_id: str,
    invocation_id: str,
    *,
    status: str,
    candidate: StageCandidate | None = None,
    error: str | None = None,
) -> None:
    path = layout.run_manifest(run_id)
    manifest = manifests.read(path)
    raw_invocations = manifest.get(_PROVIDER_INVOCATIONS)
    if not isinstance(raw_invocations, list):
        raise ValueError("provider_invocations must be an array")
    matches = [
        index
        for index, item in enumerate(raw_invocations)
        if isinstance(item, Mapping) and item.get("invocation_id") == invocation_id
    ]
    if len(matches) != 1:
        raise ValueError("provider invocation record is missing or duplicated")
    index = matches[0]
    record = raw_invocations[index]
    if not isinstance(record, Mapping) or record.get("status") != "started":
        raise ValueError("provider invocation is already finalized")
    request_digest = str(record["request_digest"])
    candidate_ref = (
        artifacts.put_json(
            {
                **candidate.to_dict(),
                "audit_request_digest": request_digest,
            },
            artifact_type="stage_candidate",
            schema_version=candidate.schema_version,
        )
        if candidate is not None
        else None
    )
    metadata_ref = artifacts.put_json(
        {
            "schema_version": "1",
            "invocation_id": invocation_id,
            "run_id": run_id,
            "stage": record["stage"],
            "status": status,
            "request_digest": request_digest,
            "candidate_digest": (
                candidate_ref.content_digest if candidate_ref is not None else None
            ),
            "error": error,
            "raw_response": (
                candidate.raw_response
                if candidate is not None and candidate.raw_response is not None
                else "unavailable_at_candidate_provider_boundary"
            ),
            "recorded_at": datetime.now(UTC),
        },
        artifact_type="provider_invocation",
    )
    metadata = record.get("metadata")
    if not isinstance(metadata, list):
        raise ValueError("provider invocation metadata must be an array")
    finalized = {
        **record,
        "candidate": candidate_ref,
        "metadata": [*metadata, metadata_ref],
        "status": status,
    }
    updated = list(raw_invocations)
    updated[index] = finalized
    manifest[_PROVIDER_INVOCATIONS] = updated
    manifests.write(path, manifest)


def _bind_navigation_request_digest(
    manifest: dict[str, Any],
    raw_stage: str,
    digest: object,
) -> None:
    if not isinstance(digest, str):
        return
    raw_navigation = manifest.get(_STAGE_NAVIGATION)
    if not isinstance(raw_navigation, Mapping):
        return
    raw = raw_navigation.get(raw_stage)
    if not isinstance(raw, Mapping):
        return
    manifest[_STAGE_NAVIGATION] = {
        **dict(raw_navigation),
        raw_stage: {**dict(raw), "latest_request_digest": digest},
    }

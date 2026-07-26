"""Atomic application-run and settled-stage persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from readwelt.domain import (
    ArtifactRef,
    ArtifactStatus,
    LedgerDecision,
    ReadingClaim,
    ReadingGap,
    ReadingRun,
    ReadingStage,
    StageArtifact,
    stable_id,
)
from readwelt.providers import ProviderSelection, StageCandidate, StageRequest
from readwelt.storage import ArtifactStore, ManifestStore, ProjectLayout

_STAGES = tuple(ReadingStage)
_STAGE_RECORDS = "settled_stage_artifacts"
_PROVIDER_INVOCATIONS = "provider_invocations"


class ApplicationRunStore:
    """Keep the run manifest as the atomic index over immutable CAS objects."""

    def __init__(self, layout: ProjectLayout, artifacts: ArtifactStore) -> None:
        self._layout = layout
        self._artifacts = artifacts
        self._manifests = ManifestStore()

    def write(
        self,
        run: ReadingRun,
        *,
        pipeline_policy: str,
        selection: ProviderSelection,
        purpose: str,
        token_budget: int,
    ) -> None:
        path = self._layout.run_manifest(run.run_id)
        preserved: dict[str, object] = {
            _STAGE_RECORDS: [],
            _PROVIDER_INVOCATIONS: [],
        }
        if path.exists():
            existing = self._manifests.read(path)
            preserved = {key: existing.get(key, []) for key in preserved}
        self._manifests.write(
            path,
            {
                **run_mapping(run),
                "pipeline_policy": pipeline_policy,
                "provider_selection": selection.to_dict(),
                "purpose": purpose,
                "token_budget": token_budget,
                **preserved,
            },
        )

    def append_stage_artifact(self, run_id: str, artifact: StageArtifact) -> ArtifactRef:
        path = self._layout.run_manifest(run_id)
        manifest = self._manifests.read(path)
        existing = self._decode_records(run_id, manifest)
        ordinal = len(existing)
        if ordinal >= len(_STAGES):
            raise ValueError(f"run already has all settled stages: {run_id}")
        expected = _STAGES[ordinal]
        if artifact.run_id != run_id:
            raise ValueError("settled stage artifact belongs to another run")
        if artifact.stage is not expected:
            raise ValueError(
                f"settled stage artifact is not the next prefix stage: "
                f"expected {expected.value}, got {artifact.stage.value}"
            )
        expected_inputs = tuple(item.artifact_id for item in existing)
        if artifact.input_artifact_ids != expected_inputs:
            raise ValueError("settled stage artifact input lineage does not match the prefix")

        reference = self._artifacts.put_json(
            artifact,
            artifact_type="stage_artifact",
            schema_version="1",
        )
        raw_artifacts = manifest.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise ValueError("run manifest artifacts must be an array")
        raw_records = manifest.get(_STAGE_RECORDS)
        if not isinstance(raw_records, list):
            raise ValueError("settled_stage_artifacts must be an array")
        manifest["artifacts"] = [*raw_artifacts, reference]
        manifest[_STAGE_RECORDS] = [
            *raw_records,
            {"stage": artifact.stage.value, "artifact": reference},
        ]
        self._manifests.write(path, manifest)
        return reference

    def begin_provider_invocation(
        self,
        request: StageRequest,
        *,
        provider: str,
        model: str,
    ) -> str:
        path = self._layout.run_manifest(request.run_id)
        manifest = self._manifests.read(path)
        raw_invocations = manifest.get(_PROVIDER_INVOCATIONS, [])
        if not isinstance(raw_invocations, list):
            raise ValueError("provider_invocations must be an array")
        request_ref = self._artifacts.put_json(
            request,
            artifact_type="stage_request",
            schema_version=request.schema_version,
        )
        attempt = sum(
            isinstance(item, Mapping) and item.get("stage") == request.stage
            for item in raw_invocations
        )
        invocation_id = stable_id(
            "provider_invocation",
            request.run_id,
            request.stage,
            request_ref.content_digest,
            str(attempt),
        )
        metadata_ref = self._artifacts.put_json(
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
        self._manifests.write(path, manifest)
        return invocation_id

    def finish_provider_invocation(
        self,
        run_id: str,
        invocation_id: str,
        *,
        status: str,
        candidate: StageCandidate | None = None,
        error: str | None = None,
    ) -> None:
        path = self._layout.run_manifest(run_id)
        manifest = self._manifests.read(path)
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
            self._artifacts.put_json(
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
        metadata_ref = self._artifacts.put_json(
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
        self._manifests.write(path, manifest)

    def load_stage_artifacts(self, run_id: str) -> tuple[StageArtifact, ...]:
        path = self._layout.run_manifest(run_id)
        if not path.exists():
            return ()
        return self._decode_records(run_id, self._manifests.read(path))

    def _decode_records(
        self,
        run_id: str,
        manifest: Mapping[str, Any],
    ) -> tuple[StageArtifact, ...]:
        raw_records = manifest.get(_STAGE_RECORDS, [])
        if not isinstance(raw_records, list):
            raise ValueError("settled_stage_artifacts must be an array")
        run_references = self._run_references(manifest)
        artifacts: list[StageArtifact] = []
        for ordinal, value in enumerate(raw_records):
            if not isinstance(value, Mapping):
                raise ValueError("settled stage record must be an object")
            expected = _STAGES[ordinal] if ordinal < len(_STAGES) else None
            if expected is None or value.get("stage") != expected.value:
                raise ValueError("settled stage records must be the fixed stage prefix")
            raw_reference = value.get("artifact")
            if not isinstance(raw_reference, Mapping):
                raise ValueError("settled stage record has no artifact reference")
            reference = _decode_artifact_ref(raw_reference)
            if reference.artifact_type != "stage_artifact":
                raise ValueError("settled stage record references the wrong artifact type")
            indexed = run_references.get(reference.artifact_id)
            if indexed != reference:
                raise ValueError("settled stage artifact is not indexed by the run")
            raw = json.loads(self._artifacts.read_text(reference))
            if not isinstance(raw, Mapping):
                raise ValueError("settled stage artifact CAS payload must be an object")
            artifact = _decode_stage_artifact(raw)
            if artifact.run_id != run_id or artifact.stage is not expected:
                raise ValueError("settled stage artifact identity does not match its record")
            expected_inputs = tuple(item.artifact_id for item in artifacts)
            if artifact.input_artifact_ids != expected_inputs:
                raise ValueError("settled stage artifact input lineage is invalid")
            artifacts.append(artifact)
        return tuple(artifacts)

    @staticmethod
    def _run_references(manifest: Mapping[str, Any]) -> dict[str, ArtifactRef]:
        raw = manifest.get("artifacts")
        if not isinstance(raw, list):
            raise ValueError("run manifest artifacts must be an array")
        references = tuple(_decode_artifact_ref(item) for item in raw if isinstance(item, Mapping))
        if len(references) != len(raw):
            raise ValueError("run manifest contains an invalid artifact reference")
        if len({item.artifact_id for item in references}) != len(references):
            raise ValueError("run manifest contains duplicate artifact ids")
        return {item.artifact_id: item for item in references}


def run_mapping(run: ReadingRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "schema_version": run.schema_version,
        "snapshot_id": run.snapshot_id,
        "execution_status": run.execution_status,
        "epistemic_status": run.epistemic_status,
        "model_status": run.model_status,
        "publication_status": run.publication_status,
        "current_task": run.current_task,
        "artifacts": run.artifacts,
        "warnings": run.warnings,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "parent_run_id": run.parent_run_id,
        "content_digest": run.content_digest,
    }


def _decode_artifact_ref(value: Mapping[str, Any]) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=str(value["artifact_id"]),
        artifact_type=str(value["artifact_type"]),
        schema_version=str(value["schema_version"]),
        content_digest=str(value["content_digest"]),
        path=str(value["path"]),
        size=int(value["size"]),
        status=ArtifactStatus(str(value["status"])),
    )


def _decode_stage_artifact(value: Mapping[str, Any]) -> StageArtifact:
    stage = ReadingStage(str(value["stage"]))
    raw_claims = value.get("claims")
    raw_gaps = value.get("gaps")
    if not isinstance(raw_claims, list) or not isinstance(raw_gaps, list):
        raise ValueError("stage artifact claims and gaps must be arrays")
    claims = tuple(_decode_claim(item, stage) for item in raw_claims)
    gaps = tuple(_decode_gap(item, stage) for item in raw_gaps)
    return StageArtifact(
        artifact_id=str(value["artifact_id"]),
        run_id=str(value["run_id"]),
        stage=stage,
        claims=claims,
        gaps=gaps,
        warnings=_string_tuple(value.get("warnings"), "warnings"),
        input_artifact_ids=_string_tuple(
            value.get("input_artifact_ids"),
            "input_artifact_ids",
        ),
        provider=str(value["provider"]),
        model=str(value["model"]) if value.get("model") is not None else None,
        status=_epistemic_status(value["status"]),
        content_digest=str(value["content_digest"]),
        provider_provenance=_pairs(
            value.get("provider_provenance", []),
            "provider_provenance",
        ),
    )


def _decode_claim(value: object, stage: ReadingStage) -> ReadingClaim:
    if not isinstance(value, Mapping):
        raise ValueError("stage artifact claim must be an object")
    return ReadingClaim(
        claim_id=str(value["claim_id"]),
        text=str(value["text"]),
        stage=stage,
        anchor_ids=_string_tuple(value.get("anchor_ids"), "anchor_ids"),
        decision=LedgerDecision(str(value["decision"])),
        source_claim_ids=_string_tuple(
            value.get("source_claim_ids"),
            "source_claim_ids",
        ),
        limitations=_string_tuple(value.get("limitations"), "limitations"),
        provenance=_pairs(value.get("provenance", []), "claim provenance"),
    )


def _decode_gap(value: object, stage: ReadingStage) -> ReadingGap:
    if not isinstance(value, Mapping):
        raise ValueError("stage artifact gap must be an object")
    return ReadingGap(
        gap_id=str(value["gap_id"]),
        kind=str(value["kind"]),
        description=str(value["description"]),
        origin_stage=stage,
        affected_claim_ids=_string_tuple(
            value.get("affected_claim_ids"),
            "affected_claim_ids",
        ),
        critical=_strict_bool(value.get("critical"), "critical"),
        repairable=_strict_bool(value.get("repairable"), "repairable"),
        resolved=_strict_bool(value.get("resolved"), "resolved"),
    )


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _pairs(value: object, label: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    pairs: list[tuple[str, str]] = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"{label} entries must be key/value pairs")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(pairs)


def _epistemic_status(value: object) -> Any:
    from readwelt.domain import EpistemicStatus

    return EpistemicStatus(str(value))

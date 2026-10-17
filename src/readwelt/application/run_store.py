"""Atomic application-run and settled-stage persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from readwelt.article_graph import QueryReceipt
from readwelt.domain import (
    ArtifactRef,
    ReadingRun,
    ReadingStage,
    StageArtifact,
    StageInputStatus,
)
from readwelt.providers import ProviderSelection, StageCandidate, StageRequest
from readwelt.stage_views import StageView, StageViewContinuationCursor
from readwelt.storage import ArtifactStore, ManifestStore, ProjectLayout

from .provider_invocations import (
    begin_provider_invocation as _begin_provider_invocation,
)
from .provider_invocations import (
    finish_provider_invocation as _finish_provider_invocation,
)
from .run_query_receipts import QUERY_RECEIPTS_KEY
from .run_query_receipts import append_query_receipt as _append_query_receipt
from .run_query_receipts import load_query_receipts as _load_query_receipts
from .run_store_codec import (
    StageNavigationState,
    run_mapping,
)
from .run_store_codec import (
    decode_artifact_ref as _decode_artifact_ref,
)
from .run_store_codec import (
    decode_navigation as _decode_navigation,
)
from .run_store_codec import (
    decode_stage_artifact as _decode_stage_artifact,
)
from .run_store_codec import (
    navigation_mapping as _navigation_mapping,
)

_STAGES = tuple(ReadingStage)
_STAGE_RECORDS = "settled_stage_artifacts"
_PROVISIONAL_STAGE_RECORDS = "provisional_stage_artifacts"
_PROVIDER_INVOCATIONS = "provider_invocations"
_STAGE_NAVIGATION = "stage_navigation"


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
        hard_serialized_token_budget: int | None,
    ) -> None:
        path = self._layout.run_manifest(run.run_id)
        preserved: dict[str, object] = {
            _STAGE_RECORDS: [],
            _PROVISIONAL_STAGE_RECORDS: [],
            _PROVIDER_INVOCATIONS: [],
            _STAGE_NAVIGATION: {},
            QUERY_RECEIPTS_KEY: [],
        }
        if path.exists():
            existing = self._manifests.read(path)
            preserved = {key: existing.get(key, default) for key, default in preserved.items()}
        self._manifests.write(
            path,
            {
                **run_mapping(run),
                "pipeline_policy": pipeline_policy,
                "provider_selection": selection.to_dict(),
                "purpose": purpose,
                "token_budget": token_budget,
                "hard_serialized_token_budget": hard_serialized_token_budget,
                **preserved,
            },
        )

    def append_query_receipt(
        self,
        run_id: str,
        stage: ReadingStage,
        receipt: QueryReceipt,
    ) -> ArtifactRef:
        """Persist one immutable stage-scoped query receipt and index it in the run."""
        return _append_query_receipt(
            self._layout,
            self._artifacts,
            self._manifests,
            run_id,
            stage,
            receipt,
        )

    def load_query_receipts(
        self,
        run_id: str,
        stage: ReadingStage | None = None,
    ) -> tuple[QueryReceipt, ...]:
        return _load_query_receipts(
            self._layout,
            self._artifacts,
            self._manifests,
            run_id,
            stage,
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
            schema_version=(
                "3"
                if artifact.decompression_artifact is not None
                else "2"
                if artifact.input_state is not None
                else "1"
            ),
        )
        raw_artifacts = manifest.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise ValueError("run manifest artifacts must be an array")
        raw_records = manifest.get(_STAGE_RECORDS)
        if not isinstance(raw_records, list):
            raise ValueError("settled_stage_artifacts must be an array")
        manifest["artifacts"] = (
            raw_artifacts
            if any(
                isinstance(item, Mapping) and item.get("artifact_id") == reference.artifact_id
                for item in raw_artifacts
            )
            else [*raw_artifacts, reference]
        )
        if (
            artifact.input_state is not None
            and artifact.input_state.status is not StageInputStatus.COMPLETE
        ):
            raw_provisional = manifest.get(_PROVISIONAL_STAGE_RECORDS)
            if not isinstance(raw_provisional, list):
                raise ValueError("provisional_stage_artifacts must be an array")
            if not any(
                isinstance(item, Mapping)
                and isinstance(item.get("artifact"), Mapping)
                and item["artifact"].get("artifact_id") == reference.artifact_id
                for item in raw_provisional
            ):
                manifest[_PROVISIONAL_STAGE_RECORDS] = [
                    *raw_provisional,
                    {"stage": artifact.stage.value, "artifact": reference},
                ]
            self._manifests.write(path, manifest)
            return reference
        manifest[_STAGE_RECORDS] = [
            *raw_records,
            {"stage": artifact.stage.value, "artifact": reference},
        ]
        self._manifests.write(path, manifest)
        return reference

    def load_provisional_stage_artifacts(
        self,
        run_id: str,
    ) -> tuple[StageArtifact, ...]:
        path = self._layout.run_manifest(run_id)
        if not path.exists():
            return ()
        manifest = self._manifests.read(path)
        raw_records = manifest.get(_PROVISIONAL_STAGE_RECORDS, [])
        if not isinstance(raw_records, list):
            raise ValueError("provisional_stage_artifacts must be an array")
        run_references = self._run_references(manifest)
        result: list[StageArtifact] = []
        for value in raw_records:
            if not isinstance(value, Mapping) or not isinstance(value.get("artifact"), Mapping):
                raise ValueError("provisional stage record must reference an artifact")
            reference = _decode_artifact_ref(value["artifact"])
            if run_references.get(reference.artifact_id) != reference:
                raise ValueError("provisional stage artifact is not indexed by the run")
            raw = json.loads(self._artifacts.read_text(reference))
            if not isinstance(raw, Mapping):
                raise ValueError("provisional stage artifact payload must be an object")
            artifact = _decode_stage_artifact(raw)
            if artifact.run_id != run_id or artifact.fully_settled:
                raise ValueError("provisional stage artifact settlement state is invalid")
            result.append(artifact)
        return tuple(result)

    def save_stage_navigation(
        self,
        run_id: str,
        stage: ReadingStage,
        *,
        input_continuation: StageViewContinuationCursor | None,
        view: StageView,
        targeted_anchor_ids: tuple[str, ...],
        rescue_level: str,
    ) -> StageNavigationState:
        path = self._layout.run_manifest(run_id)
        manifest = self._manifests.read(path)
        raw_navigation = manifest.get(_STAGE_NAVIGATION, {})
        if not isinstance(raw_navigation, Mapping):
            raise ValueError("stage_navigation must be an object")
        existing = self.load_stage_navigation(run_id, stage)
        input_digest = input_continuation.content_digest if input_continuation is not None else None
        if existing is None:
            page_index = 0
        elif (
            existing.next_continuation is not None
            and input_digest == existing.next_continuation.content_digest
        ):
            page_index = existing.page_index + 1
        elif (existing.input_continuation is None and input_continuation is None) or (
            existing.input_continuation is not None
            and input_digest == existing.input_continuation.content_digest
        ):
            page_index = existing.page_index
        else:
            raise ValueError("stage navigation input does not continue the persisted frontier")
        view_ref = self._artifacts.put_json(
            view,
            artifact_type="stage_view",
            schema_version=view.schema_version,
        )
        raw_artifacts = manifest.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise ValueError("run manifest artifacts must be an array")
        if not any(
            isinstance(item, Mapping) and item.get("artifact_id") == view_ref.artifact_id
            for item in raw_artifacts
        ):
            manifest["artifacts"] = [*raw_artifacts, view_ref]
        state = StageNavigationState(
            stage=stage,
            page_index=page_index,
            input_continuation=input_continuation,
            next_continuation=view.continuation,
            targeted_anchor_ids=targeted_anchor_ids,
            rescue_level=rescue_level,
            stage_view=view_ref,
            latest_request_digest=(
                existing.latest_request_digest if existing is not None else None
            ),
            stage_view_hard_serialized_token_budget=(view.hard_serialized_token_budget),
            stage_view_token_budget=view.token_budget,
        )
        manifest[_STAGE_NAVIGATION] = {
            **dict(raw_navigation),
            stage.value: _navigation_mapping(state),
        }
        self._manifests.write(path, manifest)
        return state

    def load_stage_navigation(
        self,
        run_id: str,
        stage: ReadingStage,
    ) -> StageNavigationState | None:
        path = self._layout.run_manifest(run_id)
        if not path.exists():
            return None
        manifest = self._manifests.read(path)
        raw_navigation = manifest.get(_STAGE_NAVIGATION, {})
        if not isinstance(raw_navigation, Mapping):
            raise ValueError("stage_navigation must be an object")
        raw = raw_navigation.get(stage.value)
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ValueError("stage navigation entry must be an object")
        return _decode_navigation(stage, raw)

    def configure_stage_navigation(
        self,
        run_id: str,
        stage: ReadingStage,
        *,
        targeted_anchor_ids: tuple[str, ...],
        rescue_level: str,
    ) -> None:
        state = self.load_stage_navigation(run_id, stage)
        if state is None:
            raise ValueError("stage has no persisted navigation state")
        if rescue_level not in {
            "initial",
            "neighbors",
            "structure",
            "targeted",
            "section",
        }:
            raise ValueError(f"unsupported rescue_level: {rescue_level}")
        path = self._layout.run_manifest(run_id)
        manifest = self._manifests.read(path)
        raw_navigation = manifest.get(_STAGE_NAVIGATION)
        if not isinstance(raw_navigation, Mapping):
            raise ValueError("stage_navigation must be an object")
        navigation_changed = (
            state.targeted_anchor_ids != targeted_anchor_ids or state.rescue_level != rescue_level
        )
        updated = StageNavigationState(
            stage=state.stage,
            page_index=state.page_index + int(navigation_changed),
            input_continuation=(None if navigation_changed else state.input_continuation),
            next_continuation=(None if navigation_changed else state.next_continuation),
            targeted_anchor_ids=targeted_anchor_ids,
            rescue_level=rescue_level,
            stage_view=state.stage_view,
            latest_request_digest=state.latest_request_digest,
            stage_view_hard_serialized_token_budget=(state.stage_view_hard_serialized_token_budget),
            stage_view_token_budget=state.stage_view_token_budget,
        )
        manifest[_STAGE_NAVIGATION] = {
            **dict(raw_navigation),
            stage.value: _navigation_mapping(updated),
        }
        self._manifests.write(path, manifest)

    def begin_provider_invocation(
        self,
        request: StageRequest,
        *,
        provider: str,
        model: str,
    ) -> str:
        return _begin_provider_invocation(
            self._layout,
            self._artifacts,
            self._manifests,
            request,
            provider=provider,
            model=model,
        )

    def finish_provider_invocation(
        self,
        run_id: str,
        invocation_id: str,
        *,
        status: str,
        candidate: StageCandidate | None = None,
        error: str | None = None,
    ) -> None:
        _finish_provider_invocation(
            self._layout,
            self._artifacts,
            self._manifests,
            run_id,
            invocation_id,
            status=status,
            candidate=candidate,
            error=error,
        )

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

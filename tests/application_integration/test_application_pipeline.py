from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from readwelt.application import ReadweltApplicationService
from readwelt.domain import ExecutionStatus, ReadingStage
from readwelt.providers import (
    ProviderKind,
    ProviderSelection,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
)


class PipelineProvider:
    def __init__(self, kind: ProviderKind = ProviderKind.LOCAL) -> None:
        self._kind = kind
        self.requests: list[StageRequest] = []

    @property
    def kind(self) -> ProviderKind:
        return self._kind

    @property
    def name(self) -> str:
        return f"fake-{self.kind.value}"

    @property
    def model(self) -> str:
        return "fake-v1"

    async def generate(
        self,
        request: StageRequest,
        response_schema: Mapping[str, Any],
    ) -> StageCandidate:
        self.requests.append(request)
        assert response_schema["type"] == "object"
        stage = ReadingStage(request.stage)
        anchors = request.evidence_packet["anchors"]
        claims: list[dict[str, Any]] = [
            {
                "claim_id": f"{stage.value}:claim:{index}",
                "text": f"{stage.value} claim {index}",
                "anchor_ids": [anchors[0]["anchor_id"]],
                "decision": "accepted",
                **(
                    {"provenance": {"interpretation_id": f"lens-{index}"}}
                    if request.stage == ReadingStage.AUTHOR_MODEL.value
                    else {}
                ),
            }
            for index in range(2 if stage is ReadingStage.AUTHOR_MODEL else 1)
        ]
        if stage not in (ReadingStage.MAINLINE, ReadingStage.STRUCTURE):
            upstream = request.evidence_packet["upstream_claims"]
            for claim in claims:
                claim["source_claim_ids"] = [upstream[0]["claim_id"]]
        return StageCandidate(
            schema_version="1",
            run_id=request.run_id,
            stage=request.stage,
            candidate={"claims": claims, "gaps": [], "warnings": []},
            provider=self.name,
            model=self.model,
        )


class PipelineInterrupted(BaseException):
    pass


class InterruptingProvider(PipelineProvider):
    def __init__(self, interrupt_after: int) -> None:
        super().__init__()
        self._interrupt_after = interrupt_after

    async def generate(
        self,
        request: StageRequest,
        response_schema: Mapping[str, Any],
    ) -> StageCandidate:
        if len(self.requests) == self._interrupt_after:
            raise PipelineInterrupted
        return await super().generate(request, response_schema)


def test_prepare_persists_semantic_atlas(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("第一段。\n\n第二段。", encoding="utf-8")
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
    )
    snapshot = service.import_document(source)

    atlas = service.prepare(snapshot.document_id)

    assert atlas.snapshot_id == snapshot.snapshot_id
    assert len(atlas.segments) == 2
    manifest = (service.root / "documents" / snapshot.document_id / "manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"semantic_atlas_artifact"' in manifest


def test_read_requires_an_explicitly_available_provider(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("内容", encoding="utf-8")
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
    )

    with pytest.raises(ProviderUnavailableError, match="no model provider"):
        service.read(source)


def test_read_executes_and_persists_the_full_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("第一段提供主张。\n\n第二段提供限制。", encoding="utf-8")
    provider = PipelineProvider()
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(provider,),
    )

    run = service.read(
        source,
        provider_selection=ProviderSelection.build(primary="local"),
        idempotency_key="integration-test",
    )

    assert run.execution_status is ExecutionStatus.COMPLETED
    assert len(provider.requests) == 6
    assert {artifact.artifact_type for artifact in run.artifacts} == {
        "source_snapshot",
        "semantic_atlas",
        "stage_artifact",
        "reading_bundle",
        "reader_report_markdown",
    }
    assert sum(artifact.artifact_type == "stage_artifact" for artifact in run.artifacts) == 6
    manifest = json.loads(
        (service.root / "runs" / run.run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["settled_stage_artifacts"]) == 6
    assert len(manifest["provider_invocations"]) == 6
    assert all(
        item["request"]["artifact_type"] == "stage_request"
        for item in manifest["provider_invocations"]
    )
    assert all(
        item["candidate"]["artifact_type"] == "stage_candidate"
        for item in manifest["provider_invocations"]
    )
    report = next(
        artifact for artifact in run.artifacts if artifact.artifact_type == "reader_report_markdown"
    )
    assert (service.root / report.path).read_text(encoding="utf-8").startswith("# 逆向阅读")
    reopened = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(provider,),
    )
    assert reopened.get_run(run.run_id) == run
    bundle = next(
        artifact for artifact in run.artifacts if artifact.artifact_type == "reading_bundle"
    )
    retrieved = service.get_artifact(bundle.content_digest)
    assert retrieved["digest"] == bundle.content_digest
    assert retrieved["path"] == bundle.path


def test_agent_takeover_pauses_and_replays_submitted_candidates(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("外部 Agent 可复核的正文。", encoding="utf-8")
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    run = service.read(
        source,
        provider_selection=ProviderSelection.build(mode="agent_takeover"),
        idempotency_key="agent-integration",
    )

    for stage in ReadingStage:
        assert run.execution_status is ExecutionStatus.PENDING
        assert run.current_task == f"awaiting_agent:{stage.value}"
        request = service.pull_stage_request(run.run_id, stage.value)
        anchors = request.evidence_packet["anchors"]
        claims: list[dict[str, Any]] = [
            {
                "claim_id": f"{stage.value}:claim:{index}",
                "text": f"{stage.value} claim {index}",
                "anchor_ids": [anchors[0]["anchor_id"]],
                "decision": "accepted",
                **(
                    {"provenance": {"interpretation_id": f"lens-{index}"}}
                    if stage is ReadingStage.AUTHOR_MODEL
                    else {}
                ),
            }
            for index in range(2 if stage is ReadingStage.AUTHOR_MODEL else 1)
        ]
        if stage not in (ReadingStage.MAINLINE, ReadingStage.STRUCTURE):
            upstream = request.evidence_packet["upstream_claims"]
            for claim in claims:
                claim["source_claim_ids"] = [upstream[0]["claim_id"]]
        run = service.submit_stage_candidate(
            run.run_id,
            stage.value,
            StageCandidate(
                schema_version="1",
                run_id=run.run_id,
                stage=stage.value,
                candidate={"claims": claims, "gaps": [], "warnings": []},
                provider="codex-test-agent",
                model="test",
                provenance={
                    "request_digest": request.provenance["request_digest"],
                },
            ),
        )

    assert run.execution_status is ExecutionStatus.COMPLETED
    assert run.current_task == "completed"


def test_resume_uses_settled_stage_prefix_without_repeating_providers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "article.txt"
    source.write_text("阶段级恢复正文。", encoding="utf-8")
    interrupted = InterruptingProvider(interrupt_after=3)
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(interrupted,),
    )
    with pytest.raises(PipelineInterrupted):
        service.read(
            source,
            provider_selection=ProviderSelection.build(primary="local"),
            idempotency_key="stage-resume",
        )
    run_id = next((service.root / "runs").iterdir()).name
    manifest = json.loads(
        (service.root / "runs" / run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["settled_stage_artifacts"]) == 3

    resumed_provider = PipelineProvider()
    reopened = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(resumed_provider,),
    )
    resumed = reopened.resume(run_id)

    assert resumed.execution_status is ExecutionStatus.COMPLETED
    assert [request.stage for request in resumed_provider.requests] == [
        ReadingStage.AUTHOR_MODEL.value,
        ReadingStage.BOUNDARIES.value,
        ReadingStage.TRANSFER.value,
    ]

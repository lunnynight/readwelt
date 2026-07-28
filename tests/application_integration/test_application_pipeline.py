from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from readwelt.application import ReadweltApplicationService
from readwelt.domain import ExecutionStatus, ReadingStage
from readwelt.providers import (
    ProviderContractError,
    ProviderKind,
    ProviderSelection,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
)
from readwelt.providers.external_agent import ExternalAgentAdapter


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
        anchors_value = request.evidence_packet["anchors"]
        anchors = anchors_value["items"] if isinstance(anchors_value, Mapping) else anchors_value
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
            upstream_value = request.evidence_packet["upstream_claims"]
            upstream = (
                upstream_value["items"] if isinstance(upstream_value, Mapping) else upstream_value
            )
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
    assert '"article_graph_artifact"' in manifest


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
        "anchored_text_unitization",
        "graph_extraction",
        "article_graph_merge_report",
        "article_graph_provenance_ledger",
        "article_graph_source_index",
        "article_graph",
        "article_graph_build",
        "stage_view",
        "stage_artifact",
        "reading_bundle",
        "reader_report_markdown",
    }
    assert sum(artifact.artifact_type == "graph_extraction" for artifact in run.artifacts) == 2
    assert sum(artifact.artifact_type == "stage_view" for artifact in run.artifacts) == 6
    assert sum(artifact.artifact_type == "stage_artifact" for artifact in run.artifacts) == 6
    graph_build_ref = next(
        artifact for artifact in run.artifacts if artifact.artifact_type == "article_graph_build"
    )
    graph_build_payload = json.loads(
        (service.root / graph_build_ref.path).read_text(encoding="utf-8")
    )
    assert graph_build_payload["schema_version"] == "article-graph-build-artifact.v2"
    assert graph_build_payload["build_schema_version"] == "article-graph-build.v2"
    assert "graph" not in graph_build_payload
    assert "unitization" not in graph_build_payload
    assert "extractions" not in graph_build_payload
    assert {reference["role"] for reference in graph_build_payload["references"]} == {
        "unitization",
        "extraction:readwelt.linguistic.regex",
        "extraction:readwelt.semantic.explicit-unit",
        "merge_report",
        "provenance_ledger",
        "source_index",
        "graph",
    }
    child_graph_artifacts_size = sum(
        artifact.size
        for artifact in run.artifacts
        if artifact.artifact_type
        in {
            "anchored_text_unitization",
            "graph_extraction",
            "article_graph_merge_report",
            "article_graph_provenance_ledger",
            "article_graph_source_index",
            "article_graph",
        }
    )
    assert graph_build_ref.size < 8_000
    assert graph_build_ref.size < child_graph_artifacts_size // 4
    assert all("stage_view" in request.evidence_packet for request in provider.requests)
    assert all(
        request.evidence_packet["stage_view"]["stage"] == request.stage
        for request in provider.requests
    )
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


def test_stage_page_resume_persists_frontier_across_application_hosts(
    tmp_path: Path,
) -> None:
    hard_budget = 20_000
    source = tmp_path / "long-article.txt"
    source.write_text(
        "\n\n".join(
            f"Paragraph {index:02d} contains source-grounded evidence for paging."
            for index in range(43)
        ),
        encoding="utf-8",
    )
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    run = service.read(
        source,
        provider_selection=ProviderSelection.build(mode="agent_takeover"),
        token_budget=hard_budget,
        idempotency_key="stage-page-resume",
    )
    stage = ReadingStage.MAINLINE
    first = service.pull_stage_request(run.run_id, stage.value)
    first_view = first.evidence_packet["stage_view"]
    first_ordinals = [item["ordinal"] for item in first_view["text_units"]]

    reopened = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    resumed = reopened.resume_stage_page(
        run.run_id,
        stage,
        targeted_anchor_ids=(),
        rescue_level="section",
    )
    assert resumed.execution_status is ExecutionStatus.PENDING
    second = reopened.pull_stage_request(run.run_id, stage.value)
    second_view = second.evidence_packet["stage_view"]
    second_ordinals = [item["ordinal"] for item in second_view["text_units"]]

    assert first.provenance["stage_page_index"] == 0
    assert second.provenance["stage_page_index"] == 1
    assert second.provenance["previous_request_digest"] == first.provenance["request_digest"]
    assert (
        second.provenance["input_continuation_digest"]
        == first.provenance["next_continuation_digest"]
    )
    assert first_ordinals
    assert second_ordinals
    assert min(second_ordinals) >= max(first_ordinals)
    assert second.estimated_serialized_tokens <= hard_budget
    assert second.budget_manifest["provider_input"]["max_tokens"] <= hard_budget

    manifest = json.loads(
        (reopened.root / "runs" / run.run_id / "manifest.json").read_text(encoding="utf-8")
    )
    navigation = manifest["stage_navigation"][stage.value]
    assert navigation["page_index"] == 1
    assert navigation["next_continuation"] is not None
    assert navigation["stage_view_token_budget"] == second_view["token_budget"]
    assert (
        navigation["stage_view_hard_serialized_token_budget"]
        == (second_view["hard_serialized_token_budget"])
    )
    assert second_view["token_budget"] == first_view["token_budget"]
    assert (
        second_view["hard_serialized_token_budget"] == (first_view["hard_serialized_token_budget"])
    )
    assert (reopened.root / "runs" / run.run_id / "agent" / stage.value / "pages").is_dir()

    target_anchor_id = first.evidence_packet["anchors"]["items"][0]["anchor_id"]
    third_host = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    targeted = third_host.resume_stage_page(
        run.run_id,
        stage,
        targeted_anchor_ids=(target_anchor_id,),
        rescue_level="targeted",
    )
    assert targeted.execution_status is ExecutionStatus.PENDING
    third = third_host.pull_stage_request(run.run_id, stage.value)
    assert third.provenance["stage_page_index"] == 2
    assert third.provenance["previous_request_digest"] == second.provenance["request_digest"]
    assert third.provenance["input_continuation_digest"] is None
    assert third.provenance["rescue_level"] == "targeted"
    assert third.provenance["targeted_anchor_ids"] == [target_anchor_id]


def test_small_unprovable_budget_leaves_no_mailbox_request(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bounded-article.txt"
    source.write_text("Evidence paragraph.", encoding="utf-8")
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )

    run = service.read(
        source,
        provider_selection=ProviderSelection.build(mode="agent_takeover"),
        token_budget=1_000,
        idempotency_key="small-provider-envelope",
    )

    assert run.execution_status is ExecutionStatus.FAILED
    assert any("budget" in warning.lower() for warning in run.warnings)
    with pytest.raises(ProviderContractError, match="no external-agent request"):
        service.pull_stage_request(run.run_id, ReadingStage.MAINLINE.value)


def test_chinese_stage_view_request_and_provider_share_hard_counter(
    tmp_path: Path,
) -> None:
    hard_budget = 20_000
    source = tmp_path / "chinese-article.txt"
    source.write_text(
        "\n\n".join(
            (
                "第一段提出文章试图解决的问题。",
                "第二段给出支持主张的事实与推理。",
                "第三段说明结论成立所依赖的条件。",
            )
        ),
        encoding="utf-8",
    )
    provider = PipelineProvider()
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(provider,),
    )

    run = service.read(
        source,
        provider_selection=ProviderSelection.build(primary="local"),
        token_budget=hard_budget,
        idempotency_key="chinese-hard-provider-envelope",
    )

    assert run.execution_status is ExecutionStatus.COMPLETED
    assert len(provider.requests) == len(ReadingStage)
    for request in provider.requests:
        assert request.estimated_serialized_tokens is not None
        assert request.estimated_serialized_tokens <= hard_budget
        provider_input = request.budget_manifest["provider_input"]
        assert provider_input["max_tokens"] <= hard_budget
        assert provider_input["receipts"][0]["counter_id"] == (
            "readwelt.utf8_bytes.max_1_token_per_byte.v1"
        )
        stage_view = request.evidence_packet["stage_view"]
        assert (
            stage_view["estimated_serialized_tokens"]
            <= (stage_view["hard_serialized_token_budget"])
        )
        assert stage_view["token_counter"]["mode"] == ("conservative_upper_bound")


def test_host_neutral_agent_turns_complete_without_an_internal_provider(
    tmp_path: Path,
) -> None:
    source = tmp_path / "article.txt"
    source.write_text("第一段提出主张。\n\n第二段给出限制。", encoding="utf-8")
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    agent = ExternalAgentAdapter(service)

    async def run_session() -> dict[str, Any]:
        turn = await agent.start(
            str(source),
            idempotency_key="host-neutral-agent",
        )
        for expected_stage in ReadingStage:
            assert turn["action"] == "generate_stage_candidate"
            assert turn["stage"] == expected_stage.value
            request = turn["request"]
            assert request["response_schema"]["type"] == "object"
            anchors = request["evidence_packet"]["anchors"]
            upstream = request["evidence_packet"]["upstream_claims"]
            claims = [
                {
                    "claim_id": f"{expected_stage.value}:host-neutral:{index}",
                    "text": f"{expected_stage.value} claim {index}",
                    "anchor_ids": [anchors[0]["anchor_id"]],
                    "decision": "accepted",
                    **(
                        {
                            "source_claim_ids": [upstream[0]["claim_id"]],
                        }
                        if expected_stage not in (ReadingStage.MAINLINE, ReadingStage.STRUCTURE)
                        else {}
                    ),
                    **(
                        {"provenance": {"interpretation_id": f"lens-{index}"}}
                        if expected_stage is ReadingStage.AUTHOR_MODEL
                        else {}
                    ),
                }
                for index in range(2 if expected_stage is ReadingStage.AUTHOR_MODEL else 1)
            ]
            turn = await agent.advance(
                turn["run_id"],
                {"claims": claims, "gaps": [], "warnings": []},
                agent_name="generic-agent",
                model="agent-model",
            )
        return turn

    completed = asyncio.run(run_session())

    assert completed["action"] == "completed"
    assert completed["execution_status"] == "completed"
    assert {item["artifact_type"] for item in completed["outputs"]} == {
        "reading_bundle",
        "reader_report_markdown",
    }


def test_host_neutral_agent_can_retry_a_rejected_candidate(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("文章提出一个可以验证的主张。", encoding="utf-8")
    service = ReadweltApplicationService(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    agent = ExternalAgentAdapter(service)

    async def reject_then_retry() -> tuple[dict[str, Any], dict[str, Any]]:
        turn = await agent.start(str(source), idempotency_key="agent-retry")
        rejected = await agent.advance(
            turn["run_id"],
            {"claims": [], "gaps": ["not-an-object"], "warnings": []},
            agent_name="generic-agent",
        )
        request = rejected["request"]
        accepted = await agent.advance(
            turn["run_id"],
            {
                "claims": [
                    {
                        "claim_id": "retry:claim:1",
                        "text": "文章提出一个主张。",
                        "anchor_ids": [request["evidence_packet"]["anchors"][0]["anchor_id"]],
                        "decision": "accepted",
                    }
                ],
                "gaps": [],
                "warnings": [],
            },
            agent_name="generic-agent",
        )
        return rejected, accepted

    rejected, accepted = asyncio.run(reject_then_retry())

    assert rejected["action"] == "generate_stage_candidate"
    assert rejected["stage"] == ReadingStage.MAINLINE.value
    assert "gaps entries must be objects" in rejected["validation_errors"][0]
    assert accepted["stage"] == ReadingStage.STRUCTURE.value
    rejected_candidates = tuple(
        path
        for path in (service.root / "runs" / rejected["run_id"] / "agent").rglob(
            "rejected/candidate-*.json"
        )
        if not path.name.endswith(".rejection.json")
    )
    assert len(rejected_candidates) == 1


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

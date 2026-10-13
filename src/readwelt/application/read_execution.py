"""Application-level orchestration for one complete six-stage reading run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from readwelt.article_graph import ArticleGraphBuildResult
from readwelt.domain import (
    ArtifactRef,
    EpistemicStatus,
    EvidencePacket,
    ExecutionStatus,
    ModelStatus,
    PublicationStatus,
    ReadingRun,
    ReadingStage,
    SourceDocumentSnapshot,
    StageArtifact,
)
from readwelt.projections import write_projection_artifacts
from readwelt.providers import (
    AgentInputRequired,
    CandidateProvider,
    ExternalAgentMailboxProvider,
    MinimumProviderEnvelopeExceeded,
    ProviderMode,
    ProviderResolver,
    ProviderSelection,
    StageRequest,
)
from readwelt.runner import DocumentRunner
from readwelt.semantic import (
    HybridRetriever,
    SemanticAtlas,
    SemanticEvidencePacket,
    build_stage_retrieval_plan,
)
from readwelt.stage_views import StageContext, StageView, StageViewProjector
from readwelt.stages import (
    AgentCandidateRejected,
    SixStageReadingEngine,
    StageInputIncomplete,
)
from readwelt.stages.request_factory import build_stage_request
from readwelt.storage import ArtifactStore, ProjectLayout
from readwelt.token_budget import DEFAULT_TOKEN_COUNTER

from .provider_request_validation import validate_final_provider_request
from .provider_runtime import AuditedCandidateProvider, ResolvingCandidateProvider
from .run_store import ApplicationRunStore
from .stage_query_bootstrap import StageQueryBootstrap, build_stage_query_bootstrap


class ReadExecutionHost(Protocol):
    _layout: ProjectLayout
    _artifacts: ArtifactStore
    _run_store: ApplicationRunStore
    _retriever: HybridRetriever
    _mailbox: ExternalAgentMailboxProvider
    _resolver: ProviderResolver
    _runner: DocumentRunner
    _stage_views: StageViewProjector

    def _prepare_snapshot(
        self,
        snapshot: SourceDocumentSnapshot,
    ) -> tuple[
        SemanticAtlas,
        ArtifactRef,
        ArticleGraphBuildResult,
        tuple[ArtifactRef, ...],
    ]: ...

    def _write_application_run(
        self,
        run: ReadingRun,
        *,
        selection: ProviderSelection,
        purpose: str,
        token_budget: int,
        hard_serialized_token_budget: int | None,
    ) -> None: ...

    def _emit(self, run_id: str, event_type: str, task: str) -> None: ...


async def execute_read(
    service: ReadExecutionHost,
    snapshot: SourceDocumentSnapshot,
    selection: ProviderSelection,
    *,
    run_id: str,
    purpose: str,
    token_budget: int | None,
    hard_serialized_token_budget: int | None,
    created_at: datetime,
) -> ReadingRun:
    atlas, atlas_ref, graph_build, graph_refs = service._prepare_snapshot(snapshot)
    effective_budget = (
        token_budget
        if token_budget is not None
        else max(
            256,
            sum(segment.statistics.token_count for segment in atlas.segments),
        )
    )
    base_plan = build_stage_retrieval_plan(
        ReadingStage.MAINLINE,
        purpose=purpose,
        token_budget=effective_budget,
    )
    semantic_packet = service._retriever.retrieve(atlas, base_plan)
    stage_packets: dict[ReadingStage, SemanticEvidencePacket] = {
        ReadingStage.MAINLINE: semantic_packet,
    }
    stage_evidence_packets: dict[ReadingStage, EvidencePacket] = {}
    stage_view_refs: dict[ReadingStage, ArtifactRef] = {}
    stage_query_bootstraps: dict[ReadingStage, StageQueryBootstrap] = {}
    evidence = cast(EvidencePacket, semantic_packet.to_stage_packet(run_id))
    stage_evidence_packets[ReadingStage.MAINLINE] = evidence
    initial_artifacts = service._run_store.load_stage_artifacts(run_id)
    if selection.mode is ProviderMode.AGENT_TAKEOVER:
        selected_provider: CandidateProvider = service._mailbox
    else:
        selected_provider = ResolvingCandidateProvider(service._resolver, selection)
    provider: CandidateProvider = AuditedCandidateProvider(
        selected_provider,
        service._run_store,
    )
    provider_token_counter = getattr(
        provider,
        "input_token_counter",
        DEFAULT_TOKEN_COUNTER,
    )
    engine = SixStageReadingEngine(
        provider,
        retry_invalid_candidates=selection.mode is ProviderMode.AGENT_TAKEOVER,
    )

    def evidence_for_stage(
        stage: ReadingStage,
        artifacts: Sequence[StageArtifact],
    ) -> EvidencePacket:
        if stage is ReadingStage.MAINLINE and not artifacts:
            return evidence
        if stage is ReadingStage.TRANSFER and artifacts:
            upstream_claims = artifacts[-1].accepted_claims
        else:
            upstream_claims = tuple(
                claim for artifact in artifacts for claim in artifact.accepted_claims
            )
        plan = build_stage_retrieval_plan(
            stage,
            purpose=purpose,
            token_budget=effective_budget,
            upstream_claims=upstream_claims,
        )
        packet = service._retriever.retrieve(atlas, plan)
        stage_packets[stage] = packet
        stage_evidence = cast(EvidencePacket, packet.to_stage_packet(run_id))
        stage_evidence_packets[stage] = stage_evidence
        return stage_evidence

    def stage_view_for_stage(
        stage: ReadingStage,
        artifacts: Sequence[StageArtifact],
    ) -> StageView:
        locator_packet = stage_packets.get(stage)
        upstream_claims = (
            artifacts[-1].accepted_claims
            if stage is ReadingStage.TRANSFER and artifacts
            else tuple(claim for artifact in artifacts for claim in artifact.accepted_claims)
        )
        navigation = service._run_store.load_stage_navigation(run_id, stage)
        candidate_ready = (
            selection.mode is ProviderMode.AGENT_TAKEOVER
            and service._mailbox.has_candidate(run_id, stage.value)
        )
        if navigation is None:
            input_continuation = None
            targeted_anchor_ids: tuple[str, ...] = ()
            rescue_level = "section"
        else:
            input_continuation = (
                navigation.input_continuation
                if candidate_ready or navigation.next_continuation is None
                else navigation.next_continuation
            )
            targeted_anchor_ids = navigation.targeted_anchor_ids
            rescue_level = navigation.rescue_level
        stage_evidence = stage_evidence_packets.get(stage, evidence)
        bootstrap = None
        query_text = " ".join(
            (
                *stage_evidence.retrieval_queries,
                *(anchor.exact_text for anchor in stage_evidence.anchors[:2]),
            )
        ).strip()
        if query_text:
            bootstrap = build_stage_query_bootstrap(
                graph_build,
                stage,
                document_id=snapshot.document_id,
                query_text=query_text,
            )
            stage_query_bootstraps[stage] = bootstrap
            service._run_store.append_query_receipt(run_id, stage, bootstrap.page.receipt)
        view_hard_budget = (
            navigation.stage_view_hard_serialized_token_budget
            if navigation is not None
            and navigation.stage_view_hard_serialized_token_budget is not None
            else stage_view_budget(hard_serialized_token_budget)
        )
        view_token_budget = (
            navigation.stage_view_token_budget
            if navigation is not None and navigation.stage_view_token_budget is not None
            else effective_budget
        )
        for attempt in range(8):
            view = service._stage_views.project(
                graph_build,
                StageContext(
                    stage=stage,
                    task_intent=purpose,
                    token_budget=view_token_budget,
                    hard_serialized_token_budget=view_hard_budget,
                    upstream_claim_ids=tuple(claim.claim_id for claim in upstream_claims),
                    unresolved_gap_ids=tuple(
                        gap.gap_id
                        for artifact in artifacts
                        for gap in artifact.gaps
                        if not gap.resolved
                    ),
                    allowed_anchor_ids=(
                        tuple(anchor.anchor_id for anchor in locator_packet.anchors)
                        if locator_packet is not None
                        else None
                    ),
                    critical_range_ids=(
                        bootstrap.critical_range_ids if bootstrap is not None else ()
                    ),
                    critical_element_ids=(
                        bootstrap.critical_element_ids if bootstrap is not None else ()
                    ),
                    targeted_anchor_ids=targeted_anchor_ids,
                    rescue_level=cast(Any, rescue_level),
                    continuation=input_continuation,
                ),
                upstream_claims=upstream_claims,
                locator_packet=locator_packet,
                external_evidence=stage_evidence.external_evidence,
            )
            if hard_serialized_token_budget is None or view_hard_budget is None:
                break
            try:
                # Probe the real provider profile and current response schema
                # before persisting this page's continuation frontier.
                build_stage_request(
                    provider_name=provider.name,
                    provider_kind=provider.kind.value,
                    provider_model=provider.model,
                    token_counter=provider_token_counter,
                    stage=stage,
                    snapshot=snapshot,
                    evidence=stage_evidence,
                    artifacts=artifacts,
                    upstream_claims=upstream_claims,
                    stage_view=view,
                    request_provenance={
                        "stage_page_index": (
                            navigation.page_index if navigation is not None else 0
                        ),
                        "stage_view_digest": view.content_digest,
                        "input_continuation_digest": (
                            input_continuation.content_digest
                            if input_continuation is not None
                            else None
                        ),
                        "next_continuation_digest": (
                            view.continuation.content_digest
                            if view.continuation is not None
                            else None
                        ),
                        "previous_request_digest": (
                            navigation.latest_request_digest if navigation is not None else None
                        ),
                        "rescue_level": rescue_level,
                        "targeted_anchor_ids": list(targeted_anchor_ids),
                    },
                    hard_serialized_token_budget=hard_serialized_token_budget,
                )
                break
            except MinimumProviderEnvelopeExceeded as error:
                if attempt == 7:
                    raise
                overage = error.actual_tokens - error.hard_budget
                required_reduction = overage + 8
                if view.estimated_tokens <= required_reduction:
                    raise
                next_budget = view.estimated_tokens - required_reduction
                if next_budget >= view_token_budget:
                    raise
                view_token_budget = next_budget
        service._run_store.save_stage_navigation(
            run_id,
            stage,
            input_continuation=input_continuation,
            view=view,
            targeted_anchor_ids=targeted_anchor_ids,
            rescue_level=rescue_level,
        )
        stage_view_refs[stage] = service._artifacts.put_json(
            view,
            artifact_type="stage_view",
            schema_version=view.schema_version,
        )
        return view

    def request_provenance_for_stage(
        stage: ReadingStage,
        stage_view: StageView | None,
    ) -> Mapping[str, Any]:
        navigation = service._run_store.load_stage_navigation(run_id, stage)
        if navigation is None:
            return {}
        query_receipts = service._run_store.load_query_receipts(run_id, stage)
        return {
            "stage_page_index": navigation.page_index,
            "stage_view_digest": (stage_view.content_digest if stage_view is not None else None),
            "input_continuation_digest": (
                navigation.input_continuation.content_digest
                if navigation.input_continuation is not None
                else None
            ),
            "next_continuation_digest": (
                navigation.next_continuation.content_digest
                if navigation.next_continuation is not None
                else None
            ),
            "previous_request_digest": navigation.latest_request_digest,
            "rescue_level": navigation.rescue_level,
            "targeted_anchor_ids": list(navigation.targeted_anchor_ids),
            "articlegraph_query_receipt_ids": [receipt.receipt_id for receipt in query_receipts],
            "articlegraph_query_primary": stage in stage_query_bootstraps,
        }

    def validate_final_request(
        request: StageRequest,
        stage_view: StageView | None,
    ) -> None:
        if stage_view is None:
            raise ValueError("final provider request requires a StageView")
        validate_final_provider_request(request, stage_view, graph_build)

    source_ref = service._artifacts.put_json(snapshot, artifact_type="source_snapshot")
    manifest_path = service._layout.run_manifest(run_id)
    if manifest_path.exists():
        prior = service._runner.get(run_id)
        running = replace(
            prior,
            execution_status=ExecutionStatus.RUNNING,
            current_task="six_stage_reading",
            completed_at=None,
        )
    else:
        running = ReadingRun(
            run_id=run_id,
            schema_version="1",
            snapshot_id=snapshot.snapshot_id,
            execution_status=ExecutionStatus.RUNNING,
            epistemic_status=EpistemicStatus.UNDERDETERMINED,
            model_status=ModelStatus.READY,
            publication_status=PublicationStatus.WITHHELD,
            current_task="six_stage_reading",
            artifacts=(source_ref, atlas_ref, *graph_refs),
            warnings=(),
            created_at=created_at,
        )
    service._write_application_run(
        running,
        selection=selection,
        purpose=purpose,
        token_budget=effective_budget,
        hard_serialized_token_budget=hard_serialized_token_budget,
    )
    service._emit(run_id, "run_started", "six_stage_reading")

    async def persist_stage(artifact: StageArtifact) -> None:
        reference = service._run_store.append_stage_artifact(run_id, artifact)
        service._emit(
            run_id,
            "stage_settled" if artifact.fully_settled else "stage_input_incomplete",
            artifact.stage.value,
        )
        if reference.status.value != "completed":
            raise ValueError("settled stage artifact was not completed")

    try:
        bundle = await engine.run(
            snapshot,
            evidence,
            initial_artifacts=initial_artifacts,
            artifact_sink=persist_stage,
            evidence_factory=evidence_for_stage,
            stage_view_factory=stage_view_for_stage,
            request_provenance_factory=request_provenance_for_stage,
            request_validator=validate_final_request,
            hard_serialized_token_budget=hard_serialized_token_budget,
        )
    except AgentCandidateRejected as exc:
        service._mailbox.reject(run_id, exc.stage, exc.reason)
        persisted = service._runner.get(run_id)
        awaiting_retry = replace(
            persisted,
            artifacts=tuple(dict.fromkeys((*persisted.artifacts, *stage_view_refs.values()))),
            execution_status=ExecutionStatus.PENDING,
            model_status=ModelStatus.READY,
            current_task=f"awaiting_agent:{exc.stage}",
            warnings=(f"{exc.stage}: candidate rejected: {exc.reason}",),
            completed_at=None,
        )
        service._write_application_run(
            awaiting_retry,
            selection=selection,
            purpose=purpose,
            token_budget=effective_budget,
            hard_serialized_token_budget=hard_serialized_token_budget,
        )
        service._emit(run_id, "agent_candidate_rejected", exc.stage)
        return awaiting_retry
    except StageInputIncomplete as exc:
        if selection.mode is ProviderMode.AGENT_TAKEOVER:
            service._mailbox.accept_page(run_id, exc.artifact.stage.value)
        persisted = service._runner.get(run_id)
        state = exc.artifact.input_state
        assert state is not None
        awaiting_continuation = replace(
            persisted,
            artifacts=tuple(dict.fromkeys((*persisted.artifacts, *stage_view_refs.values()))),
            execution_status=ExecutionStatus.PENDING,
            epistemic_status=EpistemicStatus.UNDERDETERMINED,
            publication_status=PublicationStatus.WITHHELD,
            current_task=(f"stage_input_{state.status.value}:{exc.artifact.stage.value}"),
            warnings=(
                f"{exc.artifact.stage.value}: bounded input is "
                f"{state.status.value}; resume traversal",
            ),
            completed_at=None,
        )
        service._write_application_run(
            awaiting_continuation,
            selection=selection,
            purpose=purpose,
            token_budget=effective_budget,
            hard_serialized_token_budget=hard_serialized_token_budget,
        )
        service._emit(
            run_id,
            "stage_input_incomplete",
            exc.artifact.stage.value,
        )
        return awaiting_continuation
    except AgentInputRequired as exc:
        persisted = service._runner.get(run_id)
        awaiting = replace(
            persisted,
            artifacts=tuple(dict.fromkeys((*persisted.artifacts, *stage_view_refs.values()))),
            execution_status=ExecutionStatus.PENDING,
            current_task=f"awaiting_agent:{exc.request.stage}",
        )
        service._write_application_run(
            awaiting,
            selection=selection,
            purpose=purpose,
            token_budget=effective_budget,
            hard_serialized_token_budget=hard_serialized_token_budget,
        )
        service._emit(run_id, "agent_input_required", exc.request.stage)
        return awaiting

    projections = write_projection_artifacts(bundle, service._artifacts)
    failed = bundle.execution_status is ExecutionStatus.FAILED
    persisted = service._runner.get(run_id)
    completed = replace(
        persisted,
        execution_status=bundle.execution_status,
        epistemic_status=bundle.epistemic_status,
        model_status=ModelStatus.FAILED if failed else ModelStatus.READY,
        publication_status=(PublicationStatus.WITHHELD if failed else PublicationStatus.INTERNAL),
        current_task="failed" if failed else "completed",
        artifacts=(
            *persisted.artifacts,
            *(
                reference
                for reference in stage_view_refs.values()
                if reference not in persisted.artifacts
            ),
            projections.bundle,
            projections.report,
        ),
        warnings=((bundle.failure,) if bundle.failure else ()),
        completed_at=None if failed else datetime.now(UTC),
        content_digest=projections.bundle.content_digest,
    )
    service._write_application_run(
        completed,
        selection=selection,
        purpose=purpose,
        token_budget=effective_budget,
        hard_serialized_token_budget=hard_serialized_token_budget,
    )
    service._emit(
        run_id,
        "run_failed" if failed else "run_completed",
        completed.current_task,
    )
    return completed


def stage_view_budget(
    hard_request_budget: int | None,
) -> int | None:
    if hard_request_budget is None:
        return None
    return min(hard_request_budget, max(1_000, hard_request_budget * 2 // 5))


def request_page_items(value: object) -> tuple[Any, ...]:
    items = value.get("items", ()) if isinstance(value, Mapping) else value
    if not isinstance(items, (list, tuple)):
        return ()
    return tuple(items)

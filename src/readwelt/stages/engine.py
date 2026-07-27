"""Deterministic gates around model-provided six-stage candidates."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from readwelt.domain.documents import SourceDocumentSnapshot
from readwelt.domain.reading import (
    EvidencePacket,
    ReadingBundle,
    ReadingClaim,
    ReadingGap,
    ReadingStage,
    SourceCitation,
    StageArtifact,
)
from readwelt.domain.status import EpistemicStatus, ExecutionStatus
from readwelt.providers.contracts import AgentInputRequired, StageCandidate, StageRequest
from readwelt.providers.model_protocol import CandidateProvider
from readwelt.stage_views import StageView, validate_stage_view
from readwelt.token_budget import DEFAULT_TOKEN_COUNTER

from .ai_boundary import (
    stage_view_graph_object_ids as _stage_view_graph_object_ids,
)
from .ai_boundary import (
    stage_view_source_citations as _stage_view_source_citations,
)
from .ai_boundary import (
    validate_stage_claim_boundary as _validate_stage_claim_boundary,
)
from .candidate_settlement import bind_stage_input as _bind_stage_input
from .candidate_settlement import parse_claim as _parse_claim_impl
from .candidate_settlement import parse_gap as _parse_gap_impl
from .candidate_settlement import settle_candidate as _settle_candidate_impl
from .policies import (
    RESPONSE_SCHEMA as _RESPONSE_SCHEMA,
)
from .policies import (
    STAGES as _STAGES,
)
from .request_factory import build_stage_request as _build_stage_request
from .stage_results import add_entry_gaps as _add_entry_gaps_impl
from .stage_results import build_bundle as _build_bundle
from .stage_results import gap_gate as _gap_gate_impl
from .stage_results import mediate_author_model as _mediate_author_model_impl


class AgentCandidateRejected(ValueError):
    """A retryable external-agent candidate failed deterministic settlement."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


class StageInputIncomplete(RuntimeError):
    """A valid page candidate cannot settle a stage before traversal completes."""

    def __init__(self, artifact: StageArtifact) -> None:
        state = artifact.input_state
        if state is None or artifact.fully_settled:
            raise ValueError("StageInputIncomplete requires an incomplete artifact")
        super().__init__(
            f"{artifact.stage.value} input is {state.status.value}; bounded traversal must resume"
        )
        self.artifact = artifact


StageArtifactSink = Callable[[StageArtifact], Awaitable[None]]
StageEvidenceFactory = Callable[
    [ReadingStage, Sequence[StageArtifact]],
    EvidencePacket,
]
StageViewFactory = Callable[
    [ReadingStage, Sequence[StageArtifact]],
    "StageView",
]
StageRequestProvenanceFactory = Callable[
    [ReadingStage, "StageView | None"],
    Mapping[str, Any],
]
StageRequestValidator = Callable[
    [StageRequest, "StageView | None"],
    None,
]


class SixStageReadingEngine:
    """Execute the fixed stage order and freeze every accepted result."""

    def __init__(
        self,
        provider: CandidateProvider,
        *,
        retry_invalid_candidates: bool = False,
    ) -> None:
        self._provider = provider
        self._retry_invalid_candidates = retry_invalid_candidates

    async def run(
        self,
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
        *,
        initial_artifacts: Sequence[StageArtifact] = (),
        artifact_sink: StageArtifactSink | None = None,
        evidence_factory: StageEvidenceFactory | None = None,
        stage_view_factory: StageViewFactory | None = None,
        request_provenance_factory: StageRequestProvenanceFactory | None = None,
        request_validator: StageRequestValidator | None = None,
        hard_serialized_token_budget: int | None = None,
    ) -> ReadingBundle:
        if evidence.run_id == "":
            raise ValueError("evidence run_id is required")
        anchor_ids = self._validate_evidence(snapshot, evidence)
        self._validate_initial_artifacts(evidence.run_id, initial_artifacts)
        artifacts = list(initial_artifacts)
        transitions: list[str] = ["created", "entry_check"]
        transitions.extend(f"resumed:{artifact.stage.value}" for artifact in artifacts)
        known_claim_ids = {claim.claim_id for artifact in artifacts for claim in artifact.claims}

        for stage in _STAGES[len(artifacts) :]:
            transitions.append(stage.value)
            eligible = self._eligible_upstream_claims(stage, artifacts)
            try:
                stage_evidence = (
                    evidence_factory(stage, artifacts) if evidence_factory is not None else evidence
                )
                if stage_evidence.run_id != evidence.run_id:
                    raise ValueError("stage evidence belongs to a different run")
                if stage_evidence.stage is not None and stage_evidence.stage is not stage:
                    raise ValueError("stage evidence belongs to a different reading stage")
                anchor_ids = self._validate_evidence(snapshot, stage_evidence)
                stage_view = (
                    stage_view_factory(stage, artifacts) if stage_view_factory is not None else None
                )
                if stage_view is not None:
                    validate_stage_view(
                        stage_view,
                        snapshot_id=snapshot.snapshot_id,
                        stage=stage,
                        allowed_anchor_ids=anchor_ids,
                    )
                request = self._build_request(
                    stage=stage,
                    snapshot=snapshot,
                    evidence=stage_evidence,
                    artifacts=artifacts,
                    upstream_claims=eligible,
                    stage_view=stage_view,
                    request_provenance=(
                        request_provenance_factory(stage, stage_view)
                        if request_provenance_factory is not None
                        else {}
                    ),
                    hard_serialized_token_budget=hard_serialized_token_budget,
                )
                if request_validator is not None:
                    request_validator(request, stage_view)
                candidate = await self._provider.generate(request, _RESPONSE_SCHEMA)
                presented_anchor_ids = _request_presented_anchor_ids(request)
                try:
                    artifact = self._settle_candidate(
                        candidate=candidate,
                        stage=stage,
                        run_id=evidence.run_id,
                        input_artifacts=artifacts,
                        allowed_anchor_ids=presented_anchor_ids,
                        allowed_source_claim_ids={claim.claim_id for claim in eligible},
                        allowed_graph_object_ids=_stage_view_graph_object_ids(stage_view),
                        allowed_source_citations=_stage_view_source_citations(
                            stage_view,
                            presented_anchor_ids=presented_anchor_ids,
                        ),
                        known_claim_ids=known_claim_ids,
                    )
                except ValueError as exc:
                    if self._retry_invalid_candidates:
                        raise AgentCandidateRejected(stage.value, str(exc)) from exc
                    raise
                if stage is ReadingStage.MAINLINE:
                    artifact = self._add_entry_gaps(artifact, snapshot, stage_evidence)
                artifact = _bind_stage_input(artifact, stage_view)
                if not artifact.fully_settled:
                    if artifact_sink is not None:
                        await artifact_sink(artifact)
                    raise StageInputIncomplete(artifact)
                if stage is ReadingStage.STRUCTURE:
                    artifacts.append(artifact)
                    if artifact_sink is not None:
                        await artifact_sink(artifact)
                    known_claim_ids.update(claim.claim_id for claim in artifact.claims)
                    gap_state = self._gap_gate(artifacts)
                    transitions.append(f"gap_gate:{gap_state.value}")
                    continue
                if stage is ReadingStage.AUTHOR_MODEL:
                    transitions.append("mediation")
                    artifact = self._mediate_author_model(artifact)
                artifacts.append(artifact)
                if artifact_sink is not None:
                    await artifact_sink(artifact)
                known_claim_ids.update(claim.claim_id for claim in artifact.claims)
            except AgentInputRequired:
                raise
            except AgentCandidateRejected:
                raise
            except StageInputIncomplete:
                raise
            except Exception as exc:
                transitions.append("failed")
                return self._bundle(
                    run_id=evidence.run_id,
                    snapshot_id=snapshot.snapshot_id,
                    artifacts=artifacts,
                    transitions=transitions,
                    execution_status=ExecutionStatus.FAILED,
                    failure=f"{stage.value}: {type(exc).__name__}: {exc}",
                )

        transitions.extend(("final_ledger", "completed"))
        return self._bundle(
            run_id=evidence.run_id,
            snapshot_id=snapshot.snapshot_id,
            artifacts=artifacts,
            transitions=transitions,
            execution_status=ExecutionStatus.COMPLETED,
        )

    @staticmethod
    def _validate_initial_artifacts(
        run_id: str,
        artifacts: Sequence[StageArtifact],
    ) -> None:
        if len(artifacts) > len(_STAGES):
            raise ValueError("too many initial stage artifacts")
        previous_ids: list[str] = []
        known_claim_ids: set[str] = set()
        for expected_stage, artifact in zip(_STAGES, artifacts, strict=False):
            if not artifact.fully_settled:
                raise ValueError("initial artifacts must contain only fully settled stages")
            if artifact.run_id != run_id:
                raise ValueError("initial artifact belongs to a different run")
            if artifact.stage is not expected_stage:
                raise ValueError("initial artifacts must form the fixed stage prefix")
            if artifact.input_artifact_ids != tuple(previous_ids):
                raise ValueError("initial artifact lineage does not match its prefix")
            claim_ids = {claim.claim_id for claim in artifact.claims}
            if known_claim_ids & claim_ids:
                raise ValueError("initial artifacts contain duplicate claim ids")
            for claim in artifact.claims:
                _validate_stage_claim_boundary(claim)
            known_claim_ids.update(claim_ids)
            previous_ids.append(artifact.artifact_id)

    @staticmethod
    def _validate_evidence(
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
    ) -> frozenset[str]:
        section_anchors = tuple(section.anchor for section in snapshot.sections)
        all_anchors = (*section_anchors, *evidence.anchors)
        if any(anchor.snapshot_id != snapshot.snapshot_id for anchor in all_anchors):
            raise ValueError("all evidence anchors must belong to the source snapshot")
        source_anchor_ids = frozenset(anchor.anchor_id for anchor in section_anchors)
        if any(anchor.anchor_id not in source_anchor_ids for anchor in evidence.anchors):
            raise ValueError("evidence anchor does not belong to the source snapshot")
        return frozenset(anchor.anchor_id for anchor in evidence.anchors)

    @staticmethod
    def _eligible_upstream_claims(
        stage: ReadingStage,
        artifacts: Sequence[StageArtifact],
    ) -> tuple[ReadingClaim, ...]:
        if not artifacts:
            return ()
        if stage is ReadingStage.TRANSFER:
            boundary = artifacts[-1]
            if boundary.stage is not ReadingStage.BOUNDARIES:
                raise ValueError("stage 6 requires the settled stage 5 artifact")
            return boundary.accepted_claims
        return tuple(claim for artifact in artifacts for claim in artifact.accepted_claims)

    def _build_request(
        self,
        *,
        stage: ReadingStage,
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
        artifacts: Sequence[StageArtifact],
        upstream_claims: Sequence[ReadingClaim],
        stage_view: StageView | None = None,
        request_provenance: Mapping[str, Any] | None = None,
        hard_serialized_token_budget: int | None = None,
    ) -> StageRequest:
        return _build_stage_request(
            provider_name=self._provider.name,
            provider_kind=self._provider.kind.value,
            provider_model=self._provider.model,
            token_counter=getattr(
                self._provider,
                "input_token_counter",
                DEFAULT_TOKEN_COUNTER,
            ),
            stage=stage,
            snapshot=snapshot,
            evidence=evidence,
            artifacts=artifacts,
            upstream_claims=upstream_claims,
            stage_view=stage_view,
            request_provenance=request_provenance,
            hard_serialized_token_budget=hard_serialized_token_budget,
        )

    def _settle_candidate(
        self,
        *,
        candidate: StageCandidate,
        stage: ReadingStage,
        run_id: str,
        input_artifacts: Sequence[StageArtifact],
        allowed_anchor_ids: frozenset[str],
        allowed_source_claim_ids: set[str],
        allowed_graph_object_ids: frozenset[str],
        allowed_source_citations: frozenset[SourceCitation] | None = None,
        known_claim_ids: set[str],
    ) -> StageArtifact:
        return _settle_candidate_impl(
            candidate=candidate,
            stage=stage,
            run_id=run_id,
            input_artifacts=input_artifacts,
            allowed_anchor_ids=allowed_anchor_ids,
            allowed_source_claim_ids=allowed_source_claim_ids,
            allowed_graph_object_ids=allowed_graph_object_ids,
            allowed_source_citations=allowed_source_citations,
            known_claim_ids=known_claim_ids,
        )

    @staticmethod
    def _parse_claim(
        value: Mapping[str, Any],
        *,
        stage: ReadingStage,
        allowed_anchor_ids: frozenset[str],
        allowed_source_claim_ids: set[str],
        allowed_graph_object_ids: frozenset[str],
        allowed_source_citations: frozenset[SourceCitation] | None = None,
        known_claim_ids: set[str],
        provider: str,
    ) -> ReadingClaim:
        return _parse_claim_impl(
            value,
            stage=stage,
            allowed_anchor_ids=allowed_anchor_ids,
            allowed_source_claim_ids=allowed_source_claim_ids,
            allowed_graph_object_ids=allowed_graph_object_ids,
            allowed_source_citations=allowed_source_citations,
            known_claim_ids=known_claim_ids,
            provider=provider,
        )

    @staticmethod
    def _parse_gap(value: Mapping[str, Any], stage: ReadingStage) -> ReadingGap:
        return _parse_gap_impl(value, stage)

    @staticmethod
    def _add_entry_gaps(
        artifact: StageArtifact,
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
    ) -> StageArtifact:
        return _add_entry_gaps_impl(artifact, snapshot, evidence)

    @staticmethod
    def _gap_gate(artifacts: Sequence[StageArtifact]) -> EpistemicStatus:
        return _gap_gate_impl(artifacts)

    @staticmethod
    def _mediate_author_model(artifact: StageArtifact) -> StageArtifact:
        return _mediate_author_model_impl(artifact)

    @staticmethod
    def _bundle(
        *,
        run_id: str,
        snapshot_id: str,
        artifacts: Sequence[StageArtifact],
        transitions: Sequence[str],
        execution_status: ExecutionStatus,
        failure: str | None = None,
    ) -> ReadingBundle:
        return _build_bundle(
            run_id=run_id,
            snapshot_id=snapshot_id,
            artifacts=artifacts,
            transitions=transitions,
            execution_status=execution_status,
            failure=failure,
        )


def _request_presented_anchor_ids(request: StageRequest) -> frozenset[str]:
    raw = request.evidence_packet.get("anchors", ())
    items = raw.get("items", ()) if isinstance(raw, Mapping) else raw
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return frozenset()
    return frozenset(
        str(item["anchor_id"])
        for item in items
        if isinstance(item, Mapping) and isinstance(item.get("anchor_id"), str)
    )

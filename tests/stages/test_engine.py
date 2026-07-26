from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from readwelt.domain import (
    DocumentSection,
    EpistemicStatus,
    EvidencePacket,
    ExecutionStatus,
    ReadingStage,
    SourceDocumentSnapshot,
    SpanAnchor,
)
from readwelt.providers import ProviderKind, StageCandidate, StageRequest
from readwelt.stages import SixStageReadingEngine


class FakeCandidateProvider:
    def __init__(
        self,
        anchor_id: str,
        *,
        critical_gap_at: ReadingStage | None = None,
        bad_anchor_at: ReadingStage | None = None,
        illegal_stage6_source: bool = False,
        empty_stage6_source: bool = False,
    ) -> None:
        self.anchor_id = anchor_id
        self.critical_gap_at = critical_gap_at
        self.bad_anchor_at = bad_anchor_at
        self.illegal_stage6_source = illegal_stage6_source
        self.empty_stage6_source = empty_stage6_source
        self.requests: list[StageRequest] = []

    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.LOCAL

    @property
    def name(self) -> str:
        return "fake"

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
        anchor_id = "anchor:does-not-exist" if stage is self.bad_anchor_at else self.anchor_id
        claim_count = 2 if stage is ReadingStage.AUTHOR_MODEL else 1
        claims: list[dict[str, Any]] = [
            {
                "claim_id": f"{stage.value}:claim:{index}",
                "text": f"{stage.value} claim {index}",
                "anchor_ids": [anchor_id],
                "decision": "accepted",
                **(
                    {"provenance": {"interpretation_id": f"lens-{index}"}}
                    if stage is ReadingStage.AUTHOR_MODEL
                    else {}
                ),
            }
            for index in range(claim_count)
        ]
        if stage is ReadingStage.TRANSFER and self.empty_stage6_source:
            pass
        elif stage is ReadingStage.TRANSFER and self.illegal_stage6_source:
            claims[0]["source_claim_ids"] = ["stage_1_mainline:claim:0"]
        elif stage not in (ReadingStage.MAINLINE, ReadingStage.STRUCTURE):
            upstream = request.evidence_packet["upstream_claims"]
            for claim in claims:
                claim["source_claim_ids"] = [upstream[0]["claim_id"]]
        gaps: list[dict[str, Any]] = []
        if stage is self.critical_gap_at:
            gaps.append(
                {
                    "kind": "reasoning_discontinuity",
                    "description": "the article does not establish this step",
                    "critical": True,
                }
            )
        return StageCandidate(
            schema_version="1",
            run_id=request.run_id,
            stage=request.stage,
            candidate={"claims": claims, "gaps": gaps, "warnings": []},
            provider=self.name,
            model=self.model,
        )


def _snapshot_and_packet() -> tuple[SourceDocumentSnapshot, EvidencePacket, SpanAnchor]:
    text = "A claim supported by the article."
    anchor = SpanAnchor.create(
        snapshot_id="snapshot-1",
        section_id="section-1",
        text=text,
        start_offset=0,
        end_offset=len(text),
    )
    snapshot = SourceDocumentSnapshot(
        snapshot_id="snapshot-1",
        document_id="document-1",
        schema_version="1",
        source_kind="txt",
        source_locator="article.txt",
        content_digest="sha256:" + "a" * 64,
        captured_at=datetime.now(UTC),
        language="en",
        normalized_text_ref="objects/source.txt",
        sections=(
            DocumentSection(
                section_id="section-1",
                title=None,
                start_offset=0,
                end_offset=len(text),
                anchor=anchor,
            ),
        ),
        title="Article",
    )
    packet = EvidencePacket(
        run_id="run-1",
        anchors=(anchor,),
        retrieval_queries=("main claim",),
        external_evidence=("external biography must not enter early stages",),
        token_budget=2048,
    )
    return snapshot, packet, anchor


def test_executes_fixed_order_and_enforces_evidence_boundaries() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    provider = FakeCandidateProvider(anchor.anchor_id)

    bundle = asyncio.run(SixStageReadingEngine(provider).run(snapshot, packet))

    assert bundle.execution_status is ExecutionStatus.COMPLETED
    assert [request.stage for request in provider.requests] == [
        stage.value for stage in ReadingStage
    ]
    for request in provider.requests[:2]:
        assert request.capabilities == ()
        assert request.evidence_packet["external_evidence_allowed"] is False
        assert request.evidence_packet["external_evidence"] == []
    assert provider.requests[2].evidence_packet["external_evidence"] == [
        "external biography must not enter early stages"
    ]
    stage6_inputs = provider.requests[-1].evidence_packet["upstream_claims"]
    assert {item["stage"] for item in stage6_inputs} == {ReadingStage.BOUNDARIES.value}
    assert provider.requests[0].evidence_packet["stage_policy"]["goal"]
    assert len(bundle.artifacts) == 6
    assert "mediation" in bundle.transitions
    assert all(
        claim.anchor_ids == (anchor.anchor_id,)
        for line in bundle.artifacts
        for claim in line.claims
    )


def test_stage_evidence_factory_tracks_settled_artifact_prefix() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    provider = FakeCandidateProvider(anchor.anchor_id)
    observed_prefixes: list[int] = []

    def evidence_factory(
        stage: ReadingStage,
        artifacts: tuple[object, ...] | list[object],
    ) -> EvidencePacket:
        observed_prefixes.append(len(artifacts))
        return replace(
            packet,
            stage=stage,
            retrieval_queries=(f"query:{stage.value}",),
            retrieval_backend="hybrid-rrf-v1",
        )

    bundle = asyncio.run(
        SixStageReadingEngine(provider).run(
            snapshot,
            packet,
            evidence_factory=evidence_factory,
        )
    )

    assert bundle.execution_status is ExecutionStatus.COMPLETED
    assert observed_prefixes == [0, 1, 2, 3, 4, 5]
    assert [request.evidence_packet["retrieval_queries"][0] for request in provider.requests] == [
        f"query:{stage.value}" for stage in ReadingStage
    ]
    assert all(
        request.evidence_packet["retrieval_backend"] == "hybrid-rrf-v1"
        for request in provider.requests
    )


def test_claim_cannot_cite_snapshot_anchor_omitted_from_stage_packet() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    provider = FakeCandidateProvider(anchor.anchor_id)
    omitted_packet = replace(
        packet,
        anchors=(),
        omitted_anchor_ids=(anchor.anchor_id,),
        coverage_complete=False,
    )

    bundle = asyncio.run(SixStageReadingEngine(provider).run(snapshot, omitted_packet))

    assert bundle.execution_status is ExecutionStatus.FAILED
    assert bundle.failure is not None
    assert "outside the admitted evidence packet" in bundle.failure


def test_critical_internal_gap_is_preserved_as_underdetermined() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    provider = FakeCandidateProvider(
        anchor.anchor_id,
        critical_gap_at=ReadingStage.STRUCTURE,
    )

    bundle = asyncio.run(SixStageReadingEngine(provider).run(snapshot, packet))

    assert bundle.execution_status is ExecutionStatus.COMPLETED
    assert bundle.epistemic_status is EpistemicStatus.UNDERDETERMINED
    assert "gap_gate:underdetermined" in bundle.transitions
    gap = bundle.artifacts[1].gaps[0]
    assert gap.kind == "reasoning_discontinuity"
    assert gap.resolved is False


def test_unknown_anchor_freezes_a_failed_bundle_without_later_stages() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    provider = FakeCandidateProvider(
        anchor.anchor_id,
        bad_anchor_at=ReadingStage.STRUCTURE,
    )

    bundle = asyncio.run(SixStageReadingEngine(provider).run(snapshot, packet))

    assert bundle.execution_status is ExecutionStatus.FAILED
    assert bundle.epistemic_status is EpistemicStatus.INVALID
    assert bundle.failure is not None
    assert "outside the admitted evidence packet" in bundle.failure
    assert len(bundle.artifacts) == 1
    assert [request.stage for request in provider.requests] == [
        ReadingStage.MAINLINE.value,
        ReadingStage.STRUCTURE.value,
    ]


def test_stage6_rejects_a_claim_sourced_directly_from_stage1() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    provider = FakeCandidateProvider(anchor.anchor_id, illegal_stage6_source=True)

    bundle = asyncio.run(SixStageReadingEngine(provider).run(snapshot, packet))

    assert bundle.execution_status is ExecutionStatus.FAILED
    assert len(bundle.artifacts) == 5
    assert bundle.failure is not None
    assert "ineligible source claim ids" in bundle.failure


def test_stage6_rejects_an_unsettled_transfer_claim() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    provider = FakeCandidateProvider(anchor.anchor_id, empty_stage6_source=True)

    bundle = asyncio.run(SixStageReadingEngine(provider).run(snapshot, packet))

    assert bundle.execution_status is ExecutionStatus.FAILED
    assert bundle.failure is not None
    assert "eligible upstream source claim" in bundle.failure


def test_budget_omissions_survive_into_the_entry_gap_gate() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    packet = replace(
        packet,
        omitted_anchor_ids=("anchor:not-selected",),
        coverage_complete=False,
    )
    provider = FakeCandidateProvider(anchor.anchor_id)

    bundle = asyncio.run(SixStageReadingEngine(provider).run(snapshot, packet))

    assert bundle.epistemic_status is EpistemicStatus.UNDERDETERMINED
    assert any(gap.kind == "evidence_budget_omission" for gap in bundle.artifacts[0].gaps)


def test_resume_uses_frozen_stage_prefix_without_recalling_provider() -> None:
    snapshot, packet, anchor = _snapshot_and_packet()
    first_provider = FakeCandidateProvider(anchor.anchor_id)
    first = asyncio.run(SixStageReadingEngine(first_provider).run(snapshot, packet))
    resumed_provider = FakeCandidateProvider(anchor.anchor_id)
    persisted: list[str] = []

    async def sink(artifact: Any) -> None:
        persisted.append(artifact.stage.value)

    resumed = asyncio.run(
        SixStageReadingEngine(resumed_provider).run(
            snapshot,
            packet,
            initial_artifacts=first.artifacts[:3],
            artifact_sink=sink,
        )
    )

    assert resumed.execution_status is ExecutionStatus.COMPLETED
    assert [request.stage for request in resumed_provider.requests] == [
        ReadingStage.AUTHOR_MODEL.value,
        ReadingStage.BOUNDARIES.value,
        ReadingStage.TRANSFER.value,
    ]
    assert persisted == [
        ReadingStage.AUTHOR_MODEL.value,
        ReadingStage.BOUNDARIES.value,
        ReadingStage.TRANSFER.value,
    ]

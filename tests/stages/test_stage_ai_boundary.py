from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from readwelt.domain import (
    DocumentSection,
    EpistemicStatus,
    EvidencePacket,
    ExecutionStatus,
    LedgerDecision,
    ReadingClaim,
    ReadingStage,
    SourceCitation,
    SourceCitationKind,
    SourceDocumentSnapshot,
    SpanAnchor,
    StageArtifact,
)
from readwelt.providers import ProviderKind, StageCandidate, StageRequest
from readwelt.stages import SixStageReadingEngine
from readwelt.stages.policies import RESPONSE_SCHEMA


class _UnusedProvider:
    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.LOCAL

    @property
    def name(self) -> str:
        return "unused"

    @property
    def model(self) -> str:
        return "unused-v1"

    async def generate(
        self,
        request: StageRequest,
        response_schema: Mapping[str, Any],
    ) -> StageCandidate:
        del request, response_schema
        raise AssertionError("provider should not be called")


def _snapshot_and_packet() -> tuple[SourceDocumentSnapshot, EvidencePacket, SpanAnchor]:
    text = "Source claim."
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
        source_kind="text/plain",
        source_locator="source.txt",
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
    )
    return (
        snapshot,
        EvidencePacket(run_id="run-1", anchors=(anchor,), token_budget=256),
        anchor,
    )


def test_stage_request_keeps_stage_1_and_2_under_ai_responsibility() -> None:
    snapshot, packet, _ = _snapshot_and_packet()
    engine = SixStageReadingEngine(_UnusedProvider())

    request = engine._build_request(  # noqa: SLF001
        stage=ReadingStage.MAINLINE,
        snapshot=snapshot,
        evidence=packet,
        artifacts=(),
        upstream_claims=(),
    )

    boundary = request.evidence_packet["article_graph_boundary"]
    assert boundary["object_role"] == "machine_locating_candidate"
    assert boundary["may_be_final_stage_conclusion"] is False
    assert boundary["may_be_written_as_source_fact"] is False
    policy = request.evidence_packet["response_policy"]
    assert "Stage 1 remains responsible" in policy["ai_boundary"]
    assert "Stage 2 remains" in policy["ai_boundary"]


def test_stage_claim_preserves_graph_refs_but_remains_a_stage_conclusion() -> None:
    claim = SixStageReadingEngine._parse_claim(  # noqa: SLF001
        {
            "text": "Stage conclusion",
            "anchor_ids": ["anchor-1"],
            "graph_object_ids": ["node-1", "edge-1"],
        },
        stage=ReadingStage.MAINLINE,
        allowed_anchor_ids=frozenset(("anchor-1",)),
        allowed_source_claim_ids=set(),
        allowed_graph_object_ids=frozenset(("node-1", "edge-1")),
        known_claim_ids=set(),
        provider="test",
    )

    provenance = dict(claim.provenance)
    assert provenance["artifact_role"] == "stage_conclusion"
    assert provenance["source_fact"] == "false"
    assert provenance["graph_object_ids"] == '["node-1","edge-1"]'
    assert claim.source_citations[-2:] == (
        SourceCitation(SourceCitationKind.GRAPH_OBJECT, "node-1"),
        SourceCitation(SourceCitationKind.GRAPH_OBJECT, "edge-1"),
    )


def test_response_schema_exposes_graph_objects_and_typed_source_citations() -> None:
    claim_schema = RESPONSE_SCHEMA["properties"]["claims"]["items"]
    properties = claim_schema["properties"]

    assert properties["graph_object_ids"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    citation_schema = properties["source_citations"]["items"]
    assert set(citation_schema["properties"]["kind"]["enum"]) == {
        "anchor",
        "unit",
        "range",
        "element",
        "graph_object",
    }
    assert set(citation_schema["required"]) == {"kind", "identity"}


def test_image_only_source_root_element_can_ground_an_accepted_claim() -> None:
    citation = SourceCitation(SourceCitationKind.ELEMENT, "source-root-1")

    claim = SixStageReadingEngine._parse_claim(  # noqa: SLF001
        {
            "text": "The scanned source contains a diagram.",
            "anchor_ids": [],
            "source_citations": [
                {
                    "kind": "element",
                    "identity": "source-root-1",
                }
            ],
        },
        stage=ReadingStage.MAINLINE,
        allowed_anchor_ids=frozenset(),
        allowed_source_claim_ids=set(),
        allowed_graph_object_ids=frozenset(),
        allowed_source_citations=frozenset((citation,)),
        known_claim_ids=set(),
        provider="test",
    )

    assert claim.anchor_ids == ()
    assert claim.source_citations == (citation,)
    assert claim.decision is LedgerDecision.ACCEPTED


def test_unknown_or_unpresented_typed_source_citation_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside the presented provider material"):
        SixStageReadingEngine._parse_claim(  # noqa: SLF001
            {
                "text": "Unseen source claim",
                "anchor_ids": [],
                "source_citations": [
                    {
                        "kind": "element",
                        "identity": "source-root-unseen",
                    }
                ],
            },
            stage=ReadingStage.MAINLINE,
            allowed_anchor_ids=frozenset(),
            allowed_source_claim_ids=set(),
            allowed_graph_object_ids=frozenset(),
            allowed_source_citations=frozenset(),
            known_claim_ids=set(),
            provider="test",
        )


def test_graph_object_is_reachable_from_response_candidate_to_reading_claim() -> None:
    citation = SourceCitation(SourceCitationKind.GRAPH_OBJECT, "node-1")
    candidate = StageCandidate(
        schema_version="1",
        run_id="run-1",
        stage=ReadingStage.MAINLINE.value,
        candidate={
            "claims": [
                {
                    "text": "Stage conclusion grounded through a graph locator.",
                    "anchor_ids": [],
                    "graph_object_ids": ["node-1"],
                }
            ]
        },
        provider="test",
        model="test-v1",
    )

    artifact = SixStageReadingEngine(_UnusedProvider())._settle_candidate(  # noqa: SLF001
        candidate=candidate,
        stage=ReadingStage.MAINLINE,
        run_id="run-1",
        input_artifacts=(),
        allowed_anchor_ids=frozenset(),
        allowed_source_claim_ids=set(),
        allowed_graph_object_ids=frozenset(("node-1",)),
        allowed_source_citations=frozenset((citation,)),
        known_claim_ids=set(),
    )

    assert artifact.claims[0].source_citations == (citation,)
    bundle = SixStageReadingEngine(_UnusedProvider())._bundle(  # noqa: SLF001
        run_id="run-1",
        snapshot_id="snapshot-1",
        artifacts=(artifact,),
        transitions=(ReadingStage.MAINLINE.value,),
        execution_status=ExecutionStatus.COMPLETED,
    )
    assert bundle.ledger.lines[0].source_citations == (citation,)


@pytest.mark.parametrize(
    "field",
    ("source_fact", "is_source_fact", "object_role", "epistemic_status", "writeback"),
)
def test_stage_candidate_cannot_declare_source_or_articlegraph_role(field: str) -> None:
    with pytest.raises(ValueError, match="cannot declare source-fact"):
        SixStageReadingEngine._parse_claim(  # noqa: SLF001
            {
                "text": "Stage conclusion",
                "anchor_ids": ["anchor-1"],
                field: "source_fact",
            },
            stage=ReadingStage.MAINLINE,
            allowed_anchor_ids=frozenset(("anchor-1",)),
            allowed_source_claim_ids=set(),
            allowed_graph_object_ids=frozenset(),
            known_claim_ids=set(),
            provider="test",
        )


def test_provider_provenance_cannot_reclassify_stage_output_as_source_fact() -> None:
    with pytest.raises(ValueError, match="cannot reclassify"):
        SixStageReadingEngine._parse_claim(  # noqa: SLF001
            {
                "text": "Stage conclusion",
                "anchor_ids": ["anchor-1"],
                "provenance": {"source_fact": "true"},
            },
            stage=ReadingStage.MAINLINE,
            allowed_anchor_ids=frozenset(("anchor-1",)),
            allowed_source_claim_ids=set(),
            allowed_graph_object_ids=frozenset(),
            known_claim_ids=set(),
            provider="test",
        )


def test_resumed_stage_artifact_cannot_claim_source_fact_status() -> None:
    claim = ReadingClaim(
        claim_id="claim-1",
        text="Improperly reclassified conclusion",
        stage=ReadingStage.MAINLINE,
        anchor_ids=("anchor-1",),
        decision=LedgerDecision.ACCEPTED,
        provenance=(("artifact_role", "stage_conclusion"), ("source_fact", "true")),
    )
    artifact = StageArtifact(
        artifact_id="artifact-1",
        run_id="run-1",
        stage=ReadingStage.MAINLINE,
        claims=(claim,),
        gaps=(),
        warnings=(),
        input_artifact_ids=(),
        provider="test",
        model="test-v1",
        status=EpistemicStatus.SUFFICIENT,
        content_digest="sha256:" + "a" * 64,
    )

    with pytest.raises(ValueError, match="cannot be reclassified as source facts"):
        SixStageReadingEngine._validate_initial_artifacts(  # noqa: SLF001
            "run-1",
            (artifact,),
        )

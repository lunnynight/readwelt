from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from readwelt.application.run_store_codec import (
    cursor_mapping,
    decode_cursor,
    decode_navigation,
    decode_stage_artifact,
)
from readwelt.domain import (
    DecompressionArtifact,
    DecompressionUnit,
    EpistemicStatus,
    LedgerDecision,
    ReadingClaim,
    ReadingStage,
    SourceCitation,
    SourceCitationKind,
    StageArtifact,
)
from readwelt.stage_views import (
    ElementTraversalPosition,
    StageViewContinuationCursor,
    TraversalPosition,
)
from readwelt.stage_views.cursors import validate_cursor
from readwelt.storage.serialization import to_primitive

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "stage_navigation"


def _cursor_v2() -> StageViewContinuationCursor:
    return StageViewContinuationCursor.create(
        snapshot_id="snapshot_codec",
        source_plane_schema_version="article-source-plane.v1",
        stage=ReadingStage.MAINLINE,
        policy_digest="sha256:" + ("1" * 64),
        index_digest="sha256:" + ("2" * 64),
        frontier=(TraversalPosition("unit_1", 3),),
        visited_unit_ids=("unit_0",),
        range_frontier=("range_1",),
        element_frontier=(ElementTraversalPosition("element_1", 7),),
        visited_range_ids=("range_0",),
        visited_element_ids=("element_0",),
    )


def test_cursor_v2_codec_preserves_every_source_plane_frontier() -> None:
    cursor = _cursor_v2()

    encoded = cursor_mapping(cursor)
    decoded = decode_cursor(encoded)

    assert decoded == cursor


@pytest.mark.parametrize(
    "missing_field",
    [
        "range_frontier",
        "element_frontier",
        "visited_range_ids",
        "visited_element_ids",
    ],
)
def test_cursor_v2_codec_fails_closed_when_traversal_state_is_missing(
    missing_field: str,
) -> None:
    encoded = cursor_mapping(_cursor_v2())
    assert encoded is not None
    encoded.pop(missing_field)

    with pytest.raises(ValueError, match="missing traversal fields"):
        decode_cursor(encoded)


def test_genuine_pre_v2_cursor_fixture_validates_original_digest_and_resume() -> None:
    path = _FIXTURES / "pre_v2_cursor.v1.json"
    original = path.read_bytes()
    payload = json.loads(original)

    cursor = decode_cursor(payload)

    assert cursor is not None
    assert cursor.schema_version == "stage-view-cursor.v1"
    assert cursor.range_frontier == ()
    assert cursor.element_frontier == ()
    historical_build = SimpleNamespace(
        snapshot_id=cursor.snapshot_id,
        unitization=SimpleNamespace(
            schema_version=cursor.source_plane_schema_version,
            units=(SimpleNamespace(unit_id="unit:legacy:2"),),
            source_ranges=(),
            source_elements=(),
        ),
        source_index=SimpleNamespace(content_digest=cursor.index_digest),
    )
    context = SimpleNamespace(
        continuation=cursor,
        stage=ReadingStage.MAINLINE,
    )
    validate_cursor(historical_build, context, cursor.policy_digest)
    assert path.read_bytes() == original


def test_pre_v2_cursor_fixture_is_explicitly_stale_for_complete_source_plane() -> None:
    cursor = decode_cursor(json.loads((_FIXTURES / "pre_v2_cursor.v1.json").read_bytes()))
    assert cursor is not None
    current_build = SimpleNamespace(
        snapshot_id=cursor.snapshot_id,
        unitization=SimpleNamespace(
            schema_version="article-source-plane.v1",
            units=(SimpleNamespace(unit_id="unit:legacy:2"),),
            source_ranges=(),
            source_elements=(),
        ),
        source_index=SimpleNamespace(content_digest=cursor.index_digest),
    )
    context = SimpleNamespace(
        continuation=cursor,
        stage=ReadingStage.MAINLINE,
    )

    with pytest.raises(ValueError, match="stale or incompatible"):
        validate_cursor(current_build, context, cursor.policy_digest)


def test_genuine_pre_v2_stage_navigation_fixture_decodes_without_rewrite() -> None:
    path = _FIXTURES / "pre_v2_stage_navigation.v1.json"
    original = path.read_bytes()
    payload = json.loads(original)

    state = decode_navigation(ReadingStage.MAINLINE, payload)

    assert state.page_index == 1
    assert state.next_continuation is not None
    assert state.next_continuation.schema_version == "stage-view-cursor.v1"
    assert state.stage_view.schema_version == "stage-view.v1"
    assert state.stage_view_token_budget is None
    assert state.stage_view_hard_serialized_token_budget is None
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "missing_field",
    (
        "snapshot_id",
        "source_plane_schema_version",
        "stage",
        "policy_digest",
        "index_digest",
        "frontier",
        "visited_unit_ids",
        "content_digest",
    ),
)
def test_historical_cursor_codec_fails_closed_when_required_state_is_missing(
    missing_field: str,
) -> None:
    payload = json.loads((_FIXTURES / "pre_v2_cursor.v1.json").read_bytes())
    payload.pop(missing_field)

    with pytest.raises(ValueError, match="missing fields"):
        decode_cursor(payload)


def test_stage_navigation_codec_fails_closed_for_missing_or_mismatched_stage() -> None:
    payload = json.loads((_FIXTURES / "pre_v2_stage_navigation.v1.json").read_bytes())
    payload.pop("stage_view")
    with pytest.raises(ValueError, match="missing fields"):
        decode_navigation(ReadingStage.MAINLINE, payload)

    payload = json.loads((_FIXTURES / "pre_v2_stage_navigation.v1.json").read_bytes())
    with pytest.raises(ValueError, match="another reading stage"):
        decode_navigation(ReadingStage.STRUCTURE, payload)


def test_stage_artifact_codec_roundtrips_typed_source_citations() -> None:
    citation = SourceCitation(SourceCitationKind.ELEMENT, "source-root-1")
    artifact = StageArtifact(
        artifact_id="artifact-typed-citation",
        run_id="run-typed-citation",
        stage=ReadingStage.MAINLINE,
        claims=(
            ReadingClaim(
                claim_id="claim-typed-citation",
                text="The image-only source contains a diagram.",
                stage=ReadingStage.MAINLINE,
                anchor_ids=(),
                decision=LedgerDecision.ACCEPTED,
                source_citations=(citation,),
            ),
        ),
        gaps=(),
        warnings=(),
        input_artifact_ids=(),
        provider="test",
        model="test-v1",
        status=EpistemicStatus.SUFFICIENT,
        content_digest="sha256:" + "8" * 64,
    )

    encoded = to_primitive(artifact)
    assert isinstance(encoded, dict)
    decoded = decode_stage_artifact(encoded)

    assert decoded == artifact
    assert decoded.claims[0].source_citations == (citation,)


def test_decompression_artifact_codec_preserves_versioned_units_and_citations() -> None:
    citation = SourceCitation(SourceCitationKind.ANCHOR, "anchor-decompression")
    claim = ReadingClaim(
        claim_id="stage_3_decompression:claim:1",
        text="The concept depends on the stated prerequisite.",
        stage=ReadingStage.DECOMPRESSION,
        anchor_ids=(citation.identity,),
        decision=LedgerDecision.ACCEPTED,
        source_claim_ids=("stage_2_structure:claim:1",),
        source_citations=(citation,),
    )
    unit = DecompressionUnit(
        unit_id="du-1",
        explanation="The prerequisite explains why the conclusion follows.",
        claim_ids=(claim.claim_id,),
        source_citations=(citation,),
        concepts_assumed=("the prerequisite",),
        mechanism_steps=("apply the prerequisite", "derive the conclusion"),
        changed_condition_examples=("remove the prerequisite and reassess",),
        uncertainties=("whether the source establishes the prerequisite",),
    )
    decompression = DecompressionArtifact(
        artifact_id="decompression-artifact-1",
        run_id="run-decompression",
        units=(unit,),
    )
    artifact = StageArtifact(
        artifact_id="stage-artifact-decompression",
        run_id="run-decompression",
        stage=ReadingStage.DECOMPRESSION,
        claims=(claim,),
        gaps=(),
        warnings=(),
        input_artifact_ids=("stage-2-artifact",),
        provider="test",
        model="test-v1",
        status=EpistemicStatus.SUFFICIENT,
        content_digest="sha256:" + "9" * 64,
        decompression_artifact=decompression,
    )

    encoded = to_primitive(artifact)
    assert isinstance(encoded, dict)
    decoded = decode_stage_artifact(encoded)

    assert decoded == artifact
    assert decoded.decompression_artifact is not None
    assert decoded.decompression_artifact.schema_version == "decompression-artifact.v1"
    assert decoded.decompression_artifact.units[0].source_citations == (citation,)


def test_historical_stage_claim_without_typed_citations_upgrades_from_anchors() -> None:
    payload = {
        "artifact_id": "artifact-legacy-citation",
        "run_id": "run-legacy-citation",
        "stage": ReadingStage.MAINLINE.value,
        "claims": [
            {
                "claim_id": "claim-legacy-citation",
                "text": "Historical anchored claim.",
                "anchor_ids": ["anchor-legacy"],
                "decision": LedgerDecision.ACCEPTED.value,
                "source_claim_ids": [],
                "limitations": [],
                "provenance": [],
            }
        ],
        "gaps": [],
        "warnings": [],
        "input_artifact_ids": [],
        "provider": "legacy",
        "model": None,
        "status": EpistemicStatus.SUFFICIENT.value,
        "content_digest": "sha256:" + "7" * 64,
        "provider_provenance": [],
        "input_state": None,
    }

    decoded = decode_stage_artifact(payload)

    assert decoded.claims[0].source_citations == (
        SourceCitation(SourceCitationKind.ANCHOR, "anchor-legacy"),
    )
    assert decoded.decompression_artifact is None

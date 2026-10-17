"""Stable manifest codecs for application-run persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from readwelt.domain import (
    ArtifactRef,
    ArtifactStatus,
    DecompressionArtifact,
    DecompressionUnit,
    LedgerDecision,
    ReadingClaim,
    ReadingGap,
    ReadingRun,
    ReadingStage,
    SourceCitation,
    SourceCitationKind,
    StageArtifact,
    StageInputState,
    StageInputStatus,
)
from readwelt.stage_views import (
    ElementTraversalPosition,
    StageViewContinuationCursor,
    TraversalPosition,
)


@dataclass(frozen=True, slots=True)
class StageNavigationState:
    stage: ReadingStage
    page_index: int
    input_continuation: StageViewContinuationCursor | None
    next_continuation: StageViewContinuationCursor | None
    targeted_anchor_ids: tuple[str, ...]
    rescue_level: str
    stage_view: ArtifactRef
    latest_request_digest: str | None = None
    stage_view_hard_serialized_token_budget: int | None = None
    stage_view_token_budget: int | None = None

    def __post_init__(self) -> None:
        if (
            self.stage_view_hard_serialized_token_budget is not None
            and self.stage_view_hard_serialized_token_budget < 1
        ):
            raise ValueError("persisted StageView hard budget must be positive")
        if self.stage_view_token_budget is not None and self.stage_view_token_budget < 0:
            raise ValueError("persisted StageView token budget cannot be negative")


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


def navigation_mapping(state: StageNavigationState) -> dict[str, Any]:
    return {
        "schema_version": "stage-navigation.v1",
        "stage": state.stage.value,
        "page_index": state.page_index,
        "input_continuation": cursor_mapping(state.input_continuation),
        "next_continuation": cursor_mapping(state.next_continuation),
        "targeted_anchor_ids": list(state.targeted_anchor_ids),
        "rescue_level": state.rescue_level,
        "stage_view": state.stage_view,
        "latest_request_digest": state.latest_request_digest,
        "stage_view_hard_serialized_token_budget": (state.stage_view_hard_serialized_token_budget),
        "stage_view_token_budget": state.stage_view_token_budget,
    }


def cursor_mapping(
    cursor: StageViewContinuationCursor | None,
) -> dict[str, Any] | None:
    if cursor is None:
        return None
    result: dict[str, Any] = {
        "schema_version": cursor.schema_version,
        "snapshot_id": cursor.snapshot_id,
        "source_plane_schema_version": cursor.source_plane_schema_version,
        "stage": cursor.stage.value,
        "policy_digest": cursor.policy_digest,
        "index_digest": cursor.index_digest,
        "frontier": [
            {"unit_id": item.unit_id, "start_offset": item.start_offset} for item in cursor.frontier
        ],
        "visited_unit_ids": list(cursor.visited_unit_ids),
        "content_digest": cursor.content_digest,
    }
    if cursor.schema_version == "stage-view-cursor.v2":
        result.update(
            {
                "range_frontier": list(cursor.range_frontier),
                "element_frontier": [
                    {
                        "element_id": item.element_id,
                        "start_offset": item.start_offset,
                    }
                    for item in cursor.element_frontier
                ],
                "visited_range_ids": list(cursor.visited_range_ids),
                "visited_element_ids": list(cursor.visited_element_ids),
            }
        )
    return result


def decode_navigation(
    stage: ReadingStage,
    value: Mapping[str, Any],
) -> StageNavigationState:
    if value.get("schema_version") != "stage-navigation.v1":
        raise ValueError("unsupported stage navigation schema")
    required = (
        "stage",
        "page_index",
        "input_continuation",
        "next_continuation",
        "targeted_anchor_ids",
        "rescue_level",
        "stage_view",
        "latest_request_digest",
    )
    missing = tuple(field for field in required if field not in value)
    if missing:
        raise ValueError(f"stage-navigation.v1 is missing fields: {', '.join(missing)}")
    if value["stage"] != stage.value:
        raise ValueError("stage navigation belongs to another reading stage")
    raw_view = value.get("stage_view")
    if not isinstance(raw_view, Mapping):
        raise ValueError("stage navigation requires a stage_view artifact")
    return StageNavigationState(
        stage=stage,
        page_index=int(value["page_index"]),
        input_continuation=decode_cursor(value.get("input_continuation")),
        next_continuation=decode_cursor(value.get("next_continuation")),
        targeted_anchor_ids=string_tuple(
            value.get("targeted_anchor_ids"),
            "targeted_anchor_ids",
        ),
        rescue_level=str(value["rescue_level"]),
        stage_view=decode_artifact_ref(raw_view),
        latest_request_digest=(
            str(value["latest_request_digest"])
            if value.get("latest_request_digest") is not None
            else None
        ),
        stage_view_hard_serialized_token_budget=(
            int(value["stage_view_hard_serialized_token_budget"])
            if value.get("stage_view_hard_serialized_token_budget") is not None
            else None
        ),
        stage_view_token_budget=(
            int(value["stage_view_token_budget"])
            if value.get("stage_view_token_budget") is not None
            else None
        ),
    )


def decode_cursor(value: object) -> StageViewContinuationCursor | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("stage navigation cursor must be an object")
    common_fields = (
        "schema_version",
        "snapshot_id",
        "source_plane_schema_version",
        "stage",
        "policy_digest",
        "index_digest",
        "frontier",
        "visited_unit_ids",
        "content_digest",
    )
    missing_common = tuple(field for field in common_fields if field not in value)
    if missing_common:
        raise ValueError(f"stage navigation cursor is missing fields: {', '.join(missing_common)}")
    raw_frontier = value.get("frontier")
    if not isinstance(raw_frontier, list):
        raise ValueError("stage navigation cursor frontier must be an array")
    schema_version = str(value["schema_version"])
    if schema_version == "stage-view-cursor.v2":
        required_v2 = (
            "range_frontier",
            "element_frontier",
            "visited_range_ids",
            "visited_element_ids",
        )
        missing = tuple(field for field in required_v2 if field not in value)
        if missing:
            raise ValueError(
                f"stage-view-cursor.v2 is missing traversal fields: {', '.join(missing)}"
            )
        raw_element_frontier = value["element_frontier"]
        if not isinstance(raw_element_frontier, list):
            raise ValueError("element_frontier must be an array")
        range_frontier = string_tuple(value["range_frontier"], "range_frontier")
        element_frontier = tuple(_decode_element_position(item) for item in raw_element_frontier)
        visited_range_ids = string_tuple(
            value["visited_range_ids"],
            "visited_range_ids",
        )
        visited_element_ids = string_tuple(
            value["visited_element_ids"],
            "visited_element_ids",
        )
    else:
        range_frontier = ()
        element_frontier = ()
        visited_range_ids = ()
        visited_element_ids = ()
    if any(not isinstance(item, Mapping) for item in raw_frontier):
        raise ValueError("stage navigation cursor frontier entries must be objects")
    return StageViewContinuationCursor(
        schema_version=schema_version,
        snapshot_id=str(value["snapshot_id"]),
        source_plane_schema_version=str(value["source_plane_schema_version"]),
        stage=ReadingStage(str(value["stage"])),
        policy_digest=str(value["policy_digest"]),
        index_digest=str(value["index_digest"]),
        frontier=tuple(
            TraversalPosition(
                unit_id=str(item["unit_id"]),
                start_offset=int(item["start_offset"]),
            )
            for item in raw_frontier
        ),
        visited_unit_ids=string_tuple(
            value.get("visited_unit_ids"),
            "visited_unit_ids",
        ),
        content_digest=str(value["content_digest"]),
        range_frontier=range_frontier,
        element_frontier=element_frontier,
        visited_range_ids=visited_range_ids,
        visited_element_ids=visited_element_ids,
    )


def _decode_element_position(value: object) -> ElementTraversalPosition:
    if not isinstance(value, Mapping):
        raise ValueError("element_frontier entries must be objects")
    return ElementTraversalPosition(
        element_id=str(value["element_id"]),
        start_offset=int(value["start_offset"]),
    )


def decode_artifact_ref(value: Mapping[str, Any]) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=str(value["artifact_id"]),
        artifact_type=str(value["artifact_type"]),
        schema_version=str(value["schema_version"]),
        content_digest=str(value["content_digest"]),
        path=str(value["path"]),
        size=int(value["size"]),
        status=ArtifactStatus(str(value["status"])),
    )


def decode_stage_artifact(value: Mapping[str, Any]) -> StageArtifact:
    stage = ReadingStage(str(value["stage"]))
    raw_claims = value.get("claims")
    raw_gaps = value.get("gaps")
    if not isinstance(raw_claims, list) or not isinstance(raw_gaps, list):
        raise ValueError("stage artifact claims and gaps must be arrays")
    claims = tuple(decode_claim(item, stage) for item in raw_claims)
    gaps = tuple(decode_gap(item, stage) for item in raw_gaps)
    raw_decompression = value.get("decompression_artifact")
    if raw_decompression is not None and not isinstance(raw_decompression, Mapping):
        raise ValueError("stage artifact decompression_artifact must be an object")
    raw_input_state = value.get("input_state")
    if raw_input_state is not None and not isinstance(raw_input_state, Mapping):
        raise ValueError("stage artifact input_state must be an object")
    input_state = (
        StageInputState(
            schema_version=str(raw_input_state["schema_version"]),
            status=StageInputStatus(str(raw_input_state["status"])),
            stage_view_digest=str(raw_input_state["stage_view_digest"]),
            coverage_digest=(
                str(raw_input_state["coverage_digest"])
                if raw_input_state.get("coverage_digest") is not None
                else None
            ),
            continuation_digest=(
                str(raw_input_state["continuation_digest"])
                if raw_input_state.get("continuation_digest") is not None
                else None
            ),
            blocking_reasons=string_tuple(
                raw_input_state.get("blocking_reasons"),
                "blocking_reasons",
            ),
            unresolved_critical_ids=string_tuple(
                raw_input_state.get("unresolved_critical_ids"),
                "unresolved_critical_ids",
            ),
        )
        if isinstance(raw_input_state, Mapping)
        else None
    )
    return StageArtifact(
        artifact_id=str(value["artifact_id"]),
        run_id=str(value["run_id"]),
        stage=stage,
        claims=claims,
        gaps=gaps,
        warnings=string_tuple(value.get("warnings"), "warnings"),
        input_artifact_ids=string_tuple(
            value.get("input_artifact_ids"),
            "input_artifact_ids",
        ),
        provider=str(value["provider"]),
        model=str(value["model"]) if value.get("model") is not None else None,
        status=epistemic_status(value["status"]),
        content_digest=str(value["content_digest"]),
        provider_provenance=pairs(
            value.get("provider_provenance", []),
            "provider_provenance",
        ),
        input_state=input_state,
        decompression_artifact=(
            decode_decompression_artifact(raw_decompression)
            if isinstance(raw_decompression, Mapping)
            else None
        ),
    )


def decode_decompression_artifact(value: Mapping[str, Any]) -> DecompressionArtifact:
    raw_units = value.get("units")
    if not isinstance(raw_units, list):
        raise ValueError("decompression artifact units must be an array")
    units: list[DecompressionUnit] = []
    for raw_unit in raw_units:
        if not isinstance(raw_unit, Mapping):
            raise ValueError("decompression artifact units must be objects")
        units.append(
            DecompressionUnit(
                unit_id=str(raw_unit.get("unit_id", "")).strip(),
                explanation=str(raw_unit.get("explanation", "")).strip(),
                claim_ids=string_tuple(raw_unit.get("claim_ids"), "claim_ids"),
                source_citations=source_citations(raw_unit.get("source_citations")),
                concepts_introduced=string_tuple(
                    raw_unit.get("concepts_introduced", []), "concepts_introduced"
                ),
                concepts_assumed=string_tuple(
                    raw_unit.get("concepts_assumed", []), "concepts_assumed"
                ),
                mechanism_steps=string_tuple(
                    raw_unit.get("mechanism_steps", []), "mechanism_steps"
                ),
                dependencies=string_tuple(raw_unit.get("dependencies", []), "dependencies"),
                missing_prerequisites=string_tuple(
                    raw_unit.get("missing_prerequisites", []), "missing_prerequisites"
                ),
                tacit_practices=string_tuple(
                    raw_unit.get("tacit_practices", []), "tacit_practices"
                ),
                assumptions=string_tuple(raw_unit.get("assumptions", []), "assumptions"),
                inferred_relations=string_tuple(
                    raw_unit.get("inferred_relations", []), "inferred_relations"
                ),
                boundary_conditions=string_tuple(
                    raw_unit.get("boundary_conditions", []), "boundary_conditions"
                ),
                alternatives=string_tuple(raw_unit.get("alternatives", []), "alternatives"),
                changed_condition_examples=string_tuple(
                    raw_unit.get("changed_condition_examples", []),
                    "changed_condition_examples",
                ),
                uncertainties=string_tuple(
                    raw_unit.get("uncertainties", []), "uncertainties"
                ),
            )
        )
    return DecompressionArtifact(
        artifact_id=str(value.get("artifact_id", "")).strip(),
        run_id=str(value.get("run_id", "")).strip(),
        units=tuple(units),
        schema_version=str(value.get("schema_version", "")),
    )


def decode_claim(value: object, stage: ReadingStage) -> ReadingClaim:
    if not isinstance(value, Mapping):
        raise ValueError("stage artifact claim must be an object")
    return ReadingClaim(
        claim_id=str(value["claim_id"]),
        text=str(value["text"]),
        stage=stage,
        anchor_ids=string_tuple(value.get("anchor_ids"), "anchor_ids"),
        decision=LedgerDecision(str(value["decision"])),
        source_claim_ids=string_tuple(
            value.get("source_claim_ids"),
            "source_claim_ids",
        ),
        limitations=string_tuple(value.get("limitations"), "limitations"),
        provenance=pairs(value.get("provenance", []), "claim provenance"),
        source_citations=source_citations(value.get("source_citations", [])),
    )


def decode_gap(value: object, stage: ReadingStage) -> ReadingGap:
    if not isinstance(value, Mapping):
        raise ValueError("stage artifact gap must be an object")
    return ReadingGap(
        gap_id=str(value["gap_id"]),
        kind=str(value["kind"]),
        description=str(value["description"]),
        origin_stage=stage,
        affected_claim_ids=string_tuple(
            value.get("affected_claim_ids"),
            "affected_claim_ids",
        ),
        critical=strict_bool(value.get("critical"), "critical"),
        repairable=strict_bool(value.get("repairable"), "repairable"),
        resolved=strict_bool(value.get("resolved"), "resolved"),
    )


def string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def source_citations(value: object) -> tuple[SourceCitation, ...]:
    if not isinstance(value, list):
        raise ValueError("source_citations must be an array")
    result: list[SourceCitation] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("source_citations entries must be objects")
        result.append(
            SourceCitation(
                kind=SourceCitationKind(str(item.get("kind", ""))),
                identity=str(item.get("identity", "")).strip(),
                schema_version=str(item.get("schema_version", "source-citation.v1")),
            )
        )
    return tuple(result)


def strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def pairs(value: object, label: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    result: list[tuple[str, str]] = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"{label} entries must be key/value pairs")
        result.append((str(pair[0]), str(pair[1])))
    return tuple(result)


def epistemic_status(value: object) -> Any:
    from readwelt.domain import EpistemicStatus

    return EpistemicStatus(str(value))

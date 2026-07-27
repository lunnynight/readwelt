"""Integrity checks and policy binding for StageView traversal cursors."""

from __future__ import annotations

from readwelt.article_graph import ArticleGraphBuildResult
from readwelt.article_graph.digest import content_digest
from readwelt.semantic.models import SemanticEvidencePacket

from .models import StageContext


def validate_locator(
    build: ArticleGraphBuildResult,
    context: StageContext,
    locator_packet: SemanticEvidencePacket | None,
) -> None:
    if locator_packet is None:
        return
    if locator_packet.snapshot_id != build.snapshot_id:
        raise ValueError("locator packet belongs to a different snapshot")
    if locator_packet.stage is not None and locator_packet.stage is not context.stage:
        raise ValueError("locator packet belongs to a different reading stage")


def validate_cursor(
    build: ArticleGraphBuildResult,
    context: StageContext,
    policy_digest: str,
) -> None:
    cursor = context.continuation
    assert cursor is not None
    expected = {
        "snapshot_id": build.snapshot_id,
        "source_plane_schema_version": build.unitization.schema_version,
        "stage": context.stage,
        "policy_digest": policy_digest,
        "index_digest": build.source_index.content_digest,
    }
    actual = {
        "snapshot_id": cursor.snapshot_id,
        "source_plane_schema_version": cursor.source_plane_schema_version,
        "stage": cursor.stage,
        "policy_digest": cursor.policy_digest,
        "index_digest": cursor.index_digest,
    }
    if actual != expected:
        raise ValueError("stale or incompatible StageView continuation cursor")
    if (
        build.unitization.schema_version == "article-source-plane.v1"
        and cursor.schema_version != "stage-view-cursor.v2"
    ):
        raise ValueError(
            "text-only StageView cursor cannot resume a complete Source Plane traversal"
        )
    known_ids = {unit.unit_id for unit in build.unitization.units}
    if any(item.unit_id not in known_ids for item in cursor.frontier):
        raise ValueError("StageView continuation cursor names an unknown source unit")
    known_ranges = {item.range_id for item in build.unitization.source_ranges}
    if not set(cursor.range_frontier).issubset(known_ranges):
        raise ValueError("StageView continuation cursor names an unknown source range")
    if not set(cursor.visited_range_ids).issubset(known_ranges):
        raise ValueError("StageView continuation cursor visited unknown source ranges")
    known_elements = {item.element_id for item in build.unitization.source_elements}
    if any(item.element_id not in known_elements for item in cursor.element_frontier):
        raise ValueError("StageView continuation cursor names an unknown source element")
    if not set(cursor.visited_element_ids).issubset(known_elements):
        raise ValueError("StageView continuation cursor visited unknown source elements")


def policy_digest(context: StageContext) -> str:
    return content_digest(
        {
            "policy_version": context.policy_version,
            "stage": context.stage.value,
            "task_intent": context.task_intent,
            "token_budget": context.token_budget,
            "hard_serialized_token_budget": context.hard_serialized_token_budget,
            "allowed_anchor_ids": context.allowed_anchor_ids,
            "critical_anchor_ids": context.critical_anchor_ids,
            "critical_range_ids": context.critical_range_ids,
            "critical_element_ids": context.critical_element_ids,
            "cited_anchor_ids": context.cited_anchor_ids,
            "cited_range_ids": context.cited_range_ids,
            "cited_element_ids": context.cited_element_ids,
            "targeted_anchor_ids": context.targeted_anchor_ids,
            "rescue_level": context.rescue_level,
            "split_oversized_units": context.split_oversized_units,
        }
    )

"""Deterministic admission checks for stage projections."""

from __future__ import annotations

from collections.abc import Collection

from readwelt.domain.reading import ReadingStage

from .models import StageView


def validate_stage_view(
    view: StageView,
    *,
    snapshot_id: str,
    stage: ReadingStage,
    allowed_anchor_ids: Collection[str],
) -> None:
    if view.snapshot_id != snapshot_id:
        raise ValueError("StageView belongs to a different snapshot")
    if view.stage is not stage:
        raise ValueError("StageView belongs to a different reading stage")
    if not set(view.anchor_ids).issubset(allowed_anchor_ids):
        raise ValueError("StageView contains anchors outside admitted evidence")

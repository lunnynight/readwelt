"""Per-stage context exposure accounting during Query Plane migration."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.domain import ReadingStage
from readwelt.stage_views import StageView
from readwelt.storage import ArtifactStore, ImmutableArtifactReader

from .run_store import ApplicationRunStore


@dataclass(frozen=True, slots=True)
class StageContextExposure:
    stage: ReadingStage
    eager_stage_view_estimated_tokens: int
    query_evidence_estimated_tokens: int
    compatibility_adapter_estimated_tokens: int
    logical_primary_delta_tokens: int
    actual_inline_delta_tokens: int
    quality_gain_claimed: bool = False


def measure_stage_context_exposure(
    run_store: ApplicationRunStore,
    artifacts: ArtifactStore,
    run_id: str,
) -> tuple[StageContextExposure, ...]:
    """Compare query-selected evidence with the retained eager compatibility surface."""
    reader = ImmutableArtifactReader(artifacts)
    measurements: list[StageContextExposure] = []
    for stage in ReadingStage:
        navigation = run_store.load_stage_navigation(run_id, stage)
        receipts = run_store.load_query_receipts(run_id, stage)
        if navigation is None or len(receipts) != 1:
            raise ValueError(f"stage exposure is incomplete: {stage.value}")
        decoded = reader.read(navigation.stage_view).decoded
        if not isinstance(decoded, StageView):
            raise ValueError("stage navigation does not reference a StageView")
        eager_tokens = decoded.estimated_tokens
        query_tokens = receipts[0].usage.estimated_tokens
        measurements.append(
            StageContextExposure(
                stage=stage,
                eager_stage_view_estimated_tokens=eager_tokens,
                query_evidence_estimated_tokens=query_tokens,
                compatibility_adapter_estimated_tokens=eager_tokens,
                logical_primary_delta_tokens=query_tokens - eager_tokens,
                actual_inline_delta_tokens=0,
            )
        )
    return tuple(measurements)


__all__ = ["StageContextExposure", "measure_stage_context_exposure"]

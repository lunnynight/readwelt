"""Intent, frontier, and integrity state for resumable StageView traversal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from readwelt.article_graph.digest import content_digest
from readwelt.domain.reading import ReadingStage

RescueLevel = Literal["initial", "neighbors", "structure", "targeted", "section"]


@dataclass(frozen=True, slots=True)
class StageContext:
    """Intent and budget that determine one stage projection."""

    stage: ReadingStage
    task_intent: str
    token_budget: int
    upstream_claim_ids: tuple[str, ...] = ()
    unresolved_gap_ids: tuple[str, ...] = ()
    allowed_anchor_ids: tuple[str, ...] | None = None
    critical_anchor_ids: tuple[str, ...] = ()
    critical_range_ids: tuple[str, ...] = ()
    critical_element_ids: tuple[str, ...] = ()
    cited_anchor_ids: tuple[str, ...] = ()
    cited_range_ids: tuple[str, ...] = ()
    cited_element_ids: tuple[str, ...] = ()
    targeted_anchor_ids: tuple[str, ...] = ()
    rescue_level: RescueLevel = "structure"
    continuation: StageViewContinuationCursor | None = None
    hard_serialized_token_budget: int | None = None
    policy_version: str = "stage-view-policy.v2"
    split_oversized_units: bool = True

    def __post_init__(self) -> None:
        if not self.task_intent.strip():
            raise ValueError("task_intent is required")
        if self.token_budget < 0:
            raise ValueError("token_budget cannot be negative")
        if self.hard_serialized_token_budget is not None and self.hard_serialized_token_budget < 1:
            raise ValueError("hard_serialized_token_budget must be positive")
        if self.rescue_level not in {
            "initial",
            "neighbors",
            "structure",
            "targeted",
            "section",
        }:
            raise ValueError(f"unsupported rescue_level: {self.rescue_level}")
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")
        for name, identities in (
            ("critical_range_ids", self.critical_range_ids),
            ("critical_element_ids", self.critical_element_ids),
            ("cited_range_ids", self.cited_range_ids),
            ("cited_element_ids", self.cited_element_ids),
        ):
            if len(identities) != len(set(identities)) or any(
                not identity for identity in identities
            ):
                raise ValueError(f"{name} must contain unique non-empty identities")


@dataclass(frozen=True, slots=True)
class TraversalPosition:
    """One deterministic position in a resumable text traversal."""

    unit_id: str
    start_offset: int = 0

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("traversal unit_id is required")
        if self.start_offset < 0:
            raise ValueError("traversal start_offset cannot be negative")


@dataclass(frozen=True, slots=True)
class ElementTraversalPosition:
    """One resumable position inside a Source Plane element."""

    element_id: str
    start_offset: int = 0

    def __post_init__(self) -> None:
        if not self.element_id:
            raise ValueError("traversal element_id is required")
        if self.start_offset < 0:
            raise ValueError("element traversal start_offset cannot be negative")


@dataclass(frozen=True, slots=True)
class StageViewContinuationCursor:
    """Integrity-bound traversal state; never resumes against another build."""

    schema_version: str
    snapshot_id: str
    source_plane_schema_version: str
    stage: ReadingStage
    policy_digest: str
    index_digest: str
    frontier: tuple[TraversalPosition, ...]
    visited_unit_ids: tuple[str, ...]
    content_digest: str
    range_frontier: tuple[str, ...] = ()
    element_frontier: tuple[ElementTraversalPosition, ...] = ()
    visited_range_ids: tuple[str, ...] = ()
    visited_element_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version not in {"stage-view-cursor.v1", "stage-view-cursor.v2"}:
            raise ValueError(f"unsupported StageView cursor: {self.schema_version}")
        if not self.snapshot_id or not self.source_plane_schema_version:
            raise ValueError("cursor source identity is required")
        for name, digest in (
            ("policy_digest", self.policy_digest),
            ("index_digest", self.index_digest),
            ("content_digest", self.content_digest),
        ):
            if not digest.startswith("sha256:"):
                raise ValueError(f"{name} must be a sha256 digest")
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "source_plane_schema_version": self.source_plane_schema_version,
            "stage": self.stage.value,
            "policy_digest": self.policy_digest,
            "index_digest": self.index_digest,
            "frontier": self.frontier,
            "visited_unit_ids": self.visited_unit_ids,
        }
        if self.schema_version == "stage-view-cursor.v2":
            payload.update(
                {
                    "range_frontier": self.range_frontier,
                    "element_frontier": self.element_frontier,
                    "visited_range_ids": self.visited_range_ids,
                    "visited_element_ids": self.visited_element_ids,
                }
            )
        if self.content_digest != content_digest(payload):
            raise ValueError("StageView cursor content digest mismatch")

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        source_plane_schema_version: str,
        stage: ReadingStage,
        policy_digest: str,
        index_digest: str,
        frontier: tuple[TraversalPosition, ...],
        visited_unit_ids: tuple[str, ...],
        range_frontier: tuple[str, ...] = (),
        element_frontier: tuple[ElementTraversalPosition, ...] = (),
        visited_range_ids: tuple[str, ...] = (),
        visited_element_ids: tuple[str, ...] = (),
    ) -> StageViewContinuationCursor:
        payload: dict[str, object] = {
            "schema_version": "stage-view-cursor.v2",
            "snapshot_id": snapshot_id,
            "source_plane_schema_version": source_plane_schema_version,
            "stage": stage.value,
            "policy_digest": policy_digest,
            "index_digest": index_digest,
            "frontier": frontier,
            "visited_unit_ids": visited_unit_ids,
            "range_frontier": range_frontier,
            "element_frontier": element_frontier,
            "visited_range_ids": visited_range_ids,
            "visited_element_ids": visited_element_ids,
        }
        return cls(
            schema_version="stage-view-cursor.v2",
            snapshot_id=snapshot_id,
            source_plane_schema_version=source_plane_schema_version,
            stage=stage,
            policy_digest=policy_digest,
            index_digest=index_digest,
            frontier=frontier,
            visited_unit_ids=visited_unit_ids,
            content_digest=content_digest(payload),
            range_frontier=range_frontier,
            element_frontier=element_frontier,
            visited_range_ids=visited_range_ids,
            visited_element_ids=visited_element_ids,
        )

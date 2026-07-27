"""Coverage and blocking contracts for bounded StageViews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OmissionReason = Literal[
    "anchor_not_admitted",
    "continuation_pending",
    "hard_serialized_budget",
    "not_presented_to_provider",
    "oversized_unit_blocked",
    "oversized_unit_remainder",
    "oversized_element_blocked",
    "oversized_element_remainder",
    "stage_policy_not_selected",
    "visited_previous_page",
]


@dataclass(frozen=True, slots=True)
class CoverageOmission:
    identity: str
    reason: OmissionReason
    detail: str | None = None
    object_type: Literal["unit", "range", "element"] = "unit"


@dataclass(frozen=True, slots=True)
class StageViewCoverageManifest:
    """Separate source, traversal, serialization, and provider coverage."""

    schema_version: str
    source_unit_ids: tuple[str, ...]
    visited_unit_ids: tuple[str, ...]
    selected_unit_ids: tuple[str, ...]
    serialized_identities: tuple[str, ...]
    presented_identities: tuple[str, ...]
    cited_unit_ids: tuple[str, ...]
    critical_unit_ids: tuple[str, ...]
    omitted: tuple[CoverageOmission, ...]
    source_complete: bool
    stage_input_complete: bool
    critical_range_ids: tuple[str, ...] = ()
    critical_element_ids: tuple[str, ...] = ()
    cited_range_ids: tuple[str, ...] = ()
    cited_element_ids: tuple[str, ...] = ()
    source_range_ids: tuple[str, ...] = ()
    visited_range_ids: tuple[str, ...] = ()
    selected_range_ids: tuple[str, ...] = ()
    source_element_ids: tuple[str, ...] = ()
    visited_element_ids: tuple[str, ...] = ()
    selected_element_ids: tuple[str, ...] = ()
    presented_range_ids: tuple[str, ...] = ()
    presented_element_ids: tuple[str, ...] = ()
    completed_unit_ids: tuple[str, ...] = ()
    completed_range_ids: tuple[str, ...] = ()
    completed_element_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version not in {
            "stage-view-coverage.v1",
            "stage-view-coverage.v2",
        }:
            raise ValueError(f"unsupported StageView coverage: {self.schema_version}")
        if len(self.source_unit_ids) != len(set(self.source_unit_ids)):
            raise ValueError("source coverage identities must be unique")
        source_ids = set(self.source_unit_ids)
        if not set(self.visited_unit_ids).issubset(source_ids):
            raise ValueError("visited coverage must resolve to source units")
        if not set(self.selected_unit_ids).issubset(source_ids):
            raise ValueError("selected coverage must resolve to source units")
        if not set(self.cited_unit_ids).issubset(source_ids):
            raise ValueError("cited coverage must resolve to source units")
        if not set(self.critical_unit_ids).issubset(source_ids):
            raise ValueError("critical coverage must resolve to source units")
        range_ids = set(self.source_range_ids)
        element_ids = set(self.source_element_ids)
        if not set(self.critical_range_ids).issubset(range_ids):
            raise ValueError("critical range coverage must resolve to Source Plane ranges")
        if not set(self.critical_element_ids).issubset(element_ids):
            raise ValueError("critical element coverage must resolve to Source Plane elements")
        if not set(self.cited_range_ids).issubset(range_ids):
            raise ValueError("cited range coverage must resolve to Source Plane ranges")
        if not set(self.cited_element_ids).issubset(element_ids):
            raise ValueError("cited element coverage must resolve to Source Plane elements")
        if not set(self.visited_range_ids).issubset(range_ids):
            raise ValueError("visited range coverage must resolve to Source Plane ranges")
        if not set(self.selected_range_ids).issubset(range_ids):
            raise ValueError("selected range coverage must resolve to Source Plane ranges")
        if not set(self.presented_range_ids).issubset(range_ids):
            raise ValueError("presented range coverage must resolve to Source Plane ranges")
        if not set(self.visited_element_ids).issubset(element_ids):
            raise ValueError("visited element coverage must resolve to Source Plane elements")
        if not set(self.selected_element_ids).issubset(element_ids):
            raise ValueError("selected element coverage must resolve to Source Plane elements")
        if not set(self.presented_element_ids).issubset(element_ids):
            raise ValueError("presented element coverage must resolve to Source Plane elements")
        if not set(self.completed_unit_ids).issubset(source_ids):
            raise ValueError("completed unit coverage must resolve to source units")
        if not set(self.completed_range_ids).issubset(range_ids):
            raise ValueError("completed range coverage must resolve to Source Plane ranges")
        if not set(self.completed_element_ids).issubset(element_ids):
            raise ValueError("completed element coverage must resolve to Source Plane elements")
        if self.schema_version == "stage-view-coverage.v2" and (
            len(self.source_range_ids) != len(range_ids)
            or len(self.source_element_ids) != len(element_ids)
        ):
            raise ValueError("Source Plane coverage identities must be unique")
        omitted_ids = [item.identity for item in self.omitted]
        if len(omitted_ids) != len(set(omitted_ids)):
            raise ValueError("each omitted identity requires exactly one reason")
        source_by_type = {
            "unit": source_ids,
            "range": range_ids,
            "element": element_ids,
        }
        if any(
            omission.identity not in source_by_type[omission.object_type]
            for omission in self.omitted
        ):
            raise ValueError("omitted coverage must resolve to its Source Plane type")
        if self.stage_input_complete and (
            not set(self.critical_unit_ids).issubset(self.presented_identities)
            or not set(self.critical_range_ids).issubset(self.presented_range_ids)
            or not set(self.critical_element_ids).issubset(self.presented_element_ids)
        ):
            raise ValueError(
                "complete stage input must present every critical Source Plane identity"
            )


@dataclass(frozen=True, slots=True)
class StageViewBlockingRecord:
    source_unit_id: str | None
    reason: str
    estimated_tokens: int
    budget: int
    detail: str | None = None
    source_range_id: str | None = None
    source_element_id: str | None = None

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("blocking reason is required")
        if self.estimated_tokens < 0 or self.budget < 0:
            raise ValueError("blocking token values cannot be negative")
        identities = tuple(
            item
            for item in (
                self.source_unit_id,
                self.source_range_id,
                self.source_element_id,
            )
            if item is not None
        )
        if len(identities) > 1:
            raise ValueError("blocking record must name one Source Plane identity")

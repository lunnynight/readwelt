"""The bounded StageView aggregate."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.domain.reading import ReadingStage

from .coverage_models import StageViewBlockingRecord, StageViewCoverageManifest
from .evidence_models import (
    StageViewExternalEvidence,
    StageViewExternalEvidenceOmission,
)
from .graph_models import (
    SelectionReason,
    StageViewCapabilityOutcome,
    StageViewClaim,
    StageViewEdge,
    StageViewNode,
    StageViewUpstreamClaim,
)
from .navigation import StageViewContinuationCursor
from .source_models import (
    StageViewSourceElement,
    StageViewSourceRange,
    StageViewTextUnit,
)


@dataclass(frozen=True, slots=True)
class StageView:
    """Self-contained, bounded graph slice with traceability diagnostics."""

    schema_version: str
    snapshot_id: str
    stage: ReadingStage
    task_intent: str
    nodes: tuple[StageViewNode, ...]
    edges: tuple[StageViewEdge, ...]
    text_units: tuple[StageViewTextUnit, ...]
    upstream_claims: tuple[StageViewUpstreamClaim, ...]
    unresolved_conflict_ids: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    capability_outcomes: tuple[StageViewCapabilityOutcome, ...]
    coverage_complete: bool
    token_budget: int
    estimated_tokens: int
    selection_reasons: tuple[SelectionReason, ...]
    locator_backend: str | None
    fallback_backend: str | None
    graph_digest: str
    source_index_digest: str
    provenance_ledger_digest: str
    content_digest: str
    coverage: StageViewCoverageManifest | None = None
    continuation: StageViewContinuationCursor | None = None
    blocking_records: tuple[StageViewBlockingRecord, ...] = ()
    hard_serialized_token_budget: int | None = None
    source_ranges: tuple[StageViewSourceRange, ...] = ()
    source_elements: tuple[StageViewSourceElement, ...] = ()
    external_evidence: tuple[StageViewExternalEvidence, ...] = ()
    external_evidence_omissions: tuple[StageViewExternalEvidenceOmission, ...] = ()
    claim_candidates: tuple[StageViewClaim, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version not in {
            "stage-view.v1",
            "stage-view.v2",
            "stage-view.v3",
            "stage-view.v4",
        }:
            raise ValueError(f"unsupported StageView schema: {self.schema_version}")
        if self.estimated_tokens < 0 or self.estimated_tokens > self.token_budget:
            raise ValueError("StageView token estimate must fit its budget")
        for name, digest in (
            ("graph_digest", self.graph_digest),
            ("source_index_digest", self.source_index_digest),
            ("provenance_ledger_digest", self.provenance_ledger_digest),
            ("content_digest", self.content_digest),
        ):
            if not digest.startswith("sha256:"):
                raise ValueError(f"{name} must be a sha256 digest")
        if (
            self.schema_version
            in {
                "stage-view.v2",
                "stage-view.v3",
                "stage-view.v4",
            }
            and self.coverage is None
        ):
            raise ValueError("current StageView requires a coverage manifest")
        if self.hard_serialized_token_budget is not None and self.hard_serialized_token_budget < 1:
            raise ValueError("hard serialized budget must be positive")
        evidence_ids = tuple(item.evidence_id for item in self.external_evidence)
        omitted_ids = tuple(item.evidence_id for item in self.external_evidence_omissions)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("admitted external evidence ids must be unique")
        if len(omitted_ids) != len(set(omitted_ids)):
            raise ValueError("external evidence omission ids must be unique")
        if set(evidence_ids).intersection(omitted_ids):
            raise ValueError("external evidence cannot be both admitted and omitted")
        if self.stage in {ReadingStage.MAINLINE, ReadingStage.STRUCTURE} and evidence_ids:
            raise ValueError("article-only StageViews cannot admit external evidence")
        if any(item.stage_policy != self.stage.value for item in self.external_evidence):
            raise ValueError("external evidence admission belongs to another stage policy")

    @property
    def anchor_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(anchor_id for unit in self.text_units for anchor_id in unit.anchor_ids)
        )

    def to_mapping(self) -> dict[str, object]:
        """Return the compact provider-facing representation."""

        from .serialization import stage_view_mapping

        return stage_view_mapping(self)

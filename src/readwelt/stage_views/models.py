"""Immutable, explainable projections consumed by reading stages."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.domain.reading import ReadingStage


@dataclass(frozen=True, slots=True)
class StageContext:
    """Intent and budget that determine one stage projection."""

    stage: ReadingStage
    task_intent: str
    token_budget: int
    upstream_claim_ids: tuple[str, ...] = ()
    unresolved_gap_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_intent.strip():
            raise ValueError("task_intent is required")
        if self.token_budget < 0:
            raise ValueError("token_budget cannot be negative")


@dataclass(frozen=True, slots=True)
class StageViewNode:
    node_id: str
    kind: str
    label: str | None
    text: str | None
    epistemic_status: str
    source_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageViewEdge:
    edge_id: str
    relation: str
    source_node_id: str
    target_node_id: str
    epistemic_status: str
    source_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageViewTextUnit:
    unit_id: str
    kind: str
    text: str
    anchor_ids: tuple[str, ...]
    ordinal: int
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class StageViewUpstreamClaim:
    claim_id: str
    text: str
    decision: str
    anchor_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionReason:
    object_type: str
    object_id: str
    reason: str
    priority: int


@dataclass(frozen=True, slots=True)
class StageViewCapabilityOutcome:
    backend_id: str
    capability: str
    status: str
    message: str | None


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

    def __post_init__(self) -> None:
        if self.schema_version != "stage-view.v1":
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

    @property
    def anchor_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                anchor_id
                for unit in self.text_units
                for anchor_id in unit.anchor_ids
            )
        )

    def to_mapping(self) -> dict[str, object]:
        """Return the stable provider-facing representation."""

        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "stage": self.stage.value,
            "task_intent": self.task_intent,
            "nodes": [
                {
                    "node_id": item.node_id,
                    "kind": item.kind,
                    "label": item.label,
                    "text": item.text,
                    "epistemic_status": item.epistemic_status,
                    "source_unit_ids": list(item.source_unit_ids),
                }
                for item in self.nodes
            ],
            "edges": [
                {
                    "edge_id": item.edge_id,
                    "relation": item.relation,
                    "source_node_id": item.source_node_id,
                    "target_node_id": item.target_node_id,
                    "epistemic_status": item.epistemic_status,
                    "source_unit_ids": list(item.source_unit_ids),
                }
                for item in self.edges
            ],
            "text_units": [
                {
                    "unit_id": item.unit_id,
                    "kind": item.kind,
                    "text": item.text,
                    "anchor_ids": list(item.anchor_ids),
                    "ordinal": item.ordinal,
                    "estimated_tokens": item.estimated_tokens,
                }
                for item in self.text_units
            ],
            "upstream_claims": [
                {
                    "claim_id": item.claim_id,
                    "text": item.text,
                    "decision": item.decision,
                    "anchor_ids": list(item.anchor_ids),
                }
                for item in self.upstream_claims
            ],
            "unresolved_conflict_ids": list(self.unresolved_conflict_ids),
            "missing_capabilities": list(self.missing_capabilities),
            "capability_outcomes": [
                {
                    "backend_id": item.backend_id,
                    "capability": item.capability,
                    "status": item.status,
                    "message": item.message,
                }
                for item in self.capability_outcomes
            ],
            "coverage_complete": self.coverage_complete,
            "token_budget": self.token_budget,
            "estimated_tokens": self.estimated_tokens,
            "selection_reasons": [
                {
                    "object_type": item.object_type,
                    "object_id": item.object_id,
                    "reason": item.reason,
                    "priority": item.priority,
                }
                for item in self.selection_reasons
            ],
            "locator_backend": self.locator_backend,
            "fallback_backend": self.fallback_backend,
            "lineage": {
                "graph_digest": self.graph_digest,
                "source_index_digest": self.source_index_digest,
                "provenance_ledger_digest": self.provenance_ledger_digest,
            },
            "content_digest": self.content_digest,
        }

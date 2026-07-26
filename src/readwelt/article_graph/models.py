"""Canonical article knowledge objects and canonicalization audit records.

The raw extraction artifacts are durable facts.  These models are deterministic
projections over those facts; source mentions intentionally survive projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

ARTICLE_GRAPH_SCHEMA_VERSION = "article-graph.v2"


class EpistemicStatus(StrEnum):
    """How a knowledge object entered the knowledge space."""

    EXPLICIT = "explicit"
    LINGUISTIC_INFERENCE = "linguistic_inference"
    SEMANTIC_INFERENCE = "semantic_inference"
    CANONICALIZED = "canonicalized"
    INTERNAL_DERIVED = "internal_derived"
    EXTERNAL = "external"
    SYNTHESIZED = "synthesized"


class MergeOutcome(StrEnum):
    MERGE = "merge"
    KEEP_SEPARATE = "keep_separate"
    DEFER = "defer"
    REJECT = "reject"


class CanonicalizationPhase(StrEnum):
    IDENTITY_RESOLUTION = "identity_resolution"
    RELATION_RECONCILIATION = "relation_reconciliation"
    CLAIM_ASSEMBLY = "claim_assembly"


@dataclass(frozen=True, slots=True)
class Mention:
    """An addressable occurrence emitted by extraction, never erased by merging."""

    mention_id: str
    candidate_id: str
    kind: str
    label: str | None
    text: str | None
    epistemic_status: EpistemicStatus
    source_unit_ids: tuple[str, ...]
    confidence: float
    ambiguity: tuple[str, ...] = ()
    attributes: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.mention_id, "mention_id")
        _require_id(self.candidate_id, "candidate_id")
        _require_id(self.kind, "kind")
        _validate_confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class ArticleNode:
    node_id: str
    kind: str
    label: str | None
    epistemic_status: EpistemicStatus
    mention_ids: tuple[str, ...]
    source_unit_ids: tuple[str, ...]
    attributes: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.node_id, "node_id")
        _require_id(self.kind, "kind")
        if not self.mention_ids:
            raise ValueError("canonical node must retain at least one mention")


@dataclass(frozen=True, slots=True)
class ArticleEdge:
    edge_id: str
    relation: str
    source_node_id: str
    target_node_id: str
    epistemic_status: EpistemicStatus
    candidate_ids: tuple[str, ...]
    source_unit_ids: tuple[str, ...]
    confidence: float
    ambiguity: tuple[str, ...] = ()
    attributes: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.edge_id, "edge_id"),
            (self.relation, "relation"),
            (self.source_node_id, "source_node_id"),
            (self.target_node_id, "target_node_id"),
        ):
            _require_id(value, name)
        _validate_confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    text: str
    epistemic_status: EpistemicStatus
    mention_ids: tuple[str, ...]
    evidence_unit_ids: tuple[str, ...]
    subject_node_id: str | None = None
    predicate: str | None = None
    object_node_id: str | None = None
    confidence: float = 1.0
    ambiguity: tuple[str, ...] = ()
    attributes: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.claim_id, "claim_id")
        if not self.text.strip():
            raise ValueError("claim text is required")
        _validate_confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class MergeDecision:
    decision_id: str
    phase: CanonicalizationPhase
    outcome: MergeOutcome
    candidate_ids: tuple[str, ...]
    canonical_object_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    policy_id: str
    confidence: float
    content_digest: str

    def __post_init__(self) -> None:
        _require_id(self.decision_id, "decision_id")
        _require_id(self.policy_id, "policy_id")
        if not self.candidate_ids:
            raise ValueError("merge decision must identify candidates")
        if not self.reasons:
            raise ValueError("merge decision must include reasons")
        _validate_confidence(self.confidence)
        _validate_digest(self.content_digest)


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    conflict_id: str
    phase: CanonicalizationPhase
    candidate_ids: tuple[str, ...]
    reason: str
    evidence_refs: tuple[str, ...]
    decision_id: str
    resolution: str = "unresolved"
    content_digest: str = ""

    def __post_init__(self) -> None:
        _require_id(self.conflict_id, "conflict_id")
        _require_id(self.decision_id, "decision_id")
        if not self.reason.strip():
            raise ValueError("conflict reason is required")
        _validate_digest(self.content_digest)


@dataclass(frozen=True, slots=True)
class MergeReport:
    schema_version: str
    policy_id: str
    decisions: tuple[MergeDecision, ...]
    conflicts: tuple[ConflictRecord, ...]
    rejected_candidate_ids: tuple[str, ...]
    deferred_candidate_ids: tuple[str, ...]
    content_digest: str

    def __post_init__(self) -> None:
        _require_id(self.schema_version, "schema_version")
        _require_id(self.policy_id, "policy_id")
        _validate_digest(self.content_digest)


@dataclass(frozen=True, slots=True)
class ArticleGraph:
    schema_version: str
    snapshot_id: str
    mentions: tuple[Mention, ...]
    nodes: tuple[ArticleNode, ...]
    edges: tuple[ArticleEdge, ...]
    claims: tuple[Claim, ...]
    content_digest: str
    available_capabilities: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != ARTICLE_GRAPH_SCHEMA_VERSION:
            raise ValueError(f"unsupported article graph schema: {self.schema_version}")
        _require_id(self.snapshot_id, "snapshot_id")
        _validate_digest(self.content_digest)
        _require_unique((item.mention_id for item in self.mentions), "mention")
        _require_unique((item.node_id for item in self.nodes), "node")
        _require_unique((item.edge_id for item in self.edges), "edge")
        _require_unique((item.claim_id for item in self.claims), "claim")
        node_ids = {item.node_id for item in self.nodes}
        if any(
            edge.source_node_id not in node_ids or edge.target_node_id not in node_ids
            for edge in self.edges
        ):
            raise ValueError("article graph edges must reference known nodes")
        mention_ids = {item.mention_id for item in self.mentions}
        if any(set(node.mention_ids) - mention_ids for node in self.nodes):
            raise ValueError("canonical nodes must reference known mentions")
        if any(set(claim.mention_ids) - mention_ids for claim in self.claims):
            raise ValueError("claims must reference known mentions")


@dataclass(frozen=True, slots=True)
class CanonicalizationPolicy:
    """Versioned conservative policy; ambiguity is deferred, never guessed."""

    policy_id: str = "readwelt.canonicalization.conservative.v1"
    schema_version: str = "canonicalization-policy.v1"
    merge_confidence_threshold: float = 0.85
    source_required_kinds: tuple[str, ...] = (
        "claim",
        "concept",
        "entity",
        "event",
        "example",
        "objection",
        "qualification",
    )
    case_sensitive_identity: bool = False

    def __post_init__(self) -> None:
        _require_id(self.policy_id, "policy_id")
        _require_id(self.schema_version, "schema_version")
        _validate_confidence(self.merge_confidence_threshold)


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    graph: ArticleGraph
    merge_report: MergeReport


def _require_id(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")


def _validate_confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be between zero and one")


def _validate_digest(value: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("content digest must be a sha256 digest")


def _require_unique(values: Any, label: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{label} ids must be unique")

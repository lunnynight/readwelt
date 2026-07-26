"""Deep ArticleGraph build interface and artifact-lineage orchestration."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from statistics import fmean
from typing import Any, cast

from readwelt.article_ir import (
    DeterministicUnitizer,
    UnitizationResult,
)
from readwelt.domain.documents import SourceDocumentSnapshot
from readwelt.extraction import (
    BackendCapability,
    CapabilityOutcome,
    CapabilityStatus,
    DegradationReport,
    DeterministicLinguisticBackend,
    DeterministicSemanticExtractionBackend,
    ExtractionCoverage,
    ExtractionInput,
    GraphExtraction,
    LinguisticBackend,
    SemanticExtractionBackend,
)
from readwelt.extraction import (
    SourceReference as ExtractionSourceReference,
)
from readwelt.provenance import (
    ProducerIdentity,
    ProvenanceEventType,
    ProvenanceLedger,
    ProvenanceLedgerArtifact,
    SourceIndex,
)

from .canonicalizer import Canonicalizer
from .digest import content_digest, stable_identifier
from .models import (
    ArticleGraph,
    CanonicalizationPhase,
    CanonicalizationPolicy,
    EpistemicStatus,
    MergeDecision,
    MergeOutcome,
    MergeReport,
)

ARTICLE_GRAPH_BUILD_SCHEMA_VERSION = "article-graph-build.v1"


@dataclass(frozen=True, slots=True)
class ArticleGraphBuildPolicy:
    """Versioned orchestration policy; backend implementations stay internal."""

    schema_version: str = "article-graph-build-policy.v1"
    policy_id: str = "readwelt.article-graph-build.default.v1"
    run_linguistic_extraction: bool = True
    run_semantic_extraction: bool = True
    canonicalization: CanonicalizationPolicy = CanonicalizationPolicy()

    def __post_init__(self) -> None:
        if self.schema_version != "article-graph-build-policy.v1":
            raise ValueError(f"unsupported build policy schema: {self.schema_version}")
        if not self.policy_id.strip():
            raise ValueError("build policy id is required")
        if not (self.run_linguistic_extraction or self.run_semantic_extraction):
            raise ValueError("at least one extraction family must run")


@dataclass(frozen=True, slots=True)
class ArticleGraphCapabilityReport:
    schema_version: str
    outcomes: tuple[CapabilityOutcome, ...]
    available_capabilities: tuple[BackendCapability, ...]
    missing_capabilities: tuple[BackendCapability, ...]
    degraded: bool
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "article-graph-capability-report.v1":
            raise ValueError(f"unsupported capability report schema: {self.schema_version}")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("capability report digest must be sha256")


@dataclass(frozen=True, slots=True)
class GroundingFailure:
    failure_id: str
    extraction_id: str
    candidate_id: str
    candidate_kind: str
    claimed_unit_ids: tuple[str, ...]
    reason: str
    content_digest: str

    def __post_init__(self) -> None:
        if not self.failure_id or not self.candidate_id or not self.reason:
            raise ValueError("grounding failure identity and reason are required")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("grounding failure digest must be sha256")


@dataclass(frozen=True, slots=True)
class ArticleGraphBuildResult:
    """Durable facts plus rebuildable graph and source projections."""

    schema_version: str
    snapshot_id: str
    policy_id: str
    unitization: UnitizationResult
    extractions: tuple[GraphExtraction, ...]
    graph: ArticleGraph
    merge_report: MergeReport
    provenance_ledger: ProvenanceLedgerArtifact
    source_index: SourceIndex
    capability_report: ArticleGraphCapabilityReport
    grounding_failures: tuple[GroundingFailure, ...]
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != ARTICLE_GRAPH_BUILD_SCHEMA_VERSION:
            raise ValueError(f"unsupported graph build schema: {self.schema_version}")
        if self.unitization.snapshot_id != self.snapshot_id:
            raise ValueError("unitization belongs to a different snapshot")
        if any(item.snapshot_id != self.snapshot_id for item in self.extractions):
            raise ValueError("extraction belongs to a different snapshot")
        if self.graph.snapshot_id != self.snapshot_id:
            raise ValueError("graph belongs to a different snapshot")
        if self.source_index.graph_digest != self.graph.content_digest:
            raise ValueError("source index belongs to a different graph projection")
        if self.source_index.ledger_head_digest != self.provenance_ledger.head_digest:
            raise ValueError("source index belongs to a different provenance ledger")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("graph build digest must be sha256")


class ArticleGraphBuilder:
    """Build the full article IR behind one application-facing interface."""

    def __init__(
        self,
        *,
        unitizer: DeterministicUnitizer | None = None,
        linguistic_backends: Iterable[LinguisticBackend] | None = None,
        semantic_backends: Iterable[SemanticExtractionBackend] | None = None,
        canonicalizer: Canonicalizer | None = None,
    ) -> None:
        self._unitizer = unitizer or DeterministicUnitizer()
        self._linguistic_backends = tuple(
            linguistic_backends
            if linguistic_backends is not None
            else (DeterministicLinguisticBackend(),)
        )
        self._semantic_backends = tuple(
            semantic_backends
            if semantic_backends is not None
            else (DeterministicSemanticExtractionBackend(),)
        )
        self._canonicalizer = canonicalizer or Canonicalizer()

    def build(
        self,
        snapshot: SourceDocumentSnapshot,
        normalized_text: str,
        policy: ArticleGraphBuildPolicy | None = None,
    ) -> ArticleGraphBuildResult:
        selected_policy = policy or ArticleGraphBuildPolicy()
        actual_digest = f"sha256:{hashlib.sha256(normalized_text.encode()).hexdigest()}"
        if actual_digest != snapshot.content_digest:
            raise ValueError(f"normalized text digest mismatch: {snapshot.snapshot_id}")

        unitization = self._unitizer.unitize(snapshot, normalized_text)
        inputs = _extraction_inputs(unitization)
        extractions: list[GraphExtraction] = []
        if selected_policy.run_linguistic_extraction:
            extractions.extend(
                _extract_or_failure(backend, inputs, snapshot)
                for backend in self._linguistic_backends
            )
        if selected_policy.run_semantic_extraction:
            extractions.extend(
                _extract_or_failure(backend, inputs, snapshot)
                for backend in self._semantic_backends
            )
        if not extractions:
            raise ValueError("selected build policy produced no extraction artifacts")

        canonical_inputs, grounding_failures = _canonical_inputs(
            extractions,
            frozenset(unit.unit_id for unit in unitization.units),
        )
        canonical = self._canonicalizer.canonicalize(
            cast(Any, canonical_inputs),
            selected_policy.canonicalization,
        )
        merge_report = _record_grounding_failures(
            canonical.merge_report,
            grounding_failures,
            selected_policy.canonicalization,
        )
        capability_report = _capability_report(extractions)
        ledger = _build_ledger(
            snapshot,
            unitization,
            extractions,
            canonical.graph,
            merge_report,
            grounding_failures,
        )
        source_index = SourceIndex.rebuild(
            canonical.graph,
            ledger,
            merge_report,
        )
        ledger_artifact = ledger.to_artifact()
        payload = {
            "schema_version": ARTICLE_GRAPH_BUILD_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "policy_id": selected_policy.policy_id,
            "unitization_digest": unitization.content_digest,
            "extraction_digests": tuple(item.content_digest for item in extractions),
            "graph_digest": canonical.graph.content_digest,
            "merge_report_digest": merge_report.content_digest,
            "provenance_ledger_digest": ledger_artifact.content_digest,
            "source_index_digest": source_index.content_digest,
            "capability_report_digest": capability_report.content_digest,
            "grounding_failure_digests": tuple(
                failure.content_digest for failure in grounding_failures
            ),
        }
        return ArticleGraphBuildResult(
            schema_version=ARTICLE_GRAPH_BUILD_SCHEMA_VERSION,
            snapshot_id=snapshot.snapshot_id,
            policy_id=selected_policy.policy_id,
            unitization=unitization,
            extractions=tuple(extractions),
            graph=canonical.graph,
            merge_report=merge_report,
            provenance_ledger=ledger_artifact,
            source_index=source_index,
            capability_report=capability_report,
            grounding_failures=grounding_failures,
            content_digest=content_digest(payload),
        )


def _extraction_inputs(unitization: UnitizationResult) -> tuple[ExtractionInput, ...]:
    return tuple(
        ExtractionInput(
            document_id=unit.document_id,
            snapshot_id=unit.snapshot_id,
            unit_id=unit.unit_id,
            text=unit.exact_text,
            source_references=tuple(
                ExtractionSourceReference(
                    unit_id=unit.unit_id,
                    reference_id=reference.reference_id,
                    start_offset=reference.start_offset,
                    end_offset=reference.end_offset,
                    exact_text=reference.exact_text,
                )
                for reference in unit.source_references
            ),
        )
        for unit in unitization.units
    )


def _extract_or_failure(
    backend: LinguisticBackend | SemanticExtractionBackend,
    inputs: tuple[ExtractionInput, ...],
    snapshot: SourceDocumentSnapshot,
) -> GraphExtraction:
    try:
        return backend.extract(inputs)
    except Exception as exc:
        descriptor = backend.descriptor
        outcomes = tuple(
            CapabilityOutcome(
                capability=capability,
                status=CapabilityStatus.FAILED,
                input_unit_ids=tuple(item.unit_id for item in inputs),
                message=f"{type(exc).__name__}: {exc}",
            )
            for capability in descriptor.supported_capabilities
        )
        coverage = ExtractionCoverage(
            input_unit_ids=tuple(item.unit_id for item in inputs),
            covered_unit_ids=(),
            uncovered_unit_ids=tuple(item.unit_id for item in inputs),
        )
        return GraphExtraction(
            schema_version="graph-extraction.v1",
            extraction_id=stable_identifier(
                "graph_extraction",
                snapshot.snapshot_id,
                descriptor.backend_id,
                "failed",
                type(exc).__name__,
                str(exc),
            ),
            document_id=snapshot.document_id,
            snapshot_id=snapshot.snapshot_id,
            backend=descriptor,
            input_unit_ids=coverage.input_unit_ids,
            candidate_nodes=(),
            candidate_edges=(),
            outcomes=outcomes,
            coverage=coverage,
            degradation=DegradationReport.from_outcomes(outcomes),
            warnings=(f"backend failed: {type(exc).__name__}: {exc}",),
        )


def _canonical_inputs(
    extractions: Iterable[GraphExtraction],
    valid_unit_ids: frozenset[str],
) -> tuple[tuple[dict[str, object], ...], tuple[GroundingFailure, ...]]:
    views: list[dict[str, object]] = []
    failures: list[GroundingFailure] = []
    for extraction in extractions:
        admitted_nodes = []
        admitted_node_ids: set[str] = set()
        for candidate in extraction.candidate_nodes:
            invalid = set(candidate.source_unit_ids) - valid_unit_ids
            if invalid or not candidate.source_unit_ids:
                failures.append(
                    _grounding_failure(
                        extraction.extraction_id,
                        candidate.candidate_id,
                        candidate.kind,
                        candidate.source_unit_ids,
                        "unknown_source_unit" if invalid else "missing_source_unit",
                    )
                )
                continue
            admitted_nodes.append(candidate)
            admitted_node_ids.add(candidate.candidate_id)
        admitted_edges = []
        for edge_candidate in extraction.candidate_edges:
            invalid = set(edge_candidate.source_unit_ids) - valid_unit_ids
            endpoints_valid = (
                edge_candidate.source_candidate_id in admitted_node_ids
                and edge_candidate.target_candidate_id in admitted_node_ids
            )
            if invalid or not edge_candidate.source_unit_ids or not endpoints_valid:
                failures.append(
                    _grounding_failure(
                        extraction.extraction_id,
                        edge_candidate.candidate_id,
                        f"relation:{edge_candidate.relation}",
                        edge_candidate.source_unit_ids,
                        (
                            "unknown_source_unit"
                            if invalid
                            else "missing_or_rejected_endpoint"
                        ),
                    )
                )
                continue
            admitted_edges.append(edge_candidate)
        views.append(
            {
                "extraction_id": extraction.extraction_id,
                "snapshot_id": extraction.snapshot_id,
                "candidate_nodes": tuple(admitted_nodes),
                "candidate_edges": tuple(admitted_edges),
                "outcomes": extraction.outcomes,
            }
        )
    return tuple(views), tuple(sorted(failures, key=lambda item: item.failure_id))


def _grounding_failure(
    extraction_id: str,
    candidate_id: str,
    candidate_kind: str,
    claimed_unit_ids: Iterable[str],
    reason: str,
) -> GroundingFailure:
    claimed = tuple(sorted(set(claimed_unit_ids)))
    payload = (extraction_id, candidate_id, candidate_kind, claimed, reason)
    return GroundingFailure(
        failure_id=stable_identifier("grounding_failure", *payload),
        extraction_id=extraction_id,
        candidate_id=candidate_id,
        candidate_kind=candidate_kind,
        claimed_unit_ids=claimed,
        reason=reason,
        content_digest=content_digest(payload),
    )


def _record_grounding_failures(
    report: MergeReport,
    failures: tuple[GroundingFailure, ...],
    policy: CanonicalizationPolicy,
) -> MergeReport:
    decisions = list(report.decisions)
    for failure in failures:
        phase = (
            CanonicalizationPhase.RELATION_RECONCILIATION
            if failure.candidate_kind.startswith("relation:")
            else CanonicalizationPhase.IDENTITY_RESOLUTION
        )
        payload = {
            "phase": phase,
            "outcome": MergeOutcome.REJECT,
            "candidate_ids": (failure.candidate_id,),
            "reasons": (f"grounding:{failure.reason}",),
            "evidence_refs": failure.claimed_unit_ids,
            "policy_id": policy.policy_id,
            "confidence": 0.0,
        }
        decisions.append(
            MergeDecision(
                decision_id=stable_identifier(
                    "merge_decision",
                    failure.failure_id,
                    policy.policy_id,
                ),
                phase=phase,
                outcome=MergeOutcome.REJECT,
                candidate_ids=(failure.candidate_id,),
                canonical_object_ids=(),
                reasons=(f"grounding:{failure.reason}",),
                evidence_refs=failure.claimed_unit_ids,
                policy_id=policy.policy_id,
                confidence=0.0,
                content_digest=content_digest(payload),
            )
        )
    settled_decisions = tuple(sorted(decisions, key=lambda item: item.decision_id))
    rejected = tuple(
        sorted(
            {
                *report.rejected_candidate_ids,
                *(failure.candidate_id for failure in failures),
            }
        )
    )
    report_payload = {
        "schema_version": report.schema_version,
        "policy_id": report.policy_id,
        "decisions": settled_decisions,
        "conflicts": report.conflicts,
        "rejected_candidate_ids": rejected,
        "deferred_candidate_ids": report.deferred_candidate_ids,
    }
    return replace(
        report,
        decisions=settled_decisions,
        rejected_candidate_ids=rejected,
        content_digest=content_digest(report_payload),
    )


def _capability_report(
    extractions: Iterable[GraphExtraction],
) -> ArticleGraphCapabilityReport:
    outcomes = tuple(
        sorted(
            (outcome for extraction in extractions for outcome in extraction.outcomes),
            key=lambda item: (item.capability.value, item.status.value, item.input_unit_ids),
        )
    )
    by_capability: dict[BackendCapability, set[CapabilityStatus]] = {}
    for outcome in outcomes:
        by_capability.setdefault(outcome.capability, set()).add(outcome.status)
    available_statuses = {
        CapabilityStatus.COMPLETE,
        CapabilityStatus.EMPTY,
        CapabilityStatus.PARTIAL,
    }
    available = tuple(
        sorted(
            (
                capability
                for capability, statuses in by_capability.items()
                if statuses & available_statuses
            ),
            key=lambda item: item.value,
        )
    )
    missing = tuple(
        sorted(
            (capability for capability in BackendCapability if capability not in available),
            key=lambda item: item.value,
        )
    )
    degraded = bool(missing) or any(
        outcome.status in {CapabilityStatus.FAILED, CapabilityStatus.PARTIAL}
        for outcome in outcomes
    )
    payload = (
        "article-graph-capability-report.v1",
        outcomes,
        available,
        missing,
        degraded,
    )
    return ArticleGraphCapabilityReport(
        schema_version="article-graph-capability-report.v1",
        outcomes=outcomes,
        available_capabilities=available,
        missing_capabilities=missing,
        degraded=degraded,
        content_digest=content_digest(payload),
    )


def _build_ledger(
    snapshot: SourceDocumentSnapshot,
    unitization: UnitizationResult,
    extractions: Iterable[GraphExtraction],
    graph: ArticleGraph,
    merge_report: MergeReport,
    grounding_failures: tuple[GroundingFailure, ...],
) -> ProvenanceLedger:
    ledger = ProvenanceLedger()
    timestamp = snapshot.captured_at.isoformat()
    unitizer_producer = ProducerIdentity(
        producer_id="readwelt.article-ir.unitizer",
        producer_version="1",
        schema_version=unitization.schema_version,
    )
    ledger.append(
        ProvenanceEventType.UNITIZATION,
        producer=unitizer_producer,
        epistemic_status=EpistemicStatus.EXPLICIT,
        inputs=(snapshot.content_digest,),
        outputs=(unitization.content_digest, *(unit.unit_id for unit in unitization.units)),
        source_refs=(
            reference.reference_id
            for unit in unitization.units
            for reference in unit.source_references
        ),
        payload={"coverage_digest": unitization.coverage.content_digest},
        timestamp=timestamp,
    )

    settled_extractions = tuple(extractions)
    for extraction in settled_extractions:
        producer = ProducerIdentity(
            producer_id=extraction.backend.backend_id,
            producer_version=extraction.backend.version,
            schema_version=extraction.schema_version,
            model_id=extraction.backend.name,
            model_revision=extraction.backend.model_revision,
        )
        status = (
            EpistemicStatus.LINGUISTIC_INFERENCE
            if any(
                capability
                in {
                    BackendCapability.SENTENCE,
                    BackendCapability.TOKEN,
                    BackendCapability.POS,
                    BackendCapability.NER,
                    BackendCapability.DEPENDENCY,
                    BackendCapability.SRL,
                    BackendCapability.COREFERENCE,
                }
                for capability in extraction.backend.supported_capabilities
            )
            else EpistemicStatus.SEMANTIC_INFERENCE
        )
        candidates: tuple[Any, ...] = (
            *extraction.candidate_nodes,
            *extraction.candidate_edges,
        )
        candidate_ids = tuple(item.candidate_id for item in candidates)
        confidence_values = tuple(item.confidence.score for item in candidates)
        ledger.append(
            ProvenanceEventType.EXTRACTION,
            producer=producer,
            epistemic_status=status,
            inputs=(unitization.content_digest, *extraction.input_unit_ids),
            outputs=(extraction.content_digest, *candidate_ids),
            source_refs=tuple(
                dict.fromkeys(unit_id for item in candidates for unit_id in item.source_unit_ids)
            ),
            confidence=fmean(confidence_values) if confidence_values else 1.0,
            ambiguity=tuple(
                ambiguity.reason for item in candidates for ambiguity in item.ambiguity
            ),
            payload={
                "backend_id": extraction.backend.backend_id,
                "coverage_complete": extraction.coverage.complete,
                "degraded": extraction.degradation.degraded,
            },
            timestamp=timestamp,
        )
    grounding_producer = ProducerIdentity(
        producer_id="readwelt.article-graph.grounding-gate",
        producer_version="1",
        schema_version="grounding-gate.v1",
    )
    for failure in grounding_failures:
        ledger.append(
            ProvenanceEventType.GROUNDING,
            producer=grounding_producer,
            epistemic_status=EpistemicStatus.SEMANTIC_INFERENCE,
            inputs=(failure.extraction_id, failure.candidate_id),
            outputs=(failure.failure_id,),
            source_refs=(),
            confidence=0.0,
            ambiguity=(failure.reason,),
            payload={
                "candidate_kind": failure.candidate_kind,
                "claimed_unit_ids": failure.claimed_unit_ids,
                "result": "rejected",
            },
            timestamp=timestamp,
        )

    canonical_producer = ProducerIdentity(
        producer_id="readwelt.article-graph.canonicalizer",
        producer_version="1",
        schema_version=graph.schema_version,
    )
    ledger.append(
        ProvenanceEventType.CANONICALIZATION,
        producer=canonical_producer,
        epistemic_status=EpistemicStatus.CANONICALIZED,
        inputs=tuple(item.content_digest for item in settled_extractions),
        outputs=(
            graph.content_digest,
            *(node.node_id for node in graph.nodes),
            *(edge.edge_id for edge in graph.edges),
            *(claim.claim_id for claim in graph.claims),
            *(decision.decision_id for decision in merge_report.decisions),
        ),
        source_refs=tuple(
            dict.fromkeys(
                unit_id
                for collection in (graph.nodes, graph.edges)
                for item in collection
                for unit_id in item.source_unit_ids
            )
        ),
        payload={
            "merge_report_digest": merge_report.content_digest,
            "policy_id": merge_report.policy_id,
        },
        timestamp=timestamp,
    )
    for conflict in merge_report.conflicts:
        ledger.append(
            ProvenanceEventType.CONFLICT,
            producer=canonical_producer,
            epistemic_status=EpistemicStatus.CANONICALIZED,
            inputs=conflict.candidate_ids,
            outputs=(conflict.conflict_id,),
            source_refs=conflict.evidence_refs,
            confidence=0.0,
            ambiguity=(conflict.reason,),
            payload={"decision_id": conflict.decision_id},
            timestamp=timestamp,
        )
    ledger.append(
        ProvenanceEventType.PROJECTION,
        producer=ProducerIdentity(
            producer_id="readwelt.provenance.source-index",
            producer_version="1",
            schema_version="source-index.v1",
        ),
        epistemic_status=EpistemicStatus.CANONICALIZED,
        inputs=(graph.content_digest, ledger.head_digest),
        outputs=(stable_identifier("source_index", graph.content_digest),),
        payload={"projection": "knowledge-source-bidirectional"},
        timestamp=timestamp,
    )
    return ledger

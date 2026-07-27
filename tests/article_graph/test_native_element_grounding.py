from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from readwelt.article_graph import ArticleGraphBuilder, GroundingReferenceKind
from readwelt.domain import (
    DocumentSection,
    ReadingStage,
    SourceDocumentSnapshot,
    SourceElement,
    SpanAnchor,
)
from readwelt.extraction import (
    BackendCapability,
    BackendDescriptor,
    CandidateEdge,
    CandidateNode,
    CapabilityOutcome,
    CapabilityStatus,
    ConfidenceAssessment,
    DegradationReport,
    ExtractionCoverage,
    ExtractionEpistemicStatus,
    ExtractionInput,
    GraphExtraction,
    NetworkBehavior,
    SourceGrounding,
)
from readwelt.extraction.models import SourceReference, _json_value
from readwelt.provenance import ProvenanceEventType
from readwelt.stage_views import StageContext, StageViewProjector


class _KnownElementOnlyBackend:
    def __init__(self, snapshot: SourceDocumentSnapshot, element_id: str) -> None:
        self._snapshot = snapshot
        self._element_id = element_id

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id=f"test.element-only.{self._element_id}",
            name="known element-only grounding test backend",
            version="2",
            model_revision=None,
            supported_capabilities=(BackendCapability.CLAIM,),
            license_name="MIT",
            network_behavior=NetworkBehavior.NONE,
            deterministic=True,
        )

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction:
        source = SourceReference(element_id=self._element_id)
        candidate = CandidateNode(
            candidate_id=f"candidate:{self._element_id}",
            kind="claim",
            label=None,
            text=f"Claim grounded in {self._element_id}",
            grounding=SourceGrounding((source,)),
            confidence=ConfidenceAssessment(1.0, "test_fixture"),
            epistemic_status=ExtractionEpistemicStatus.EXPLICIT,
        )
        evidence = CandidateNode(
            candidate_id=f"candidate:{self._element_id}:evidence",
            kind="evidence",
            label="native evidence",
            text=None,
            grounding=SourceGrounding((source,)),
            confidence=ConfidenceAssessment(1.0, "test_fixture"),
            epistemic_status=ExtractionEpistemicStatus.EXPLICIT,
        )
        edge = CandidateEdge(
            candidate_id=f"edge:{self._element_id}",
            relation="support",
            source_candidate_id=evidence.candidate_id,
            target_candidate_id=candidate.candidate_id,
            grounding=SourceGrounding((source,)),
            confidence=ConfidenceAssessment(1.0, "test_fixture"),
            epistemic_status=ExtractionEpistemicStatus.EXPLICIT,
        )
        unit_ids = tuple(item.unit_id for item in inputs)
        outcome = CapabilityOutcome(
            capability=BackendCapability.CLAIM,
            status=CapabilityStatus.COMPLETE,
            input_unit_ids=unit_ids,
            covered_unit_ids=(),
            candidate_count=1,
        )
        return GraphExtraction(
            schema_version="graph-extraction.v2",
            extraction_id=f"extraction:{self._element_id}",
            document_id=self._snapshot.document_id,
            snapshot_id=self._snapshot.snapshot_id,
            backend=self.descriptor,
            input_unit_ids=unit_ids,
            candidate_nodes=(candidate, evidence),
            candidate_edges=(edge,),
            outcomes=(outcome,),
            coverage=ExtractionCoverage(
                input_unit_ids=unit_ids,
                covered_unit_ids=(),
                uncovered_unit_ids=unit_ids,
            ),
            degradation=DegradationReport.from_outcomes((outcome,)),
        )


class _UnknownNativeElementBackend:
    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id="test.unknown-native-element",
            name="unknown native element test backend",
            version="1",
            model_revision=None,
            supported_capabilities=(BackendCapability.CLAIM,),
            license_name="MIT",
            network_behavior=NetworkBehavior.NONE,
            deterministic=True,
        )

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction:
        source = SourceReference(element_id="native-element:missing")
        candidate = CandidateNode(
            candidate_id="candidate:unknown-native-element",
            kind="claim",
            label=None,
            text=inputs[0].text,
            grounding=SourceGrounding((source,)),
            confidence=ConfidenceAssessment(1.0, "test_fixture"),
            epistemic_status=ExtractionEpistemicStatus.EXPLICIT,
        )
        unit_ids = tuple(item.unit_id for item in inputs)
        outcome = CapabilityOutcome(
            capability=BackendCapability.CLAIM,
            status=CapabilityStatus.COMPLETE,
            input_unit_ids=unit_ids,
            covered_unit_ids=unit_ids,
            candidate_count=1,
        )
        return GraphExtraction(
            schema_version="graph-extraction.v2",
            extraction_id="extraction:unknown-native-element",
            document_id=inputs[0].document_id,
            snapshot_id=inputs[0].snapshot_id,
            backend=self.descriptor,
            input_unit_ids=unit_ids,
            candidate_nodes=(candidate,),
            candidate_edges=(),
            outcomes=(outcome,),
            coverage=ExtractionCoverage(
                input_unit_ids=unit_ids,
                covered_unit_ids=unit_ids,
                uncovered_unit_ids=(),
            ),
            degradation=DegradationReport.from_outcomes((outcome,)),
        )


def _snapshot(text: str) -> SourceDocumentSnapshot:
    snapshot_id = "snapshot:unknown-native-element"
    section_id = "section:1"
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id="document:unknown-native-element",
        schema_version="1",
        source_kind="text/plain",
        source_locator="source.txt",
        content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        language="en",
        normalized_text_ref="objects/source.txt",
        sections=(
            DocumentSection(
                section_id=section_id,
                title=None,
                start_offset=0,
                end_offset=len(text),
                anchor=SpanAnchor.create(
                    snapshot_id=snapshot_id,
                    section_id=section_id,
                    text=text,
                    start_offset=0,
                    end_offset=len(text),
                ),
            ),
        ),
    )


def test_unknown_native_element_is_diagnostic_only_and_creates_no_source_edge() -> None:
    text = "A source-grounded candidate names an unknown native element."
    build = ArticleGraphBuilder(
        linguistic_backends=(),
        semantic_backends=(_UnknownNativeElementBackend(),),
    ).build(_snapshot(text), text)

    raw_candidate = build.extractions[0].candidate_nodes[0]
    assert raw_candidate.grounding.source_references[0].element_id == ("native-element:missing")
    assert build.graph.nodes == ()
    assert build.graph.edges == ()
    assert build.graph.claims == ()
    assert build.source_index.node_to_units == ()
    assert build.source_index.units_for_element("native-element:missing") == ()

    failure = build.grounding_failures[0]
    assert failure.candidate_id == raw_candidate.candidate_id
    assert failure.reference_kind is GroundingReferenceKind.SOURCE_ELEMENT
    assert failure.reason == "unknown_source_element"
    assert failure.claimed_element_ids == ("native-element:missing",)
    assert failure.claimed_unit_ids == ()

    grounding_event = next(
        event
        for event in build.provenance_ledger.events
        if event.event_type is ProvenanceEventType.GROUNDING
    )
    assert grounding_event.source_refs == ()
    payload = dict(grounding_event.payload)
    assert payload["reference_kind"] == "source_element"
    assert payload["claimed_element_ids"] == ["native-element:missing"]
    rejection = next(
        decision
        for decision in build.merge_report.decisions
        if raw_candidate.candidate_id in decision.candidate_ids
    )
    assert rejection.canonical_object_ids == ()


def test_absent_native_element_preserves_historical_v1_digest_shape() -> None:
    historical = SourceReference(unit_id="unit:1", reference_id="reference:1")
    native = replace(historical, element_id="native-element:1")

    historical_payload = _json_value(historical)
    native_payload = _json_value(native)

    assert "element_id" not in historical_payload
    assert native_payload["element_id"] == "native-element:1"


@pytest.mark.parametrize("kind", ("table", "figure", "scan_root"))
def test_known_element_only_grounding_survives_every_projection_without_fake_unit(
    kind: str,
) -> None:
    text = "正文没有对应这个原生元素的文本单元。"
    base = _snapshot(text)
    element_id = f"native:{kind}:1"
    snapshot = replace(
        base,
        source_elements=(
            SourceElement(
                element_id=element_id,
                snapshot_id=base.snapshot_id,
                schema_version="source-element.v1",
                ordinal=0,
                reading_order=0,
                projection_status="preserved",
                kind=kind,
                page=1,
                native_reference=element_id,
                raw_payload_ref=f"objects/{kind}.json",
            ),
        ),
    )
    build = ArticleGraphBuilder(
        linguistic_backends=(),
        semantic_backends=(_KnownElementOnlyBackend(snapshot, element_id),),
    ).build(snapshot, text)

    assert build.schema_version == "article-graph-build.v2"
    assert build.extractions[0].schema_version == "graph-extraction.v2"
    assert build.graph.schema_version == "article-graph.v4"
    assert build.source_index.schema_version == "source-index.v3"
    assert build.grounding_failures == ()

    mention = next(item for item in build.graph.mentions if item.kind == "claim")
    node = next(item for item in build.graph.nodes if item.kind == "claim")
    edge = build.graph.edges[0]
    claim = build.graph.claims[0]
    assert mention.source_unit_ids == node.source_unit_ids == ()
    assert claim.evidence_unit_ids == ()
    assert mention.source_element_ids == node.source_element_ids == (element_id,)
    assert claim.evidence_element_ids == (element_id,)
    assert edge.source_unit_ids == ()
    assert edge.source_element_ids == (element_id,)
    assert build.source_index.elements_for_node(node.node_id) == (element_id,)
    assert build.source_index.elements_for_edge(edge.edge_id) == (element_id,)
    assert build.source_index.evidence_elements_for_claim(claim.claim_id) == (element_id,)
    knowledge = build.source_index.knowledge_for_element(element_id)
    assert node.node_id in knowledge.node_ids
    assert knowledge.edge_ids == (edge.edge_id,)
    assert knowledge.claim_ids == (claim.claim_id,)

    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="locate element-only claim",
            token_budget=2_000,
            rescue_level="section",
        ),
    )
    projected = next(item for item in view.nodes if item.node_id == node.node_id)
    assert projected.source_unit_ids == ()
    assert projected.source_element_ids == (element_id,)
    projected_edge = next(item for item in view.edges if item.edge_id == edge.edge_id)
    assert projected_edge.source_unit_ids == ()
    assert projected_edge.source_element_ids == (element_id,)
    assert any(item.element_id == element_id for item in view.source_elements)
    mapping = view.to_mapping()
    serialized = next(item for item in mapping["nodes"] if item["node_id"] == node.node_id)
    assert serialized["source_unit_ids"] == []
    assert serialized["source_element_ids"] == [element_id]

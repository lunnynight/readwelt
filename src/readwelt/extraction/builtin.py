"""Dependency-free, deterministic fallback extraction backends."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (
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
    SourceReference,
    stable_id,
)

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_SENTENCE_PATTERN = re.compile(r"\S(?:.*?)(?:[.!?。！？]+(?=\s|$)|$)", re.DOTALL)

_LINGUISTIC_CAPABILITIES = tuple(
    capability
    for capability in BackendCapability
    if capability
    in {
        BackendCapability.SENTENCE,
        BackendCapability.TOKEN,
        BackendCapability.POS,
        BackendCapability.NER,
        BackendCapability.DEPENDENCY,
        BackendCapability.SRL,
        BackendCapability.COREFERENCE,
    }
)
_SEMANTIC_CAPABILITIES = tuple(
    capability for capability in BackendCapability if capability not in _LINGUISTIC_CAPABILITIES
)


@dataclass(frozen=True, slots=True)
class DeterministicLinguisticBackend:
    """Regex sentence/token fallback; richer linguistic capabilities stay explicit gaps."""

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id="readwelt.linguistic.regex",
            name="Readwelt deterministic regex linguistic fallback",
            version="1",
            model_revision=None,
            supported_capabilities=(
                BackendCapability.SENTENCE,
                BackendCapability.TOKEN,
            ),
            license_name="MIT",
            network_behavior=NetworkBehavior.NONE,
            deterministic=True,
        )

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction:
        nodes: list[CandidateNode] = []
        edges: list[CandidateEdge] = []
        covered: list[str] = []
        sentence_count = 0
        token_count = 0

        for item in inputs:
            if not item.text.strip():
                continue
            covered.append(item.unit_id)
            unit_grounding = _grounding(item)
            for sentence_index, match in enumerate(_SENTENCE_PATTERN.finditer(item.text)):
                sentence_text = match.group(0)
                sentence_id = stable_id(
                    "candidate",
                    self.descriptor.backend_id,
                    item.unit_id,
                    "sentence",
                    str(sentence_index),
                )
                sentence_grounding = _match_grounding(
                    item,
                    match.start(),
                    match.end(),
                    sentence_text,
                )
                nodes.append(
                    CandidateNode(
                        candidate_id=sentence_id,
                        kind="sentence",
                        label=None,
                        text=sentence_text,
                        grounding=sentence_grounding,
                        confidence=ConfidenceAssessment(1.0, "deterministic_regex"),
                        epistemic_status=ExtractionEpistemicStatus.LINGUISTIC_INFERENCE,
                    )
                )
                sentence_count += 1
                for token_index, token_match in enumerate(_TOKEN_PATTERN.finditer(sentence_text)):
                    token_text = token_match.group(0)
                    token_id = stable_id(
                        "candidate",
                        self.descriptor.backend_id,
                        item.unit_id,
                        "sentence",
                        str(sentence_index),
                        "token",
                        str(token_index),
                    )
                    start = match.start() + token_match.start()
                    end = match.start() + token_match.end()
                    nodes.append(
                        CandidateNode(
                            candidate_id=token_id,
                            kind="token",
                            label=token_text,
                            text=token_text,
                            grounding=_match_grounding(item, start, end, token_text),
                            confidence=ConfidenceAssessment(1.0, "deterministic_regex"),
                            epistemic_status=(
                                ExtractionEpistemicStatus.LINGUISTIC_INFERENCE
                            ),
                        )
                    )
                    edges.append(
                        CandidateEdge(
                            candidate_id=stable_id("candidate-edge", sentence_id, token_id),
                            relation="contains",
                            source_candidate_id=sentence_id,
                            target_candidate_id=token_id,
                            grounding=unit_grounding,
                            confidence=ConfidenceAssessment(1.0, "deterministic_structure"),
                            epistemic_status=(
                                ExtractionEpistemicStatus.LINGUISTIC_INFERENCE
                            ),
                        )
                    )
                    token_count += 1

        unit_ids = tuple(item.unit_id for item in inputs)
        covered_ids = tuple(covered)
        outcomes = _outcomes(
            _LINGUISTIC_CAPABILITIES,
            self.descriptor.supported_capabilities,
            unit_ids,
            covered_ids,
            {
                BackendCapability.SENTENCE: sentence_count,
                BackendCapability.TOKEN: token_count,
            },
        )
        return _artifact(
            backend=self.descriptor,
            inputs=inputs,
            nodes=tuple(nodes),
            edges=tuple(edges),
            outcomes=outcomes,
        )


@dataclass(frozen=True, slots=True)
class DeterministicSemanticExtractionBackend:
    """Conservative fallback preserving each non-empty unit as an explicit claim candidate."""

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id="readwelt.semantic.explicit-unit",
            name="Readwelt deterministic explicit-unit semantic fallback",
            version="1",
            model_revision=None,
            supported_capabilities=(BackendCapability.CLAIM,),
            license_name="MIT",
            network_behavior=NetworkBehavior.NONE,
            deterministic=True,
        )

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction:
        nodes: list[CandidateNode] = []
        covered: list[str] = []
        for item in inputs:
            if not item.text.strip():
                continue
            covered.append(item.unit_id)
            nodes.append(
                CandidateNode(
                    candidate_id=stable_id(
                        "candidate", self.descriptor.backend_id, item.unit_id, "claim"
                    ),
                    kind="claim",
                    label=None,
                    text=item.text,
                    grounding=_grounding(item),
                    confidence=ConfidenceAssessment(1.0, "source_unit_identity"),
                    epistemic_status=ExtractionEpistemicStatus.EXPLICIT,
                )
            )

        unit_ids = tuple(item.unit_id for item in inputs)
        covered_ids = tuple(covered)
        outcomes = _outcomes(
            _SEMANTIC_CAPABILITIES,
            self.descriptor.supported_capabilities,
            unit_ids,
            covered_ids,
            {BackendCapability.CLAIM: len(nodes)},
        )
        return _artifact(
            backend=self.descriptor,
            inputs=inputs,
            nodes=tuple(nodes),
            edges=(),
            outcomes=outcomes,
        )


def _grounding(item: ExtractionInput) -> SourceGrounding:
    references = item.source_references or (
        SourceReference(
            unit_id=item.unit_id,
            start_offset=0,
            end_offset=len(item.text),
            exact_text=item.text,
        ),
    )
    return SourceGrounding(source_references=references, exact=True)


def _match_grounding(
    item: ExtractionInput, start: int, end: int, exact_text: str
) -> SourceGrounding:
    return SourceGrounding(
        source_references=(
            SourceReference(
                unit_id=item.unit_id,
                start_offset=start,
                end_offset=end,
                exact_text=exact_text,
            ),
        ),
        exact=True,
    )


def _outcomes(
    domain_capabilities: tuple[BackendCapability, ...],
    supported: tuple[BackendCapability, ...],
    input_ids: tuple[str, ...],
    covered_ids: tuple[str, ...],
    counts: dict[BackendCapability, int],
) -> tuple[CapabilityOutcome, ...]:
    outcomes: list[CapabilityOutcome] = []
    for capability in domain_capabilities:
        if capability not in supported:
            status = CapabilityStatus.UNSUPPORTED
            capability_covered: tuple[str, ...] = ()
        else:
            status = (
                CapabilityStatus.COMPLETE
                if counts.get(capability, 0)
                else CapabilityStatus.EMPTY
            )
            capability_covered = covered_ids
        outcomes.append(
            CapabilityOutcome(
                capability=capability,
                status=status,
                input_unit_ids=input_ids,
                covered_unit_ids=capability_covered,
                candidate_count=counts.get(capability, 0),
            )
        )
    return tuple(outcomes)


def _artifact(
    *,
    backend: BackendDescriptor,
    inputs: tuple[ExtractionInput, ...],
    nodes: tuple[CandidateNode, ...],
    edges: tuple[CandidateEdge, ...],
    outcomes: tuple[CapabilityOutcome, ...],
) -> GraphExtraction:
    if not inputs:
        raise ValueError("an extraction invocation requires at least one input unit")
    source_identities = {(item.document_id, item.snapshot_id) for item in inputs}
    if len(source_identities) != 1:
        raise ValueError("all extraction input units must share document and snapshot identity")
    document_id, snapshot_id = next(iter(source_identities))
    input_ids = tuple(item.unit_id for item in inputs)
    covered_ids = tuple(item.unit_id for item in inputs if item.text.strip())
    uncovered_ids = tuple(item.unit_id for item in inputs if not item.text.strip())
    coverage = ExtractionCoverage(input_ids, covered_ids, uncovered_ids)
    extraction_id = stable_id(
        "extraction",
        backend.backend_id,
        backend.version,
        document_id,
        snapshot_id,
        *(f"{item.unit_id}:{item.text}" for item in inputs),
    )
    return GraphExtraction(
        schema_version="graph-extraction.v1",
        extraction_id=extraction_id,
        document_id=document_id,
        snapshot_id=snapshot_id,
        backend=backend,
        input_unit_ids=input_ids,
        candidate_nodes=nodes,
        candidate_edges=edges,
        outcomes=outcomes,
        coverage=coverage,
        degradation=DegradationReport.from_outcomes(outcomes),
    )

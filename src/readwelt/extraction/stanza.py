"""Optional production adapter for Stanza's Simplified Chinese pipeline.

The module stays importable without the optional dependency. Constructing the
backend loads only an already-installed Stanza runtime and an already-downloaded
model directory; Readwelt never performs an implicit network download.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from readwelt.extraction.models import (
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
from readwelt.extraction.taxonomy import ARGUMENT_TAXONOMY_SCHEMA_VERSION

_CAPABILITIES = (
    BackendCapability.SENTENCE,
    BackendCapability.TOKEN,
    BackendCapability.POS,
    BackendCapability.NER,
    BackendCapability.DEPENDENCY,
    BackendCapability.SRL,
    BackendCapability.COREFERENCE,
)


@dataclass(slots=True)
class StanzaLinguisticBackend:
    """Thin adapter over a pre-downloaded Stanza Simplified Chinese pipeline."""

    model_dir: Path
    pipeline: Any | None = field(default=None, repr=False)
    _pipeline: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.pipeline is not None:
            self._pipeline = self.pipeline
            return
        stanza: Any = import_module("stanza")

        self._pipeline = stanza.Pipeline(
            "zh-hans",
            processors="tokenize,pos,lemma,ner,depparse",
            model_dir=str(self.model_dir),
            use_gpu=False,
            verbose=False,
            download_method=None,
        )

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id="stanza.zh-hans",
            name="Stanza Simplified Chinese linguistic pipeline",
            version="1.14.0",
            model_revision="stanfordnlp/stanza-zh-hans@v1.14.0",
            supported_capabilities=(
                BackendCapability.SENTENCE,
                BackendCapability.TOKEN,
                BackendCapability.POS,
                BackendCapability.NER,
                BackendCapability.DEPENDENCY,
            ),
            required_resources=("stanfordnlp/stanza-zh-hans@v1.14.0",),
            license_name="Apache-2.0",
            license_url="https://huggingface.co/stanfordnlp/stanza-zh-hans",
            network_behavior=NetworkBehavior.NONE,
            deterministic=True,
            metadata={
                "model_license": "Apache-2.0",
                "processors": "tokenize,pos,lemma,ner,depparse",
            },
            taxonomy_schema_version=ARGUMENT_TAXONOMY_SCHEMA_VERSION,
            emitted_candidate_kinds=("stanza:sentence", "stanza:token", "entity"),
            emitted_relations=("stanza:contains", "stanza:dependency"),
        )

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction:
        if not inputs:
            raise ValueError("an extraction invocation requires at least one input unit")
        source_identities = {(item.document_id, item.snapshot_id) for item in inputs}
        if len(source_identities) != 1:
            raise ValueError("all extraction inputs must share document and snapshot identity")

        nodes: list[CandidateNode] = []
        edges: list[CandidateEdge] = []
        counts = {capability: 0 for capability in self.descriptor.supported_capabilities}
        covered_ids: list[str] = []

        for item in inputs:
            if not item.text.strip():
                continue
            covered_ids.append(item.unit_id)
            document = self._pipeline(item.text)
            for sentence_index, sentence in enumerate(document.sentences):
                sentence_start = min(token.start_char for token in sentence.tokens)
                sentence_end = max(token.end_char for token in sentence.tokens)
                sentence_text = item.text[sentence_start:sentence_end]
                sentence_id = stable_id(
                    "candidate",
                    self.descriptor.backend_id,
                    item.unit_id,
                    "sentence",
                    str(sentence_index),
                )
                nodes.append(
                    _node(
                        sentence_id,
                        "stanza:sentence",
                        sentence_text,
                        item,
                        sentence_start,
                        sentence_end,
                    )
                )
                counts[BackendCapability.SENTENCE] += 1

                word_nodes: dict[int, str] = {}
                for token_index, token in enumerate(sentence.tokens):
                    token_id = stable_id(
                        "candidate",
                        self.descriptor.backend_id,
                        item.unit_id,
                        "sentence",
                        str(sentence_index),
                        "token",
                        str(token_index),
                    )
                    words = tuple(token.words)
                    attributes = tuple(
                        sorted(
                            {
                                ("lemma", str(words[0].lemma or "")),
                                ("upos", str(words[0].upos or "")),
                                ("xpos", str(words[0].xpos or "")),
                            }
                        )
                    )
                    nodes.append(
                        _node(
                            token_id,
                            "stanza:token",
                            token.text,
                            item,
                            token.start_char,
                            token.end_char,
                            label=token.text,
                            attributes=attributes,
                        )
                    )
                    edges.append(
                        _edge(
                            "stanza:contains",
                            sentence_id,
                            token_id,
                            item,
                            token.start_char,
                            token.end_char,
                        )
                    )
                    for word in words:
                        word_nodes[int(word.id)] = token_id
                    counts[BackendCapability.TOKEN] += 1
                    counts[BackendCapability.POS] += 1

                for word in sentence.words:
                    if not word.head:
                        continue
                    source_id = word_nodes.get(int(word.head))
                    target_id = word_nodes.get(int(word.id))
                    if source_id is None or target_id is None:
                        continue
                    token = next(token for token in sentence.tokens if word in token.words)
                    edges.append(
                        _edge(
                            "stanza:dependency",
                            source_id,
                            target_id,
                            item,
                            token.start_char,
                            token.end_char,
                        )
                    )
                    counts[BackendCapability.DEPENDENCY] += 1

            for entity_index, entity in enumerate(document.ents):
                entity_id = stable_id(
                    "candidate",
                    self.descriptor.backend_id,
                    item.unit_id,
                    "entity",
                    str(entity_index),
                )
                nodes.append(
                    _node(
                        entity_id,
                        "entity",
                        entity.text,
                        item,
                        entity.start_char,
                        entity.end_char,
                        label=entity.type,
                        attributes=(("ner_type", entity.type),),
                    )
                )
                counts[BackendCapability.NER] += 1

        input_ids = tuple(item.unit_id for item in inputs)
        covered = tuple(covered_ids)
        uncovered = tuple(item.unit_id for item in inputs if item.unit_id not in covered)
        outcomes = tuple(
            _outcome(capability, input_ids, covered, counts) for capability in _CAPABILITIES
        )
        document_id, snapshot_id = next(iter(source_identities))
        extraction_id = stable_id(
            "extraction",
            self.descriptor.backend_id,
            self.descriptor.version,
            document_id,
            snapshot_id,
            *(f"{item.unit_id}:{item.text}" for item in inputs),
        )
        return GraphExtraction(
            schema_version="graph-extraction.v3",
            extraction_id=extraction_id,
            document_id=document_id,
            snapshot_id=snapshot_id,
            backend=self.descriptor,
            input_unit_ids=input_ids,
            candidate_nodes=tuple(nodes),
            candidate_edges=tuple(edges),
            outcomes=outcomes,
            coverage=ExtractionCoverage(input_ids, covered, uncovered),
            degradation=DegradationReport.from_outcomes(outcomes),
        )


def _node(
    candidate_id: str,
    kind: str,
    text: str,
    item: ExtractionInput,
    start: int,
    end: int,
    *,
    label: str | None = None,
    attributes: tuple[tuple[str, str], ...] = (),
) -> CandidateNode:
    return CandidateNode(
        candidate_id=candidate_id,
        kind=kind,
        label=label,
        text=text,
        grounding=_grounding(item, start, end),
        confidence=ConfidenceAssessment(1.0, "stanza_model_output"),
        epistemic_status=ExtractionEpistemicStatus.LINGUISTIC_INFERENCE,
        attributes=attributes,
    )


def _edge(
    relation: str,
    source_id: str,
    target_id: str,
    item: ExtractionInput,
    start: int,
    end: int,
) -> CandidateEdge:
    return CandidateEdge(
        candidate_id=stable_id(
            "candidate-edge",
            relation,
            source_id,
            target_id,
            str(start),
            str(end),
        ),
        relation=relation,
        source_candidate_id=source_id,
        target_candidate_id=target_id,
        grounding=_grounding(item, start, end),
        confidence=ConfidenceAssessment(1.0, "stanza_model_output"),
        epistemic_status=ExtractionEpistemicStatus.LINGUISTIC_INFERENCE,
    )


def _grounding(item: ExtractionInput, start: int, end: int) -> SourceGrounding:
    reference_id = (
        item.source_references[0].reference_id if len(item.source_references) == 1 else None
    )
    return SourceGrounding(
        source_references=(
            SourceReference(
                unit_id=item.unit_id,
                reference_id=reference_id,
                start_offset=start,
                end_offset=end,
                exact_text=item.text[start:end],
            ),
        ),
        exact=True,
    )


def _outcome(
    capability: BackendCapability,
    input_ids: tuple[str, ...],
    covered_ids: tuple[str, ...],
    counts: dict[BackendCapability, int],
) -> CapabilityOutcome:
    if capability not in counts:
        return CapabilityOutcome(
            capability=capability,
            status=CapabilityStatus.UNSUPPORTED,
            input_unit_ids=input_ids,
        )
    count = counts[capability]
    return CapabilityOutcome(
        capability=capability,
        status=CapabilityStatus.COMPLETE if count else CapabilityStatus.EMPTY,
        input_unit_ids=input_ids,
        covered_unit_ids=covered_ids,
        candidate_count=count,
    )

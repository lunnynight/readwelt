"""Pluggable extraction seams and immutable raw candidate artifacts."""

from .builtin import (
    DeterministicLinguisticBackend,
    DeterministicSemanticExtractionBackend,
)
from .models import (
    Ambiguity,
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
    UnresolvedReference,
    graph_extraction_digest,
    stable_id,
)
from .protocols import LinguisticBackend, SemanticExtractionBackend
from .registry import (
    BackendAlreadyRegisteredError,
    BackendNotFoundError,
    LinguisticBackendRegistry,
    SemanticExtractionBackendRegistry,
)

__all__ = [
    "Ambiguity",
    "BackendAlreadyRegisteredError",
    "BackendCapability",
    "BackendDescriptor",
    "BackendNotFoundError",
    "CandidateEdge",
    "CandidateNode",
    "CapabilityOutcome",
    "CapabilityStatus",
    "ConfidenceAssessment",
    "DegradationReport",
    "DeterministicLinguisticBackend",
    "DeterministicSemanticExtractionBackend",
    "ExtractionCoverage",
    "ExtractionEpistemicStatus",
    "ExtractionInput",
    "GraphExtraction",
    "LinguisticBackend",
    "LinguisticBackendRegistry",
    "NetworkBehavior",
    "SemanticExtractionBackend",
    "SemanticExtractionBackendRegistry",
    "SourceGrounding",
    "SourceReference",
    "UnresolvedReference",
    "graph_extraction_digest",
    "stable_id",
]

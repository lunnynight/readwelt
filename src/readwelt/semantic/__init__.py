"""Public deterministic semantic preprocessing facade."""

from readwelt.semantic.models import (
    CoverageManifest,
    EmbeddingDescriptor,
    OmittedEvidence,
    SegmentStatistics,
    SemanticAtlas,
    SemanticEvidencePacket,
    SemanticSegment,
    UncoveredRange,
)
from readwelt.semantic.packet_builder import build_evidence_packet
from readwelt.semantic.preprocessor import SemanticPreprocessor
from readwelt.semantic.protocol import EmbeddingAdapter

__all__ = [
    "CoverageManifest",
    "EmbeddingAdapter",
    "EmbeddingDescriptor",
    "OmittedEvidence",
    "SemanticAtlas",
    "SemanticEvidencePacket",
    "SemanticPreprocessor",
    "SemanticSegment",
    "SegmentStatistics",
    "UncoveredRange",
    "build_evidence_packet",
]

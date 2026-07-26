"""Public deterministic semantic preprocessing facade."""

from readwelt.domain.reading import RetrievalHit
from readwelt.semantic.local_dense import (
    DEFAULT_DENSE_MODEL,
    SentenceTransformerDenseEncoder,
    configured_dense_encoder,
)
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
from readwelt.semantic.protocol import DenseEncoder, EmbeddingAdapter
from readwelt.semantic.retrieval import (
    HybridRetriever,
    RetrievalPlan,
    build_stage_retrieval_plan,
)

__all__ = [
    "CoverageManifest",
    "configured_dense_encoder",
    "DEFAULT_DENSE_MODEL",
    "DenseEncoder",
    "EmbeddingAdapter",
    "EmbeddingDescriptor",
    "OmittedEvidence",
    "RetrievalHit",
    "RetrievalPlan",
    "SemanticAtlas",
    "SemanticEvidencePacket",
    "SemanticPreprocessor",
    "SemanticSegment",
    "SentenceTransformerDenseEncoder",
    "SegmentStatistics",
    "UncoveredRange",
    "build_evidence_packet",
    "build_stage_retrieval_plan",
    "HybridRetriever",
]

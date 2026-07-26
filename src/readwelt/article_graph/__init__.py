"""Canonical ArticleGraph trust-plane projection."""

from .builder import (
    ARTICLE_GRAPH_BUILD_SCHEMA_VERSION,
    ArticleGraphBuilder,
    ArticleGraphBuildPolicy,
    ArticleGraphBuildResult,
    ArticleGraphCapabilityReport,
    GroundingFailure,
)
from .canonicalizer import Canonicalizer
from .models import (
    ARTICLE_GRAPH_SCHEMA_VERSION,
    ArticleEdge,
    ArticleGraph,
    ArticleNode,
    CanonicalizationPhase,
    CanonicalizationPolicy,
    CanonicalizationResult,
    Claim,
    ConflictRecord,
    EpistemicStatus,
    Mention,
    MergeDecision,
    MergeOutcome,
    MergeReport,
)
from .protocols import (
    CandidateEdgeLike,
    CandidateNodeLike,
    ExtractionInput,
    GraphExtractionLike,
)

__all__ = [
    "ARTICLE_GRAPH_SCHEMA_VERSION",
    "ARTICLE_GRAPH_BUILD_SCHEMA_VERSION",
    "ArticleEdge",
    "ArticleGraph",
    "ArticleGraphBuilder",
    "ArticleGraphBuildPolicy",
    "ArticleGraphBuildResult",
    "ArticleGraphCapabilityReport",
    "GroundingFailure",
    "ArticleNode",
    "CandidateEdgeLike",
    "CandidateNodeLike",
    "CanonicalizationPhase",
    "CanonicalizationPolicy",
    "CanonicalizationResult",
    "Canonicalizer",
    "Claim",
    "ConflictRecord",
    "EpistemicStatus",
    "ExtractionInput",
    "GraphExtractionLike",
    "Mention",
    "MergeDecision",
    "MergeOutcome",
    "MergeReport",
]

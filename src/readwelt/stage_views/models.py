"""Stable compatibility facade for StageView data contracts."""

from .coverage_models import (
    CoverageOmission,
    OmissionReason,
    StageViewBlockingRecord,
    StageViewCoverageManifest,
)
from .evidence_models import (
    StageViewExternalEvidence,
    StageViewExternalEvidenceOmission,
)
from .graph_models import (
    SelectionReason,
    StageViewCapabilityOutcome,
    StageViewClaim,
    StageViewConfidenceSource,
    StageViewEdge,
    StageViewNode,
    StageViewUpstreamClaim,
)
from .navigation import (
    ElementTraversalPosition,
    StageContext,
    StageViewContinuationCursor,
    TraversalPosition,
)
from .source_models import (
    StageViewSourceElement,
    StageViewSourceRange,
    StageViewTextUnit,
)
from .view_model import StageView

__all__ = [
    "CoverageOmission",
    "ElementTraversalPosition",
    "OmissionReason",
    "SelectionReason",
    "StageContext",
    "StageView",
    "StageViewBlockingRecord",
    "StageViewCapabilityOutcome",
    "StageViewClaim",
    "StageViewConfidenceSource",
    "StageViewContinuationCursor",
    "StageViewCoverageManifest",
    "StageViewEdge",
    "StageViewExternalEvidence",
    "StageViewExternalEvidenceOmission",
    "StageViewNode",
    "StageViewSourceElement",
    "StageViewSourceRange",
    "StageViewTextUnit",
    "StageViewUpstreamClaim",
    "TraversalPosition",
]

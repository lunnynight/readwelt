"""Public contracts for Readwelt's source-anchored article IR."""

from .models import (
    ARTICLE_SOURCE_PLANE_SCHEMA_VERSION,
    HISTORICAL_UNITIZATION_SCHEMA_VERSION,
    AnchoredTextUnit,
    CoverageRecord,
    CoverageReport,
    CoverageScope,
    CoverageStatus,
    SourcePlaneCoverageManifest,
    SourceRangeKind,
    SourceRangeRecord,
    SourceReference,
    UnitizationResult,
)
from .unitizer import DeterministicUnitizer, unitize_snapshot

__all__ = [
    "ARTICLE_SOURCE_PLANE_SCHEMA_VERSION",
    "AnchoredTextUnit",
    "CoverageRecord",
    "CoverageReport",
    "CoverageScope",
    "CoverageStatus",
    "DeterministicUnitizer",
    "HISTORICAL_UNITIZATION_SCHEMA_VERSION",
    "SourceReference",
    "SourceRangeKind",
    "SourceRangeRecord",
    "SourcePlaneCoverageManifest",
    "UnitizationResult",
    "unitize_snapshot",
]

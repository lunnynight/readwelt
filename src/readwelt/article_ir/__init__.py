"""Public contracts for Readwelt's source-anchored article IR."""

from .models import (
    AnchoredTextUnit,
    CoverageRecord,
    CoverageReport,
    CoverageScope,
    CoverageStatus,
    SourceReference,
    UnitizationResult,
)
from .unitizer import DeterministicUnitizer, unitize_snapshot

__all__ = [
    "AnchoredTextUnit",
    "CoverageRecord",
    "CoverageReport",
    "CoverageScope",
    "CoverageStatus",
    "DeterministicUnitizer",
    "SourceReference",
    "UnitizationResult",
    "unitize_snapshot",
]

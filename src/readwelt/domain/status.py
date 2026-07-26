"""Independent runtime, knowledge, model and publication statuses."""

from enum import StrEnum


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EpistemicStatus(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    UNDERDETERMINED = "underdetermined"
    INVALID = "invalid"


class ModelStatus(StrEnum):
    NOT_USED = "not_used"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


class PublicationStatus(StrEnum):
    WITHHELD = "withheld"
    INTERNAL = "internal"
    PUBLISHABLE_WITH_WARNINGS = "publishable_with_warnings"
    PUBLISHABLE = "publishable"

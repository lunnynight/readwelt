"""Content-addressed artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    schema_version: str
    content_digest: str
    path: str
    size: int
    status: ArtifactStatus = ArtifactStatus.COMPLETED

    def __post_init__(self) -> None:
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("content_digest must be a sha256 digest")
        if not self.path.startswith("objects/"):
            raise ValueError("artifact path must be project-relative")
        if self.size < 0:
            raise ValueError("artifact size cannot be negative")

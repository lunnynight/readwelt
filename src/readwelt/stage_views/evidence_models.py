"""External evidence contracts admitted by StageView policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StageViewExternalEvidence:
    """External evidence explicitly admitted by one StageView policy."""

    evidence_id: str
    content: str
    selection_reason: str
    provenance: tuple[tuple[str, str], ...]
    stage_policy: str
    schema_version: str = "stage-view-external-evidence.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "stage-view-external-evidence.v1":
            raise ValueError(f"unsupported StageView external evidence: {self.schema_version}")
        if not self.evidence_id or not self.content.strip():
            raise ValueError("admitted external evidence requires identity and content")
        if not self.selection_reason or not self.stage_policy:
            raise ValueError("external evidence admission requires policy and reason")
        if not self.provenance:
            raise ValueError("external evidence admission requires provenance")


@dataclass(frozen=True, slots=True)
class StageViewExternalEvidenceOmission:
    evidence_id: str
    reason: str
    detail: str | None = None
    schema_version: str = "stage-view-external-evidence-omission.v1"

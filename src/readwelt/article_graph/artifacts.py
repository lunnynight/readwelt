"""Compact persisted contracts for ArticleGraph build lineage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from readwelt.domain import ArtifactRef

if TYPE_CHECKING:
    from .builder import ArticleGraphBuildResult


ARTICLE_GRAPH_BUILD_ARTIFACT_SCHEMA_VERSION = "article-graph-build-artifact.v2"


@dataclass(frozen=True, slots=True)
class ArticleGraphArtifactReference:
    role: str
    artifact_type: str
    schema_version: str
    content_digest: str
    size: int

    @classmethod
    def from_artifact_ref(
        cls,
        role: str,
        reference: ArtifactRef,
    ) -> ArticleGraphArtifactReference:
        return cls(
            role=role,
            artifact_type=reference.artifact_type,
            schema_version=reference.schema_version,
            content_digest=reference.content_digest,
            size=reference.size,
        )

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.artifact_type.strip():
            raise ValueError("artifact reference role and type are required")
        if not self.schema_version.strip():
            raise ValueError("artifact reference schema version is required")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("artifact reference digest must be sha256")
        if self.size < 0:
            raise ValueError("artifact reference size cannot be negative")


@dataclass(frozen=True, slots=True)
class ArticleGraphCapabilitySummary:
    available: tuple[str, ...]
    missing: tuple[str, ...]
    degraded: bool
    report_digest: str

    def __post_init__(self) -> None:
        if not self.report_digest.startswith("sha256:"):
            raise ValueError("capability report digest must be sha256")
        if set(self.available) & set(self.missing):
            raise ValueError("capabilities cannot be both available and missing")


@dataclass(frozen=True, slots=True)
class ArticleGraphBuildArtifact:
    """Reference-only persisted aggregate for one ArticleGraph build."""

    schema_version: str
    build_schema_version: str
    snapshot_id: str
    policy_id: str
    build_digest: str
    references: tuple[ArticleGraphArtifactReference, ...]
    capability_summary: ArticleGraphCapabilitySummary
    grounding_failure_digests: tuple[str, ...]

    @classmethod
    def from_build(
        cls,
        build: ArticleGraphBuildResult,
        references: tuple[ArtifactRef, ...],
    ) -> ArticleGraphBuildArtifact:
        expected_roles_and_types = (
            ("unitization", "anchored_text_unitization"),
            *(
                (f"extraction:{extraction.backend.backend_id}", "graph_extraction")
                for extraction in build.extractions
            ),
            ("merge_report", "article_graph_merge_report"),
            ("provenance_ledger", "article_graph_provenance_ledger"),
            ("source_index", "article_graph_source_index"),
            ("graph", "article_graph"),
        )
        if len(references) != len(expected_roles_and_types):
            raise ValueError("graph build references do not match build components")
        links = tuple(
            ArticleGraphArtifactReference.from_artifact_ref(role, reference)
            for (role, expected_type), reference in zip(
                expected_roles_and_types,
                references,
                strict=True,
            )
            if _require_artifact_type(reference, expected_type)
        )
        return cls(
            schema_version=ARTICLE_GRAPH_BUILD_ARTIFACT_SCHEMA_VERSION,
            build_schema_version=build.schema_version,
            snapshot_id=build.snapshot_id,
            policy_id=build.policy_id,
            build_digest=build.content_digest,
            references=links,
            capability_summary=ArticleGraphCapabilitySummary(
                available=tuple(
                    sorted(
                        capability.value
                        for capability in build.capability_report.available_capabilities
                    )
                ),
                missing=tuple(
                    sorted(
                        capability.value
                        for capability in build.capability_report.missing_capabilities
                    )
                ),
                degraded=build.capability_report.degraded,
                report_digest=build.capability_report.content_digest,
            ),
            grounding_failure_digests=tuple(
                failure.content_digest for failure in build.grounding_failures
            ),
        )

    def __post_init__(self) -> None:
        if self.schema_version not in {
            "article-graph-build-artifact.v1",
            ARTICLE_GRAPH_BUILD_ARTIFACT_SCHEMA_VERSION,
        }:
            raise ValueError(f"unsupported graph build artifact schema: {self.schema_version}")
        if not self.build_schema_version.strip():
            raise ValueError("graph build schema version is required")
        if not self.snapshot_id.strip() or not self.policy_id.strip():
            raise ValueError("snapshot and policy ids are required")
        if not self.build_digest.startswith("sha256:"):
            raise ValueError("graph build digest must be sha256")
        roles = tuple(reference.role for reference in self.references)
        if len(roles) != len(set(roles)):
            raise ValueError("graph build artifact reference roles must be unique")
        if "graph" not in roles or "unitization" not in roles:
            raise ValueError("graph build artifact must reference graph and unitization")
        if any(not digest.startswith("sha256:") for digest in self.grounding_failure_digests):
            raise ValueError("grounding failure digests must be sha256")


def _require_artifact_type(reference: ArtifactRef, expected_type: str) -> bool:
    if reference.artifact_type != expected_type:
        raise ValueError(
            f"expected {expected_type} artifact reference, got {reference.artifact_type}"
        )
    return True

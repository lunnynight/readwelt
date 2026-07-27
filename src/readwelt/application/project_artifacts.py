"""Document preparation and immutable artifact access for the project facade."""

from __future__ import annotations

import base64
import hashlib
from typing import Protocol

from readwelt.article_graph import (
    ArticleGraphBuildArtifact,
    ArticleGraphBuilder,
    ArticleGraphBuildResult,
)
from readwelt.domain import ArtifactRef, ReadingRun, SourceDocumentSnapshot
from readwelt.runner import DocumentRunner
from readwelt.semantic import SemanticAtlas, SemanticPreprocessor
from readwelt.storage import ArtifactStore, ManifestStore, ProjectLayout


class ProjectArtifactHost(Protocol):
    _layout: ProjectLayout
    _runner: DocumentRunner
    _artifacts: ArtifactStore
    _manifests: ManifestStore
    _semantic: SemanticPreprocessor
    _article_graph: ArticleGraphBuilder


def prepare_document(
    service: ProjectArtifactHost,
    document_id: str,
) -> SemanticAtlas:
    snapshot = service._runner.get_snapshot(document_id)
    atlas, atlas_ref, graph_build, graph_refs = prepare_snapshot(service, snapshot)
    manifest_path = service._layout.document_manifest(snapshot.document_id)
    manifest = service._manifests.read(manifest_path)
    manifest["semantic_atlas"] = atlas
    manifest["semantic_atlas_artifact"] = atlas_ref
    manifest["article_graph"] = graph_build.graph
    manifest["article_graph_artifact"] = next(
        item for item in graph_refs if item.artifact_type == "article_graph"
    )
    manifest["article_graph_build_artifacts"] = graph_refs
    service._manifests.write(manifest_path, manifest)
    return atlas


def prepare_snapshot(
    service: ProjectArtifactHost,
    snapshot: SourceDocumentSnapshot,
) -> tuple[
    SemanticAtlas,
    ArtifactRef,
    ArticleGraphBuildResult,
    tuple[ArtifactRef, ...],
]:
    normalized_path = (service._layout.root / snapshot.normalized_text_ref).resolve()
    normalized_path.relative_to(service._layout.root)
    normalized_text = normalized_path.read_text(encoding="utf-8")
    digest = f"sha256:{hashlib.sha256(normalized_text.encode()).hexdigest()}"
    if digest != snapshot.content_digest:
        raise ValueError(f"normalized text digest mismatch: {snapshot.snapshot_id}")
    atlas = service._semantic.prepare(snapshot, normalized_text)
    atlas_ref = service._artifacts.put_json(
        atlas,
        artifact_type="semantic_atlas",
        schema_version=atlas.schema_version,
    )
    graph_build = service._article_graph.build(snapshot, normalized_text)
    graph_component_refs = (
        service._artifacts.put_json(
            graph_build.unitization,
            artifact_type="anchored_text_unitization",
            schema_version=graph_build.unitization.schema_version,
        ),
        *(
            service._artifacts.put_json(
                extraction,
                artifact_type="graph_extraction",
                schema_version=extraction.schema_version,
            )
            for extraction in graph_build.extractions
        ),
        service._artifacts.put_json(
            graph_build.merge_report,
            artifact_type="article_graph_merge_report",
            schema_version=graph_build.merge_report.schema_version,
        ),
        service._artifacts.put_json(
            graph_build.provenance_ledger,
            artifact_type="article_graph_provenance_ledger",
            schema_version=graph_build.provenance_ledger.schema_version,
        ),
        service._artifacts.put_json(
            graph_build.source_index,
            artifact_type="article_graph_source_index",
            schema_version=graph_build.source_index.schema_version,
        ),
        service._artifacts.put_json(
            graph_build.graph,
            artifact_type="article_graph",
            schema_version=graph_build.graph.schema_version,
        ),
    )
    graph_build_artifact = ArticleGraphBuildArtifact.from_build(
        graph_build,
        graph_component_refs,
    )
    graph_refs = (
        *graph_component_refs,
        service._artifacts.put_json(
            graph_build_artifact,
            artifact_type="article_graph_build",
            schema_version=graph_build_artifact.schema_version,
        ),
    )
    return atlas, atlas_ref, graph_build, graph_refs


def get_artifact(service: ProjectArtifactHost, digest: str) -> dict[str, object]:
    hexadecimal = digest.removeprefix("sha256:")
    if len(hexadecimal) != 64 or any(char not in "0123456789abcdefABCDEF" for char in hexadecimal):
        raise ValueError("artifact digest must be a sha256 hex digest")
    hexadecimal = hexadecimal.lower()
    path = (
        service._layout.root
        / "objects"
        / "sha256"
        / hexadecimal[:2]
        / hexadecimal[2:4]
        / hexadecimal
    ).resolve()
    path.relative_to(service._layout.root)
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != hexadecimal:
        raise ValueError(f"artifact digest mismatch: sha256:{hexadecimal}")
    result: dict[str, object] = {
        "digest": f"sha256:{hexadecimal}",
        "path": service._layout.relative(path),
        "size": len(content),
    }
    try:
        result["content"] = content.decode("utf-8")
        result["content_encoding"] = "utf-8"
    except UnicodeDecodeError:
        result["content"] = base64.b64encode(content).decode("ascii")
        result["content_encoding"] = "base64"
    return result


def validate_run_artifacts(service: ProjectArtifactHost, run: ReadingRun) -> None:
    for artifact in run.artifacts:
        try:
            service._artifacts.read_bytes(artifact)
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError(f"run artifact is missing or corrupt: {artifact.artifact_id}") from exc

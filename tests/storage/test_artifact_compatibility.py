from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from readwelt import ReadweltProject
from readwelt.article_graph import ArticleGraph
from readwelt.article_graph.digest import content_digest
from readwelt.article_ir import (
    ARTICLE_SOURCE_PLANE_SCHEMA_VERSION,
    UnitizationResult,
)
from readwelt.domain import ArtifactRef
from readwelt.provenance import SourceIndex
from readwelt.providers import StageRequest
from readwelt.stage_views import StageView
from readwelt.storage import ArtifactStore, ImmutableArtifactReader, ProjectLayout
from readwelt.storage.artifact_compatibility import (
    HistoricalArticleGraphBuildV1,
    HistoricalSourceIndexV1,
)
from tests.interfaces.fakes import DeterministicFakeProvider

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "artifact_compatibility"


def _candidate(request: StageRequest) -> dict[str, Any]:
    anchor_id = request.evidence_packet["anchors"][0]["anchor_id"]
    claim: dict[str, Any] = {
        "claim_id": f"{request.stage}:claim",
        "text": f"{request.stage} claim",
        "anchor_ids": [anchor_id],
        "decision": "accepted",
    }
    if request.stage not in ("stage_1_mainline", "stage_2_structure"):
        claim["source_claim_ids"] = [request.evidence_packet["upstream_claims"][0]["claim_id"]]
    if request.stage == "stage_4_author_model":
        claim["provenance"] = {"interpretation_id": "historical-lens"}
    candidate: dict[str, Any] = {"claims": [claim], "gaps": [], "warnings": []}
    if request.stage == "stage_3_decompression":
        candidate["decompression_units"] = [
            {
                "unit_id": "stage3-unit-0",
                "explanation": "The stage claim depends on the article's stated prerequisite.",
                "claim_ids": [claim["claim_id"]],
                "source_citations": [{"kind": "anchor", "identity": anchor_id}],
            }
        ]
    return candidate


@pytest.mark.parametrize(
    ("filename", "artifact_type", "schema_version", "compatibility", "decoded_type"),
    (
        (
            "anchored_text_unitization.v1.json",
            "anchored_text_unitization",
            "anchored-text-unitization.v1",
            "legacy",
            UnitizationResult,
        ),
        (
            "article_graph.v2.json",
            "article_graph",
            "article-graph.v2",
            "legacy",
            ArticleGraph,
        ),
        (
            "source_index.v1.json",
            "article_graph_source_index",
            "source-index.v1",
            "legacy",
            HistoricalSourceIndexV1,
        ),
        (
            "stage_view.v1.json",
            "stage_view",
            "stage-view.v1",
            "legacy",
            StageView,
        ),
        (
            "article_graph_build.v1.json",
            "article_graph_build",
            "article-graph-build.v1",
            "legacy",
            HistoricalArticleGraphBuildV1,
        ),
    ),
)
def test_historical_artifact_fixtures_remain_readable_without_rewrite(
    tmp_path: Path,
    filename: str,
    artifact_type: str,
    schema_version: str,
    compatibility: str,
    decoded_type: type[object],
) -> None:
    layout = ProjectLayout(tmp_path / "project")
    layout.initialize()
    store = ArtifactStore(layout)
    original = (_FIXTURES / filename).read_bytes()
    reference = store.put_bytes(
        original,
        artifact_type=artifact_type,
        schema_version=schema_version,
    )
    object_path = layout.root / reference.path
    before = object_path.read_bytes()
    before_mtime = object_path.stat().st_mtime_ns

    readable = ImmutableArtifactReader(store).read(reference)

    assert readable.schema_version == schema_version
    assert readable.compatibility == compatibility
    assert readable.payload["schema_version"] == schema_version
    assert isinstance(readable.decoded, decoded_type)
    assert object_path.read_bytes() == before == original
    assert object_path.stat().st_mtime_ns == before_mtime


def test_current_graph_artifacts_rebuild_deterministically_without_rewrite(
    tmp_path: Path,
) -> None:
    source = tmp_path / "article.txt"
    source.write_text("第一段提出问题。\n第二段给出证据。", encoding="utf-8")
    project = ReadweltProject(base_directory=tmp_path, ingestion_backend="plain_text")
    snapshot = project.import_document(source)

    project.prepare(snapshot.document_id)
    manifest_path = project.root / "documents" / snapshot.document_id / "manifest.json"
    first_manifest = project._manifests.read(manifest_path)
    first_refs = tuple(first_manifest["article_graph_build_artifacts"])
    before = {
        reference["content_digest"]: (
            (project.root / reference["path"]).read_bytes(),
            (project.root / reference["path"]).stat().st_mtime_ns,
        )
        for reference in first_refs
    }

    project.prepare(snapshot.document_id)
    second_manifest = project._manifests.read(manifest_path)
    second_refs = tuple(second_manifest["article_graph_build_artifacts"])

    assert tuple(item["content_digest"] for item in second_refs) == tuple(
        item["content_digest"] for item in first_refs
    )
    source_index = next(
        item for item in second_refs if item["artifact_type"] == "article_graph_source_index"
    )
    assert source_index["schema_version"] == "source-index.v3"
    source_plane = next(
        item for item in second_refs if item["artifact_type"] == "anchored_text_unitization"
    )
    assert source_plane["schema_version"] == ARTICLE_SOURCE_PLANE_SCHEMA_VERSION
    source_plane_ref = ArtifactRef(**source_plane)
    decoded = ImmutableArtifactReader(project._artifacts).read(source_plane_ref)
    assert decoded.schema_version == ARTICLE_SOURCE_PLANE_SCHEMA_VERSION
    assert isinstance(decoded.decoded, UnitizationResult)
    reader = ImmutableArtifactReader(project._artifacts)
    for item in second_refs:
        if item["artifact_type"] in {
            "anchored_text_unitization",
            "article_graph",
            "article_graph_build",
            "article_graph_source_index",
            "graph_extraction",
        }:
            reader.read(ArtifactRef(**item))
    for reference in first_refs:
        content, mtime = before[reference["content_digest"]]
        object_path = project.root / reference["path"]
        assert object_path.read_bytes() == content
        assert object_path.stat().st_mtime_ns == mtime


def test_semantic_reader_rejects_tampered_internal_digest(tmp_path: Path) -> None:
    layout = ProjectLayout(tmp_path / "project")
    layout.initialize()
    store = ArtifactStore(layout)
    payload = (
        (_FIXTURES / "article_graph.v2.json")
        .read_text(encoding="utf-8")
        .replace(
            '"content_digest":"sha256:2a6cda689d371b3415d86720a89e35dcf1cdfc7b2f2c16fffa7d95625b0a54bc"',
            '"content_digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000"',
            1,
        )
    )
    reference = store.put_text(
        payload,
        artifact_type="article_graph",
        schema_version="article-graph.v2",
    )

    with pytest.raises(ValueError, match="article graph content digest mismatch"):
        ImmutableArtifactReader(store).read(reference)


def test_historical_source_index_v2_reads_with_its_original_digest_shape(
    tmp_path: Path,
) -> None:
    source = tmp_path / "article.txt"
    source.write_text("历史索引仍须可验证。", encoding="utf-8")
    project = ReadweltProject(base_directory=tmp_path, ingestion_backend="plain_text")
    snapshot = project.import_document(source)
    project.prepare(snapshot.document_id)
    manifest = project._manifests.read(
        project.root / "documents" / snapshot.document_id / "manifest.json"
    )
    reference_payload = next(
        item
        for item in manifest["article_graph_build_artifacts"]
        if item["artifact_type"] == "article_graph_source_index"
    )
    current = json.loads((project.root / reference_payload["path"]).read_text(encoding="utf-8"))
    for field in (
        "node_to_elements",
        "edge_to_elements",
        "claim_to_evidence_elements",
        "element_to_nodes",
        "element_to_edges",
        "element_to_claims",
        "source_section_ids",
    ):
        current.pop(field)
    current["schema_version"] = "source-index.v2"
    current["content_digest"] = content_digest(
        {key: value for key, value in current.items() if key != "content_digest"}
    )
    reference = project._artifacts.put_text(
        json.dumps(current, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        artifact_type="article_graph_source_index",
        schema_version="source-index.v2",
    )

    readable = ImmutableArtifactReader(project._artifacts).read(reference)

    assert readable.compatibility == "legacy"
    assert isinstance(readable.decoded, SourceIndex)
    assert readable.decoded.schema_version == "source-index.v2"


def test_current_stage_views_and_application_artifacts_are_deterministic(
    tmp_path: Path,
) -> None:
    source = tmp_path / "article.txt"
    source.write_text("问题。\n证据。\n结论。", encoding="utf-8")
    project = ReadweltProject(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(DeterministicFakeProvider(_candidate),),
    )
    snapshot = project.import_document(source)

    first = project.read(snapshot.document_id, idempotency_key="compatibility-first")
    first_refs = tuple(
        item
        for item in first.artifacts
        if item.artifact_type in {"article_graph_build", "stage_view"}
    )
    before = {
        item.content_digest: (
            (project.root / item.path).read_bytes(),
            (project.root / item.path).stat().st_mtime_ns,
        )
        for item in first_refs
    }

    second = project.read(snapshot.document_id, idempotency_key="compatibility-second")
    second_refs = tuple(
        item
        for item in second.artifacts
        if item.artifact_type in {"article_graph_build", "stage_view"}
    )

    assert tuple((item.artifact_type, item.content_digest) for item in second_refs) == tuple(
        (item.artifact_type, item.content_digest) for item in first_refs
    )
    assert {item.schema_version for item in second_refs if item.artifact_type == "stage_view"} == {
        "stage-view.v4"
    }
    assert {
        item.schema_version for item in second_refs if item.artifact_type == "article_graph_build"
    } == {"article-graph-build-artifact.v2"}
    reader = ImmutableArtifactReader(project._artifacts)
    for reference in second_refs:
        reader.read(reference)
    for reference in first_refs:
        content, mtime = before[reference.content_digest]
        object_path = project.root / reference.path
        assert object_path.read_bytes() == content
        assert object_path.stat().st_mtime_ns == mtime

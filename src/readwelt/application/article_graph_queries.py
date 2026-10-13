"""Persisted ArticleGraph query entry point shared by public adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from readwelt.article_graph import (
    ArticleGraph,
    ArticleGraphQueryRequest,
    ArticleGraphQueryService,
    QueryErrorCode,
    QueryPage,
)
from readwelt.article_graph.query_errors import fail_query
from readwelt.article_ir import UnitizationResult
from readwelt.domain import ArtifactRef
from readwelt.provenance import SourceIndex
from readwelt.storage import ArtifactStore, ImmutableArtifactReader, ManifestStore, ProjectLayout


class ArticleGraphQueryHost(Protocol):
    _layout: ProjectLayout
    _manifests: ManifestStore
    _artifacts: ArtifactStore


def query_article_graph(
    service: ArticleGraphQueryHost,
    request: ArticleGraphQueryRequest | Mapping[str, object],
) -> QueryPage:
    """Execute one normalized request against verified immutable project artifacts."""
    parsed = (
        request
        if isinstance(request, ArticleGraphQueryRequest)
        else ArticleGraphQueryRequest.from_dict(request)
    )
    query_service = _load_query_service(service, parsed.document_id)
    operations = {
        "search": query_service.search,
        "locate": query_service.locate,
        "evidence": query_service.evidence,
        "neighbors": query_service.neighbors,
        "trace_claim": query_service.trace_claim,
        "expand_context": query_service.expand_context,
    }
    return operations[parsed.operation.value](parsed)


def _load_query_service(
    service: ArticleGraphQueryHost,
    document_id: str,
) -> ArticleGraphQueryService:
    manifest_path = service._layout.document_manifest(document_id)
    if not manifest_path.is_file():
        fail_query(QueryErrorCode.DOCUMENT_NOT_FOUND, f"document not found: {document_id}")
    manifest = service._manifests.read(manifest_path)
    raw_references = manifest.get("article_graph_build_artifacts")
    if not isinstance(raw_references, Sequence) or isinstance(raw_references, (str, bytes)):
        fail_query(QueryErrorCode.GRAPH_NOT_PREPARED, f"document is not prepared: {document_id}")

    references: dict[str, ArtifactRef] = {}
    for raw_reference in raw_references:
        if not isinstance(raw_reference, Mapping):
            fail_query(QueryErrorCode.GRAPH_NOT_PREPARED, "invalid ArticleGraph artifact reference")
        reference = ArtifactRef(**dict(raw_reference))
        if reference.artifact_type in {
            "anchored_text_unitization",
            "article_graph_source_index",
            "article_graph",
        }:
            if reference.artifact_type in references:
                fail_query(
                    QueryErrorCode.GRAPH_NOT_PREPARED,
                    f"duplicate ArticleGraph artifact: {reference.artifact_type}",
                )
            references[reference.artifact_type] = reference

    required = {
        "anchored_text_unitization",
        "article_graph_source_index",
        "article_graph",
    }
    missing = tuple(sorted(required - references.keys()))
    if missing:
        fail_query(
            QueryErrorCode.GRAPH_NOT_PREPARED,
            f"missing ArticleGraph artifacts: {', '.join(missing)}",
        )

    reader = ImmutableArtifactReader(service._artifacts)
    decoded = {name: reader.read(references[name]) for name in sorted(required)}
    legacy = tuple(
        name for name, artifact in decoded.items() if artifact.compatibility != "current"
    )
    if legacy:
        fail_query(
            QueryErrorCode.UNSUPPORTED_SCHEMA,
            f"query requires current ArticleGraph artifacts: {', '.join(legacy)}",
        )

    unitization = decoded["anchored_text_unitization"].decoded
    source_index = decoded["article_graph_source_index"].decoded
    graph = decoded["article_graph"].decoded
    if not isinstance(unitization, UnitizationResult):
        fail_query(QueryErrorCode.UNSUPPORTED_SCHEMA, "invalid Source Plane artifact")
    if not isinstance(source_index, SourceIndex):
        fail_query(QueryErrorCode.UNSUPPORTED_SCHEMA, "invalid SourceIndex artifact")
    if not isinstance(graph, ArticleGraph):
        fail_query(QueryErrorCode.UNSUPPORTED_SCHEMA, "invalid ArticleGraph artifact")
    return ArticleGraphQueryService(graph, source_index, unitization)


__all__ = ["query_article_graph"]

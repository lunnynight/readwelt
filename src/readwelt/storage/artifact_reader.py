"""Read-only compatibility access to immutable structured artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from readwelt.article_ir import (
    ARTICLE_SOURCE_PLANE_SCHEMA_VERSION,
    HISTORICAL_UNITIZATION_SCHEMA_VERSION,
)
from readwelt.domain import ArtifactRef

from .artifact_compatibility import decode_artifact
from .artifact_store import ArtifactStore

Compatibility = Literal["current", "legacy"]

_SUPPORTED_SCHEMAS: dict[str, dict[str, Compatibility]] = {
    "anchored_text_unitization": {
        HISTORICAL_UNITIZATION_SCHEMA_VERSION: "legacy",
        ARTICLE_SOURCE_PLANE_SCHEMA_VERSION: "current",
    },
    "article_graph": {
        "article-graph.v2": "legacy",
        "article-graph.v3": "legacy",
        "article-graph.v4": "current",
    },
    "graph_extraction": {
        "graph-extraction.v1": "legacy",
        "graph-extraction.v2": "legacy",
        "graph-extraction.v3": "current",
    },
    "article_graph_source_index": {
        "source-index.v1": "legacy",
        "source-index.v2": "legacy",
        "source-index.v3": "current",
    },
    "stage_view": {
        "stage-view.v1": "legacy",
        "stage-view.v2": "legacy",
        "stage-view.v3": "legacy",
        "stage-view.v4": "current",
    },
    "article_graph_build": {
        "article-graph-build.v1": "legacy",
        "article-graph-build-artifact.v1": "legacy",
        "article-graph-build-artifact.v2": "current",
    },
}


@dataclass(frozen=True, slots=True)
class ReadableArtifact:
    """A verified, semantically decoded artifact without persistence side effects."""

    reference: ArtifactRef
    schema_version: str
    compatibility: Compatibility
    payload: Mapping[str, Any]
    decoded: object


class ImmutableArtifactReader:
    """Verify CAS bytes and semantically decode exact historical schemas."""

    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts

    def read(self, reference: ArtifactRef) -> ReadableArtifact:
        supported = _SUPPORTED_SCHEMAS.get(reference.artifact_type)
        if supported is None:
            raise ValueError(f"unsupported structured artifact type: {reference.artifact_type}")
        try:
            payload = json.loads(self._artifacts.read_text(reference))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"artifact payload is not valid JSON: {reference.artifact_id}"
            ) from error
        if not isinstance(payload, Mapping):
            raise ValueError("structured artifact payload must be an object")
        schema_version = payload.get("schema_version")
        if not isinstance(schema_version, str):
            raise ValueError("structured artifact schema_version must be a string")
        if schema_version != reference.schema_version:
            raise ValueError("artifact reference and payload schema versions disagree")
        compatibility = supported.get(schema_version)
        if compatibility is None:
            raise ValueError(f"unsupported {reference.artifact_type} schema: {schema_version}")
        decoded = decode_artifact(reference.artifact_type, schema_version, payload)
        return ReadableArtifact(
            reference=reference,
            schema_version=schema_version,
            compatibility=compatibility,
            payload=payload,
            decoded=decoded,
        )

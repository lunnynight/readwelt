"""Stable, read-only pagination over persisted ArticleGraph collections."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from typing import Any, Protocol

from readwelt.domain import ArtifactRef
from readwelt.storage import ArtifactStore, ManifestStore, ProjectLayout
from readwelt.storage.serialization import canonical_json_bytes

ARTICLE_GRAPH_COLLECTIONS = frozenset({"claims", "edges", "mentions", "nodes"})
_CURSOR_SCHEMA = "readwelt.article-graph-cursor.v1"
_PAGE_SCHEMA = "readwelt.article-graph-page.v1"
_MAX_PAGE_SIZE = 500


class ArticleGraphPageHost(Protocol):
    _layout: ProjectLayout
    _manifests: ManifestStore
    _artifacts: ArtifactStore


def article_graph_page(
    service: ArticleGraphPageHost,
    document_id: str,
    *,
    collection: str = "nodes",
    limit: int = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return one deterministic page bound to an immutable graph digest."""
    if collection not in ARTICLE_GRAPH_COLLECTIONS:
        choices = ", ".join(sorted(ARTICLE_GRAPH_COLLECTIONS))
        raise ValueError(f"unknown ArticleGraph collection {collection!r}; choose {choices}")
    if limit < 1 or limit > _MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {_MAX_PAGE_SIZE}")

    manifest_path = service._layout.document_manifest(document_id)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"document not found: {document_id}")
    manifest = service._manifests.read(manifest_path)
    raw_reference = manifest.get("article_graph_artifact")
    if not isinstance(raw_reference, Mapping):
        raise ValueError(f"document is not prepared: {document_id}")
    reference = ArtifactRef(**dict(raw_reference))
    payload = json.loads(service._artifacts.read_text(reference))
    if not isinstance(payload, Mapping):
        raise ValueError("ArticleGraph artifact root must be an object")
    raw_items = payload.get(collection, [])
    if not isinstance(raw_items, list):
        raise ValueError(f"ArticleGraph collection is not a list: {collection}")

    offset = 0
    if cursor is not None:
        decoded = _decode_cursor(cursor)
        expected = {
            "document_id": document_id,
            "collection": collection,
            "graph_digest": reference.content_digest,
        }
        if any(decoded.get(key) != value for key, value in expected.items()):
            raise ValueError("stale or incompatible ArticleGraph cursor")
        raw_offset = decoded.get("offset")
        if not isinstance(raw_offset, int) or raw_offset < 0 or raw_offset > len(raw_items):
            raise ValueError("ArticleGraph cursor offset is out of bounds")
        offset = raw_offset

    end = min(offset + limit, len(raw_items))
    next_cursor = (
        _encode_cursor(
            document_id=document_id,
            collection=collection,
            graph_digest=reference.content_digest,
            offset=end,
        )
        if end < len(raw_items)
        else None
    )
    return {
        "schema_version": _PAGE_SCHEMA,
        "document_id": document_id,
        "collection": collection,
        "graph_digest": reference.content_digest,
        "offset": offset,
        "limit": limit,
        "total": len(raw_items),
        "items": raw_items[offset:end],
        "next_cursor": next_cursor,
    }


def _encode_cursor(*, document_id: str, collection: str, graph_digest: str, offset: int) -> str:
    payload = canonical_json_bytes(
        {
            "schema_version": _CURSOR_SCHEMA,
            "document_id": document_id,
            "collection": collection,
            "graph_digest": graph_digest,
            "offset": offset,
        }
    )
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    integrity = hashlib.sha256(payload).hexdigest()
    return f"{encoded}.{integrity}"


def _decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        encoded, integrity = cursor.split(".", 1)
        padding = "=" * (-len(encoded) % 4)
        payload = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError, UnicodeError) as exc:
        raise ValueError("invalid ArticleGraph cursor encoding") from exc
    if hashlib.sha256(payload).hexdigest() != integrity:
        raise ValueError("invalid ArticleGraph cursor integrity")
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid ArticleGraph cursor payload") from exc
    if not isinstance(decoded, dict) or decoded.get("schema_version") != _CURSOR_SCHEMA:
        raise ValueError("unsupported ArticleGraph cursor schema")
    return decoded

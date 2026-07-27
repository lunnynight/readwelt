"""Content-addressed artifact store backed by the Rust core."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from readwelt import _core
from readwelt.domain import ArtifactRef, ArtifactStatus, stable_id
from readwelt.storage.layout import ProjectLayout
from readwelt.storage.serialization import canonical_json_bytes


class ArtifactStore:
    def __init__(self, layout: ProjectLayout) -> None:
        self._layout = layout

    def put_json(
        self,
        value: Any,
        *,
        artifact_type: str,
        schema_version: str = "1",
    ) -> ArtifactRef:
        return self.put_bytes(
            canonical_json_bytes(value),
            artifact_type=artifact_type,
            schema_version=schema_version,
        )

    def put_text(
        self,
        text: str,
        *,
        artifact_type: str,
        schema_version: str = "1",
    ) -> ArtifactRef:
        return self.put_bytes(
            text.encode("utf-8"),
            artifact_type=artifact_type,
            schema_version=schema_version,
        )

    def put_bytes(
        self,
        content: bytes,
        *,
        artifact_type: str,
        schema_version: str = "1",
    ) -> ArtifactRef:
        stored = _core.put_object(self._layout.root / "objects", content)
        digest = stored.digest
        target = self._layout.root / "objects" / stored.relative_path
        return ArtifactRef(
            artifact_id=stable_id("artifact", artifact_type, schema_version, digest),
            artifact_type=artifact_type,
            schema_version=schema_version,
            content_digest=f"sha256:{digest}",
            path=self._layout.relative(target),
            size=stored.size,
            status=ArtifactStatus.COMPLETED,
        )

    def read_bytes(self, reference: ArtifactRef) -> bytes:
        path = self._artifact_path(reference)
        content = path.read_bytes()
        actual = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if actual != reference.content_digest:
            raise ValueError(f"artifact digest mismatch: {reference.artifact_id}")
        return content

    def read_text(self, reference: ArtifactRef) -> str:
        return self.read_bytes(reference).decode("utf-8")

    def total_stored_bytes(self) -> int:
        """Return unique bytes currently present in the content-addressed store."""

        root = self._layout.root / "objects" / "sha256"
        if not root.exists():
            return 0
        return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())

    def read_range(
        self,
        reference: ArtifactRef,
        *,
        offset: int,
        length: int,
    ) -> bytes:
        """Read one bounded byte range without materializing the whole artifact."""

        if offset < 0:
            raise ValueError("artifact range offset cannot be negative")
        if length < 0:
            raise ValueError("artifact range length cannot be negative")
        path = self._artifact_path(reference)
        with path.open("rb") as stream:
            stream.seek(offset)
            return stream.read(length)

    def iter_bytes(
        self,
        reference: ArtifactRef,
        *,
        chunk_size: int = 64 * 1024,
    ) -> Iterator[bytes]:
        """Stream verified bytes; digest validation completes when exhausted."""

        if chunk_size < 1:
            raise ValueError("artifact chunk size must be positive")
        path = self._artifact_path(reference)
        expected = reference.content_digest
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(chunk_size):
                digest.update(chunk)
                yield chunk
        actual = f"sha256:{digest.hexdigest()}"
        if actual != expected:
            raise ValueError(f"artifact digest mismatch: {reference.artifact_id}")

    def _artifact_path(self, reference: ArtifactRef) -> Path:
        path = (self._layout.root / reference.path).resolve()
        path.relative_to(self._layout.root)
        digest = reference.content_digest.removeprefix("sha256:")
        if len(digest) != 64 or path.name != digest:
            raise ValueError(f"artifact CAS identity mismatch: {reference.artifact_id}")
        if path.stat().st_size != reference.size:
            raise ValueError(f"artifact size mismatch: {reference.artifact_id}")
        return path

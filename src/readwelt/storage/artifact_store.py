"""Content-addressed artifact store backed by the Rust core."""

from __future__ import annotations

import hashlib
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
        path = (self._layout.root / reference.path).resolve()
        path.relative_to(self._layout.root)
        content = path.read_bytes()
        actual = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if actual != reference.content_digest:
            raise ValueError(f"artifact digest mismatch: {reference.artifact_id}")
        return content

    def read_text(self, reference: ArtifactRef) -> str:
        return self.read_bytes(reference).decode("utf-8")

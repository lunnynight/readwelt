from __future__ import annotations

from pathlib import Path

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import SourceDocumentSnapshot
from readwelt.extraction import BackendCapability, BackendDescriptor
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


class _FailingSemanticBackend:
    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id="test.semantic.failure",
            name="failing semantic backend",
            version="1",
            model_revision=None,
            supported_capabilities=(BackendCapability.CLAIM,),
            deterministic=True,
        )

    def extract(self, inputs: object) -> object:
        del inputs
        raise RuntimeError("semantic backend unavailable")


def _snapshot(tmp_path: Path, text: str) -> SourceDocumentSnapshot:
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    return snapshot_from_text(
        source=tmp_path / "source.txt",
        text=text,
        source_kind="text/plain",
        artifacts=ArtifactStore(layout),
        adapter_finding="test",
    )


def test_semantic_failure_cannot_reduce_source_reachability(tmp_path: Path) -> None:
    text = "First paragraph.\n\nSecond paragraph."
    build = ArticleGraphBuilder(
        semantic_backends=(_FailingSemanticBackend(),),  # type: ignore[arg-type]
    ).build(_snapshot(tmp_path, text), text)

    manifest = build.unitization.coverage_manifest
    assert manifest is not None
    assert manifest.has_complete_source_reachability
    assert all(build.unitization.range_at(offset) is not None for offset in range(len(text)))
    assert any(
        extraction.backend.backend_id == "test.semantic.failure"
        and extraction.degradation.failed_capabilities == (BackendCapability.CLAIM,)
        for extraction in build.extractions
    )

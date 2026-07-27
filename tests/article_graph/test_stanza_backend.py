from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from readwelt.article_graph import ArticleGraphBuilder
from readwelt.domain import DocumentSection, SourceDocumentSnapshot, SpanAnchor, stable_id
from readwelt.extraction import (
    BackendCapability,
    CapabilityStatus,
    ExtractionInput,
    StanzaLinguisticBackend,
)


class _EmptyPipeline:
    def __call__(self, text: str) -> SimpleNamespace:
        assert text
        return SimpleNamespace(sentences=(), ents=())


def _snapshot(text: str) -> SourceDocumentSnapshot:
    snapshot_id = stable_id("snapshot", text)
    section_id = stable_id("section", snapshot_id)
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=stable_id("document", text),
        schema_version="1",
        source_kind="text/plain",
        source_locator="stanza.txt",
        content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        captured_at=datetime(2026, 7, 27, tzinfo=UTC),
        language="zh",
        normalized_text_ref="objects/stanza/body",
        sections=(
            DocumentSection(
                section_id=section_id,
                title=None,
                start_offset=0,
                end_offset=len(text),
                anchor=SpanAnchor.create(
                    snapshot_id=snapshot_id,
                    section_id=section_id,
                    text=text,
                    start_offset=0,
                    end_offset=len(text),
                ),
            ),
        ),
    )


def test_stanza_is_a_production_callable_optional_backend() -> None:
    backend = StanzaLinguisticBackend(Path("unused-model-dir"), pipeline=_EmptyPipeline())

    extraction = backend.extract(
        (
            ExtractionInput(
                document_id="doc-1",
                snapshot_id="snapshot-1",
                unit_id="unit-1",
                text="这是一个测试。",
            ),
        )
    )

    assert extraction.schema_version == "graph-extraction.v3"
    assert extraction.backend.backend_id == "stanza.zh-hans"
    assert extraction.backend.model_revision == "stanfordnlp/stanza-zh-hans@v1.14.0"
    assert extraction.coverage.complete
    outcomes = {item.capability: item for item in extraction.outcomes}
    assert outcomes[BackendCapability.SENTENCE].status is CapabilityStatus.EMPTY
    assert outcomes[BackendCapability.SRL].status is CapabilityStatus.UNSUPPORTED
    assert outcomes[BackendCapability.COREFERENCE].status is CapabilityStatus.UNSUPPORTED


def test_stanza_adapter_runs_through_article_graph_builder() -> None:
    text = "这是一个测试。"
    backend = StanzaLinguisticBackend(Path("unused-model-dir"), pipeline=_EmptyPipeline())

    build = ArticleGraphBuilder(
        linguistic_backends=(backend,),
        semantic_backends=(),
    ).build(_snapshot(text), text)

    assert tuple(item.backend.backend_id for item in build.extractions) == ("stanza.zh-hans",)
    assert build.unitization.coverage.has_complete_text_coverage

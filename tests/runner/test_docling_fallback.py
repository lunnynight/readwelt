from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from readwelt.runner.docling import (
    DoclingStructuralFallback,
    StructuralFallbackResult,
)
from readwelt.runner.xberg import XbergDocumentAdapter
from readwelt.storage import ArtifactStore, ProjectLayout


class _FakeDocument:
    def __init__(self) -> None:
        heading_ref = SimpleNamespace(cref="#/texts/0")
        body_ref = SimpleNamespace(cref="#/texts/1")
        heading = SimpleNamespace(
            self_ref="#/texts/0",
            label=SimpleNamespace(value="section_header"),
            text="Heading",
            orig="Heading",
            parent=None,
            children=[body_ref],
            captions=[],
            references=[],
            footnotes=[],
            prov=[
                SimpleNamespace(
                    page_no=1,
                    bbox=SimpleNamespace(l=1, t=2, r=30, b=12),
                    charspan=(0, 7),
                )
            ],
        )
        body = SimpleNamespace(
            self_ref="#/texts/1",
            label=SimpleNamespace(value="paragraph"),
            text="Body",
            orig="Body",
            parent=heading_ref,
            children=[],
            captions=[],
            references=[],
            footnotes=[],
            prov=[
                SimpleNamespace(
                    page_no=1,
                    bbox=SimpleNamespace(l=1, t=15, r=30, b=25),
                    charspan=(9, 13),
                )
            ],
        )
        self._items = ((heading, 0), (body, 1))

    def export_to_text(self) -> str:
        return "Heading\n\nBody"

    def iterate_items(self) -> tuple[tuple[object, int], ...]:
        return self._items


class _FakeConverter:
    def convert(self, source: Path) -> object:
        assert source.suffix == ".pdf"
        return SimpleNamespace(
            document=_FakeDocument(),
            status=SimpleNamespace(value="success"),
        )


class _FakeGroupedDocument:
    def __init__(self) -> None:
        group_ref = SimpleNamespace(cref="#/groups/0")
        child_ref = SimpleNamespace(cref="#/texts/0")
        self._group = SimpleNamespace(
            self_ref="#/groups/0",
            label=SimpleNamespace(value="section"),
            text=None,
            orig=None,
            parent=None,
            children=[child_ref],
            captions=[],
            references=[],
            footnotes=[],
            prov=[],
        )
        self._child = SimpleNamespace(
            self_ref="#/texts/0",
            label=SimpleNamespace(value="paragraph"),
            text="Grouped body",
            orig="Grouped body",
            parent=group_ref,
            children=[],
            captions=[],
            references=[],
            footnotes=[],
            prov=[
                SimpleNamespace(
                    page_no=1,
                    bbox=SimpleNamespace(l=2, t=3, r=20, b=12),
                    charspan=(0, 12),
                )
            ],
        )
        self.with_groups: bool | None = None

    def export_to_text(self) -> str:
        return "Grouped body"

    def iterate_items(
        self,
        *,
        with_groups: bool = False,
    ) -> tuple[tuple[object, int], ...]:
        self.with_groups = with_groups
        if with_groups:
            return ((self._group, 0), (self._child, 1))
        return ((self._child, 1),)


class _FakeGroupedConverter:
    def __init__(self) -> None:
        self.document = _FakeGroupedDocument()

    def convert(self, source: Path) -> object:
        assert source.suffix == ".pdf"
        return SimpleNamespace(
            document=self.document,
            status=SimpleNamespace(value="success"),
        )


class _FakeFullTraversalDocument(_FakeGroupedDocument):
    def __init__(self) -> None:
        super().__init__()
        self._group.content_layer = SimpleNamespace(value="furniture")
        self._child.content_layer = SimpleNamespace(value="body")
        self.traverse_pictures: bool | None = None
        self.included_content_layers: set[object] | None = None

    def iterate_items(
        self,
        *,
        with_groups: bool = False,
        traverse_pictures: bool = False,
        included_content_layers: set[object] | None = None,
    ) -> tuple[tuple[object, int], ...]:
        self.with_groups = with_groups
        self.traverse_pictures = traverse_pictures
        self.included_content_layers = included_content_layers
        return ((self._group, 0), (self._child, 1))


class _FakeFullTraversalConverter:
    def __init__(self) -> None:
        self.document = _FakeFullTraversalDocument()

    def convert(self, source: Path) -> object:
        assert source.suffix == ".pdf"
        return SimpleNamespace(
            document=self.document,
            status=SimpleNamespace(value="success"),
        )


class _RecordingFallback:
    def __init__(self) -> None:
        self.calls = 0

    def project(self, source: Path, *, trigger: str) -> StructuralFallbackResult:
        del source, trigger
        self.calls += 1
        return StructuralFallbackResult(None, (), ("unexpected",))


def _artifacts(tmp_path: Path) -> ArtifactStore:
    layout = ProjectLayout.resolve(tmp_path / "project")
    layout.initialize()
    return ArtifactStore(layout)


def test_docling_projection_preserves_native_structure_and_provenance() -> None:
    result = DoclingStructuralFallback(converter=_FakeConverter()).project(
        Path("scan.pdf"),
        trigger="empty_pdf_text_and_structure_unavailable",
    )

    heading, body = result.structure
    assert result.text == "Heading\n\nBody"
    assert heading.element_id == "docling:#/texts/0"
    assert heading.child_element_ids == ("docling:#/texts/1",)
    assert body.parent_element_id == "docling:#/texts/0"
    assert (body.start_offset, body.end_offset) == (9, 13)
    assert body.page == 1
    assert body.bounding_box == (1.0, 15.0, 30.0, 25.0)
    assert "docling_fallback_conversion_status:success" in result.findings
    assert "docling_fallback_remote_services:false" in result.findings
    assert "docling_fallback_backend:injected_test_double" in result.findings
    assert "docling_fallback_adapter:readwelt.docling-structural-fallback.v1" in result.findings


def test_docling_projection_requests_groups_and_closes_parent_child_references() -> None:
    converter = _FakeGroupedConverter()

    result = DoclingStructuralFallback(converter=converter).project(
        Path("scan.pdf"),
        trigger="xberg_structure_unavailable",
    )

    group, child = result.structure
    assert converter.document.with_groups is True
    assert group.exact_text is None
    assert group.kind == "section"
    assert group.element_id == "docling:#/groups/0"
    assert group.child_element_ids == ("docling:#/texts/0",)
    assert child.parent_element_id == group.element_id
    identities = {item.element_id for item in result.structure}
    assert group.child_element_ids[0] in identities
    assert child.parent_element_id in identities


def test_docling_projection_requests_complete_content_layer_traversal() -> None:
    converter = _FakeFullTraversalConverter()

    result = DoclingStructuralFallback(converter=converter).project(
        Path("scan.pdf"),
        trigger="xberg_structure_unavailable",
    )

    assert converter.document.with_groups is True
    assert converter.document.traverse_pictures is True
    assert {
        getattr(layer, "value", None)
        for layer in converter.document.included_content_layers or set()
    } == {"body", "furniture", "background", "invisible", "notes"}
    assert tuple(item.content_layer for item in result.structure) == (
        "furniture",
        "body",
    )


def test_docling_without_local_models_fails_explicitly_without_download(
    tmp_path: Path,
) -> None:
    result = DoclingStructuralFallback(artifacts_path=tmp_path / "missing-models").project(
        tmp_path / "scan.pdf",
        trigger="xberg_structure_unavailable",
    )

    assert result.structure == ()
    assert result.text is None
    assert "docling_fallback_blocked:READWELT_DOCLING_ARTIFACTS_PATH_required" in result.findings
    assert "docling_fallback_backend:production" in result.findings
    assert (
        "docling_fallback_model_artifacts:"
        "sha256:117ce0d7c9486c4bb9b53a11b5fe5f2035bf192997cf4915b5cb99f97389a202" in result.findings
    )
    assert "docling_fallback_ocr_backend:onnxruntime" in result.findings


def test_xberg_empty_pdf_uses_docling_but_preserves_original_source_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def extract(_value: object) -> object:
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    content="",
                    mime_type="application/pdf",
                    metadata=None,
                    document=None,
                    elements=None,
                )
            ]
        )

    monkeypatch.setitem(
        sys.modules,
        "xberg",
        SimpleNamespace(ExtractInput=lambda **value: value, extract=extract),
    )
    source = tmp_path / "scan.pdf"
    original = b"%PDF-1.7 original scanned bytes"
    source.write_bytes(original)
    artifacts = _artifacts(tmp_path)
    adapter = XbergDocumentAdapter(
        artifacts,
        structural_fallback=DoclingStructuralFallback(converter=_FakeConverter()),
    )

    snapshot = asyncio.run(adapter.ingest(source))

    normalized = (tmp_path / "project" / snapshot.normalized_text_ref).read_text(encoding="utf-8")
    assert normalized == "Heading\n\nBody"
    assert snapshot.source_elements[0].kind == "source_document"
    assert snapshot.source_elements[0].raw_payload_ref == snapshot.attachments[0]
    assert tuple(item.native_reference for item in snapshot.source_elements[1:]) == (
        "#/texts/0",
        "#/texts/1",
    )
    assert "docling_fallback_structure_adopted:2" in snapshot.parse_findings
    assert "docling_fallback_text_adopted:xberg_text_empty" in snapshot.parse_findings


@pytest.mark.parametrize(
    ("extension", "mime_type"),
    [("txt", "text/plain"), ("html", "text/html")],
)
def test_xberg_does_not_invoke_pdf_fallback_for_normal_text_or_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extension: str,
    mime_type: str,
) -> None:
    async def extract(_value: object) -> object:
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    content="ordinary text",
                    mime_type=mime_type,
                    metadata=None,
                    document=None,
                    elements=None,
                )
            ]
        )

    monkeypatch.setitem(
        sys.modules,
        "xberg",
        SimpleNamespace(ExtractInput=lambda **value: value, extract=extract),
    )
    source = tmp_path / f"article.{extension}"
    source.write_text("ordinary text", encoding="utf-8")
    fallback = _RecordingFallback()
    adapter = XbergDocumentAdapter(
        _artifacts(tmp_path),
        structural_fallback=fallback,
    )

    snapshot = asyncio.run(adapter.ingest(source))

    assert fallback.calls == 0
    assert all("docling_fallback" not in item for item in snapshot.parse_findings)


def test_xberg_does_not_invoke_fallback_when_pdf_structure_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def extract(_value: object) -> object:
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    content="Body",
                    mime_type="application/pdf",
                    metadata=None,
                    document=None,
                    elements=[
                        SimpleNamespace(
                            text="Body",
                            element_type="paragraph",
                            metadata=SimpleNamespace(
                                page_number=1,
                                element_index=0,
                                coordinates=None,
                            ),
                        )
                    ],
                )
            ]
        )

    monkeypatch.setitem(
        sys.modules,
        "xberg",
        SimpleNamespace(ExtractInput=lambda **value: value, extract=extract),
    )
    source = tmp_path / "native.pdf"
    source.write_bytes(b"%PDF-1.7 native")
    fallback = _RecordingFallback()
    adapter = XbergDocumentAdapter(
        _artifacts(tmp_path),
        structural_fallback=fallback,
    )

    snapshot = asyncio.run(adapter.ingest(source))

    assert fallback.calls == 0
    assert "xberg_elements_available:1" in snapshot.parse_findings


def test_xberg_pdf_text_remains_authoritative_when_only_structure_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def extract(_value: object) -> object:
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    content="Xberg text remains primary.",
                    mime_type="application/pdf",
                    metadata=None,
                    document=None,
                    elements=None,
                )
            ]
        )

    monkeypatch.setitem(
        sys.modules,
        "xberg",
        SimpleNamespace(ExtractInput=lambda **value: value, extract=extract),
    )
    source = tmp_path / "native.pdf"
    source.write_bytes(b"%PDF-1.7 native text")
    artifacts = _artifacts(tmp_path)
    adapter = XbergDocumentAdapter(
        artifacts,
        structural_fallback=DoclingStructuralFallback(converter=_FakeConverter()),
    )

    snapshot = asyncio.run(adapter.ingest(source))
    normalized = (tmp_path / "project" / snapshot.normalized_text_ref).read_text(encoding="utf-8")

    assert normalized == "Xberg text remains primary."
    assert "docling_fallback_structure_adopted:2" in snapshot.parse_findings
    assert all(
        finding != "docling_fallback_text_adopted:xberg_text_empty"
        for finding in snapshot.parse_findings
    )

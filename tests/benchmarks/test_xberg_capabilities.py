from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.articlegraph.xberg_capabilities import ProbeCase, summarize_documents


def test_summarize_documents_reports_real_exposed_capabilities() -> None:
    node = SimpleNamespace(
        id="n1",
        start_offset=1,
        end_offset=3,
        page=2,
        bbox=(0, 0, 1, 1),
        parent="root",
        ordinal=4,
    )
    document = SimpleNamespace(
        content="正文",
        mime_type="application/pdf",
        nodes=None,
        elements=None,
        pages=None,
        chunks=None,
        relationships=None,
        document=SimpleNamespace(
            nodes=[node],
            elements=None,
            pages=[object()],
            chunks=None,
            relationships=[object()],
        ),
    )

    result = summarize_documents(
        case=ProbeCase("pdf", "native_pdf", "source.pdf"),
        source=Path("source.pdf"),
        source_digest="sha256:source",
        documents=(document,),
        xberg_version="1.0.0rc38",
    )

    assert result.status == "ok"
    assert result.content_characters == 2
    assert dict(result.nested_collections)["nodes"] == 1
    assert result.native_id_count == 1
    assert result.offset_field_count == 1
    assert result.page_value_count == 1
    assert result.geometry_value_count == 1
    assert result.relationship_value_count == 1
    assert result.reading_order_value_count == 1
    assert ("id", "n1") in result.native_ids
    assert ("start_offset", "1") in result.offsets
    assert ("page", "2") in result.pages
    assert result.geometry
    assert ("parent", "root") in result.relationships
    assert ("ordinal", "4") in result.reading_order


def test_summarize_documents_does_not_invent_missing_structure() -> None:
    document = SimpleNamespace(
        content="",
        mime_type="application/pdf",
        document=None,
        elements=None,
        pages=None,
        chunks=None,
        relationships=None,
        nodes=None,
    )

    result = summarize_documents(
        case=ProbeCase("pdf", "native_pdf", "source.pdf"),
        source=Path("source.pdf"),
        source_digest="sha256:source",
        documents=(document,),
        xberg_version="1.0.0rc38",
    )

    assert result.content_characters == 0
    assert "content_empty" in result.findings
    assert "structure_not_exposed" in result.findings


def test_real_probe_report_covers_required_formats_without_missing_sources() -> None:
    payload = json.loads(
        Path("reports/xberg-capability-probe-2026-07-27.json").read_text(encoding="utf-8")
    )
    results = payload["results"]
    required = {"txt", "html", "epub", "native_pdf", "scanned_pdf"}

    assert required.issubset({result["format"] for result in results})
    for result in results:
        assert result["status"] == "ok"
        assert result["source_digest"].startswith("sha256:")
        for field in (
            "native_ids",
            "offsets",
            "pages",
            "geometry",
            "relationships",
            "reading_order",
        ):
            assert isinstance(result[field], list)
        if "structure_not_exposed" in result["findings"]:
            assert result["native_id_count"] == 0
            assert result["native_ids"] == []

from pathlib import Path

from readwelt import _core
from readwelt.application import ReadweltApplicationService


def test_rust_core_is_packaged_and_normalizes_text() -> None:
    prepared = _core.prepare("\ufeff第一段  \r\n\r\n第二段\r\n")

    assert prepared.text == "第一段\n\n第二段"
    assert [paragraph.text for paragraph in prepared.paragraphs] == ["第一段", "第二段"]
    assert prepared.paragraphs[1].start_char == 5


def test_rust_semantic_batch_is_packaged() -> None:
    records = _core.semantic_analyze(["量子芯片。", "量子芯片。"], 0.82)

    assert records[0][0][-1] == "芯片"
    assert records[1][6] == 0
    assert _core.bm25_rank([records[0][0]], ["芯片"])[0][0] == 0
    assert _core.coverage_intervals("甲 乙", [(0, 1)]) == ([(2, 3)], 1)


def test_snapshot_uses_rust_paragraph_anchors_and_cas(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("第一段  \n\n第二段\n", encoding="utf-8")
    service = ReadweltApplicationService(
        ".readwelt",
        base_directory=tmp_path,
        ingestion_backend="plain_text",
    )

    snapshot = service.import_document(source)

    assert len(snapshot.sections) == 2
    assert [section.anchor.exact_text for section in snapshot.sections] == [
        "第一段",
        "第二段",
    ]
    assert all(section.anchor.anchor_id.startswith("sha256:") for section in snapshot.sections)
    normalized_path = service.root / snapshot.normalized_text_ref
    assert normalized_path.read_text(encoding="utf-8") == "第一段\n\n第二段"

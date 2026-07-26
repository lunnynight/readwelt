from __future__ import annotations

import zipfile
from pathlib import Path

from readwelt.runner.epub_outline import EpubOutlineItem, load_epub_outline
from readwelt.runner.snapshot import snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


def test_load_epub_outline_preserves_ncx_order_and_depth(tmp_path: Path) -> None:
    epub = tmp_path / "book.epub"
    with zipfile.ZipFile(epub, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
            <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles>
                <rootfile full-path="OPS/content.opf"/>
              </rootfiles>
            </container>""",
        )
        archive.writestr(
            "OPS/content.opf",
            """<?xml version="1.0"?>
            <package xmlns="http://www.idpf.org/2007/opf">
              <manifest>
                <item id="ncx" href="toc.ncx"
                      media-type="application/x-dtbncx+xml"/>
              </manifest>
              <spine toc="ncx"/>
            </package>""",
        )
        archive.writestr(
            "OPS/toc.ncx",
            """<?xml version="1.0"?>
            <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">
              <navMap>
                <navPoint id="chapter">
                  <navLabel><text>第一章</text></navLabel>
                  <content src="chapter.xhtml"/>
                  <navPoint id="section">
                    <navLabel><text>第一节</text></navLabel>
                    <content src="chapter.xhtml#section"/>
                  </navPoint>
                </navPoint>
              </navMap>
            </ncx>""",
        )

    assert load_epub_outline(epub) == (
        EpubOutlineItem(title="第一章", href="chapter.xhtml", level=0),
        EpubOutlineItem(title="第一节", href="chapter.xhtml#section", level=1),
    )


def test_snapshot_maps_paragraphs_to_body_outline_not_toc_duplicates(
    tmp_path: Path,
) -> None:
    text = "\n\n".join(
        (
            "目录",
            "第一章",
            "第一节",
            "第二章",
            "序言内容",
            "第一章",
            "甲段",
            "第一节",
            "乙段",
            "第二章",
            "丙段",
        )
    )
    outline = (
        EpubOutlineItem(title="第一章", href="one.xhtml", level=0),
        EpubOutlineItem(title="第一节", href="one.xhtml#section", level=1),
        EpubOutlineItem(title="第二章", href="two.xhtml", level=0),
    )
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()

    snapshot = snapshot_from_text(
        source=tmp_path / "book.epub",
        text=text,
        source_kind="application/epub+zip",
        artifacts=ArtifactStore(layout),
        adapter_finding="test",
        outline=outline,
        snapshot_policy_version="test-epub-outline-v1",
    )

    body = {
        section.anchor.exact_text: (section.section_id, section.title)
        for section in snapshot.sections
        if section.anchor.exact_text in {"第一章", "甲段", "第一节", "乙段", "第二章", "丙段"}
        and section.anchor.start_offset > text.index("序言内容")
    }
    assert body["第一章"][1] == "第一章"
    assert body["甲段"] == body["第一章"]
    assert body["第一节"][1] == "第一节"
    assert body["乙段"] == body["第一节"]
    assert body["第二章"][1] == "第二章"
    assert body["丙段"] == body["第二章"]
    assert "epub_outline_aligned:3/3" in snapshot.parse_findings


def test_snapshot_accepts_heading_and_body_in_the_same_epub_block(
    tmp_path: Path,
) -> None:
    text = "第一章\n\n第一节\n\n第一章\n正文甲\n\n第一节\n正文乙"
    outline = (
        EpubOutlineItem(title="第一章", href="one.xhtml", level=0),
        EpubOutlineItem(title="第一节", href="one.xhtml#section", level=1),
    )
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()

    snapshot = snapshot_from_text(
        source=tmp_path / "book.epub",
        text=text,
        source_kind="application/epub+zip",
        artifacts=ArtifactStore(layout),
        adapter_finding="test",
        outline=outline,
        snapshot_policy_version="test-epub-outline-prefix-v1",
    )

    body_sections = [
        section
        for section in snapshot.sections
        if section.anchor.start_offset > text.index("第一节") + len("第一节")
    ]
    assert [section.title for section in body_sections] == ["第一章", "第一节"]
    assert body_sections[0].anchor.exact_text == "第一章\n正文甲"
    assert body_sections[1].anchor.exact_text == "第一节\n正文乙"

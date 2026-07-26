"""Read the navigation outline embedded in an EPUB container."""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True, slots=True)
class EpubOutlineItem:
    title: str
    href: str
    level: int


def load_epub_outline(source: Path) -> tuple[EpubOutlineItem, ...]:
    """Load an EPUB 2 NCX outline without extracting or rewriting the book."""
    with zipfile.ZipFile(source) as archive:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None:
            return ()
        package_path = rootfile.get("full-path")
        if not package_path:
            return ()

        package = ElementTree.fromstring(archive.read(package_path))
        spine = package.find(".//{*}spine")
        toc_id = spine.get("toc") if spine is not None else None
        ncx_item = None
        for item in package.findall(".//{*}manifest/{*}item"):
            if item.get("id") == toc_id or item.get("media-type") == ("application/x-dtbncx+xml"):
                ncx_item = item
                break
        if ncx_item is None or not ncx_item.get("href"):
            return ()

        ncx_path = posixpath.normpath(
            posixpath.join(posixpath.dirname(package_path), ncx_item.get("href", ""))
        )
        ncx = ElementTree.fromstring(archive.read(ncx_path))

    nav_map = ncx.find(".//{*}navMap")
    if nav_map is None:
        return ()
    result: list[EpubOutlineItem] = []

    def visit(parent: ElementTree.Element, level: int) -> None:
        for point in parent.findall("{*}navPoint"):
            title = point.findtext("{*}navLabel/{*}text")
            content = point.find("{*}content")
            href = content.get("src") if content is not None else None
            normalized_title = " ".join(title.split()) if title else ""
            if normalized_title and href:
                result.append(
                    EpubOutlineItem(
                        title=normalized_title,
                        href=href,
                        level=level,
                    )
                )
            visit(point, level + 1)

    visit(nav_map, 0)
    return tuple(result)

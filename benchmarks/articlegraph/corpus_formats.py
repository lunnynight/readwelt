"""Format-specific inspection for the ArticleGraph acceptance corpus.

PDF characteristics are delegated to Poppler command-line tools.  This module
does not implement a PDF parser.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True, slots=True)
class FormatObservation:
    text_characters: int = 0
    chinese_characters: int = 0
    english_words: int = 0
    numeric_tokens: int = 0
    quote_marks: int = 0
    tables: int = 0
    figures: int = 0
    captions: int = 0
    images: int = 0
    pages: int = 0
    structural_markers: int = 0
    package_entries: int = 0
    spine_items: int = 0


class _HTMLObservationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.tables = 0
        self.figures = 0
        self.captions = 0
        self.images = 0
        self.structural_markers = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        normalized = tag.casefold()
        if normalized == "table":
            self.tables += 1
        elif normalized == "figure":
            self.figures += 1
        elif normalized in {"caption", "figcaption"}:
            self.captions += 1
        elif normalized == "img":
            self.images += 1
        if normalized in {
            "article",
            "section",
            "nav",
            "aside",
            "header",
            "footer",
        } or re.fullmatch(r"h[1-6]", normalized):
            self.structural_markers += 1

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def inspect_text(path: Path) -> FormatObservation:
    text = path.read_text(encoding="utf-8")
    markdown_headings = len(re.findall(r"(?m)^\s{0,3}#{1,6}\s+\S", text))
    html_markers = len(re.findall(r"(?i)<(?:html|body|article|section|h[1-6])\b", text))
    return _text_observation(
        text,
        structural_markers=markdown_headings + html_markers,
    )


def inspect_html(path: Path) -> FormatObservation:
    parser = _HTMLObservationParser()
    parser.feed(path.read_text(encoding="utf-8"))
    observation = _text_observation(
        " ".join(parser.text),
        structural_markers=parser.structural_markers,
    )
    return FormatObservation(
        text_characters=observation.text_characters,
        chinese_characters=observation.chinese_characters,
        english_words=observation.english_words,
        numeric_tokens=observation.numeric_tokens,
        quote_marks=observation.quote_marks,
        tables=parser.tables,
        figures=parser.figures,
        captions=parser.captions,
        images=parser.images,
        structural_markers=parser.structural_markers,
    )


def inspect_pdf(path: Path) -> FormatObservation:
    """Inspect a PDF with Poppler rather than maintaining a local parser."""

    pdfinfo = _run_poppler("pdfinfo", (str(path),))
    text = _run_poppler("pdftotext", (str(path), "-"))
    images = _run_poppler("pdfimages", ("-list", str(path)))
    pages_match = re.search(r"(?m)^Pages:\s+(\d+)\s*$", pdfinfo)
    if pages_match is None:
        raise ValueError("pdfinfo did not report a page count")
    image_rows = tuple(
        line
        for line in images.splitlines()
        if re.match(r"^\s*\d+\s+\d+\s+\S+\s+\d+\s+\d+\s+", line)
    )
    observation = _text_observation(text)
    return FormatObservation(
        text_characters=observation.text_characters,
        chinese_characters=observation.chinese_characters,
        english_words=observation.english_words,
        numeric_tokens=observation.numeric_tokens,
        quote_marks=observation.quote_marks,
        images=len(image_rows),
        pages=int(pages_match.group(1)),
    )


def inspect_epub(path: Path) -> FormatObservation:
    if not zipfile.is_zipfile(path):
        raise ValueError("EPUB is not a ZIP package")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if not members or members[0].filename != "mimetype":
            raise ValueError("EPUB mimetype must be the first package member")
        if members[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("EPUB mimetype must be stored without compression")
        if archive.read("mimetype") != b"application/epub+zip":
            raise ValueError("EPUB mimetype payload is invalid")
        if "META-INF/container.xml" not in archive.namelist():
            raise ValueError("EPUB container.xml is missing")
        rootfile = _epub_rootfile(archive.read("META-INF/container.xml"))
        if rootfile not in archive.namelist():
            raise ValueError(f"EPUB rootfile is missing: {rootfile}")
        package = ElementTree.fromstring(archive.read(rootfile))
        manifest_items = _epub_manifest(package, rootfile)
        spine_hrefs = _epub_spine(package, manifest_items)
        if not spine_hrefs:
            raise ValueError("EPUB spine is empty")
        parser = _HTMLObservationParser()
        for href in spine_hrefs:
            if href not in archive.namelist():
                raise ValueError(f"EPUB spine target is missing: {href}")
            parser.feed(archive.read(href).decode("utf-8"))
        observation = _text_observation(
            " ".join(parser.text),
            structural_markers=parser.structural_markers,
        )
        return FormatObservation(
            text_characters=observation.text_characters,
            chinese_characters=observation.chinese_characters,
            english_words=observation.english_words,
            numeric_tokens=observation.numeric_tokens,
            quote_marks=observation.quote_marks,
            tables=parser.tables,
            figures=parser.figures,
            captions=parser.captions,
            images=parser.images,
            structural_markers=parser.structural_markers,
            package_entries=len(members),
            spine_items=len(spine_hrefs),
        )


def _text_observation(text: str, *, structural_markers: int = 0) -> FormatObservation:
    return FormatObservation(
        text_characters=len(text.strip()),
        chinese_characters=len(re.findall(r"[\u3400-\u9fff]", text)),
        english_words=len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text)),
        numeric_tokens=len(re.findall(r"\d+(?:[.,]\d+)*", text)),
        quote_marks=len(re.findall(r"[“”‘’\"']", text)),
        structural_markers=structural_markers,
    )


def _run_poppler(command: str, arguments: tuple[str, ...]) -> str:
    try:
        completed = subprocess.run(
            (command, *arguments),
            check=False,
            capture_output=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"required Poppler tool is unavailable: {command}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"{command} failed with exit {completed.returncode}: {detail}")
    return completed.stdout.decode("utf-8", errors="replace")


def _epub_rootfile(container_payload: bytes) -> str:
    root = ElementTree.fromstring(container_payload)
    rootfile = root.find(".//{*}rootfile")
    if rootfile is None:
        raise ValueError("EPUB container has no rootfile")
    full_path = rootfile.attrib.get("full-path")
    if not full_path:
        raise ValueError("EPUB rootfile has no full-path")
    return full_path


def _epub_manifest(package: ElementTree.Element, rootfile: str) -> dict[str, str]:
    base = Path(rootfile).parent
    result: dict[str, str] = {}
    for item in package.findall(".//{*}manifest/{*}item"):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        if item_id and href:
            result[item_id] = (base / href).as_posix()
    if not result:
        raise ValueError("EPUB manifest is empty")
    return result


def _epub_spine(package: ElementTree.Element, manifest: dict[str, str]) -> tuple[str, ...]:
    result: list[str] = []
    for itemref in package.findall(".//{*}spine/{*}itemref"):
        item_id = itemref.attrib.get("idref")
        if item_id is None or item_id not in manifest:
            raise ValueError(f"EPUB spine has unknown manifest id: {item_id}")
        result.append(manifest[item_id])
    return tuple(result)


def expectation_values(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValueError("expected must be an object")
    result: dict[str, int] = {}
    for key, value in raw.items():
        if key.startswith(("min_", "max_")):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"expected.{key} must be a non-negative integer")
            result[key] = value
    return result

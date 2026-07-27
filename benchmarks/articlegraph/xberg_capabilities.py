"""Probe the structure Xberg actually exposes for each document format."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

PROBE_SCHEMA_VERSION = "xberg-capability-probe.v1"
_COLLECTION_FIELDS = ("nodes", "elements", "pages", "chunks", "relationships")
_OFFSET_NAMES = (
    "start_offset",
    "end_offset",
    "start_char",
    "end_char",
    "text_start",
    "text_end",
)


@dataclass(frozen=True, slots=True)
class ProbeCase:
    label: str
    format: str
    path: str
    path_kind: str = "file"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    schema_version: str
    label: str
    format: str
    source_path: str
    source_digest: str | None
    xberg_version: str
    status: str
    result_count: int
    content_characters: int
    mime_types: tuple[str, ...]
    top_level_collections: tuple[tuple[str, int], ...]
    nested_collections: tuple[tuple[str, int], ...]
    native_id_count: int
    offset_field_count: int
    page_value_count: int
    geometry_value_count: int
    relationship_value_count: int
    reading_order_value_count: int
    native_ids: tuple[tuple[str, str], ...] = ()
    offsets: tuple[tuple[str, str], ...] = ()
    pages: tuple[tuple[str, str], ...] = ()
    geometry: tuple[tuple[str, str], ...] = ()
    relationships: tuple[tuple[str, str], ...] = ()
    reading_order: tuple[tuple[str, str], ...] = ()
    findings: tuple[str, ...] = ()


async def probe_case(case: ProbeCase, *, base_dir: Path) -> ProbeResult:
    """Run one real Xberg extraction and summarize structure without storing content."""

    source = (base_dir / case.path).resolve()
    if not source.exists():
        return _missing(case, source, "source_missing")
    try:
        from xberg import ExtractInput, extract
    except ImportError:
        return _missing(case, source, "xberg_not_installed")

    with _materialized_source(source, case.path_kind) as materialized:
        output = await extract(ExtractInput(kind="uri", uri=str(materialized)))
        documents = tuple(output.results)
    source_digest = _tree_digest(source) if source.is_dir() else _file_digest(source)
    return summarize_documents(
        case=case,
        source=source,
        source_digest=source_digest,
        documents=documents,
        xberg_version=version("xberg"),
    )


def summarize_documents(
    *,
    case: ProbeCase,
    source: Path,
    source_digest: str,
    documents: Sequence[Any],
    xberg_version: str,
) -> ProbeResult:
    top_level = {field: 0 for field in _COLLECTION_FIELDS}
    nested = {field: 0 for field in _COLLECTION_FIELDS}
    mime_types: set[str] = set()
    content_characters = 0
    observed: list[Any] = []
    for document in documents:
        content = _value(document, "content")
        if isinstance(content, str):
            content_characters += len(content)
        mime_type = _value(document, "mime_type")
        if isinstance(mime_type, str) and mime_type:
            mime_types.add(mime_type)
        for field in _COLLECTION_FIELDS:
            values = _collection(_value(document, field))
            top_level[field] += len(values)
            observed.extend(values)
        nested_document = _value(document, "document")
        if nested_document is not None:
            for field in _COLLECTION_FIELDS:
                values = _collection(_value(nested_document, field))
                nested[field] += len(values)
                observed.extend(values)

    native_id_count = sum(
        _has_value(item, ("id", "element_id", "element_index"))
        for item in observed
    )
    offset_field_count = sum(_has_value(item, _OFFSET_NAMES) for item in observed)
    page_value_count = sum(
        _has_value(item, ("page", "page_no", "page_number")) for item in observed
    )
    geometry_value_count = sum(
        _has_value(item, ("bbox", "bounding_box", "coordinates")) for item in observed
    )
    relationship_value_count = sum(
        _has_value(item, ("parent", "children", "relationships", "references"))
        for item in observed
    )
    reading_order_value_count = sum(
        _has_value(item, ("reading_order", "ordinal", "order", "element_index"))
        for item in observed
    )
    findings: list[str] = []
    if content_characters == 0:
        findings.append("content_empty")
    if not observed:
        findings.append("structure_not_exposed")
    return ProbeResult(
        schema_version=PROBE_SCHEMA_VERSION,
        label=case.label,
        format=case.format,
        source_path=str(source),
        source_digest=source_digest,
        xberg_version=xberg_version,
        status="ok",
        result_count=len(documents),
        content_characters=content_characters,
        mime_types=tuple(sorted(mime_types)),
        top_level_collections=tuple(sorted(top_level.items())),
        nested_collections=tuple(sorted(nested.items())),
        native_id_count=native_id_count,
        offset_field_count=offset_field_count,
        page_value_count=page_value_count,
        geometry_value_count=geometry_value_count,
        relationship_value_count=relationship_value_count,
        reading_order_value_count=reading_order_value_count,
        native_ids=_observed_values(
            observed,
            ("id", "element_id", "element_index"),
        ),
        offsets=_observed_values(observed, _OFFSET_NAMES),
        pages=_observed_values(
            observed,
            ("page", "page_no", "page_number"),
        ),
        geometry=_observed_values(
            observed,
            ("bbox", "bounding_box", "coordinates"),
        ),
        relationships=_observed_values(
            observed,
            ("parent", "children", "relationships", "references"),
        ),
        reading_order=_observed_values(
            observed,
            ("reading_order", "ordinal", "order", "element_index"),
        ),
        findings=tuple(findings),
    )


async def run_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = value.get("cases", ())
    if not isinstance(raw_cases, list):
        raise ValueError("probe manifest cases must be a list")
    cases = tuple(
        ProbeCase(
            label=str(item["label"]),
            format=str(item["format"]),
            path=str(item["path"]),
            path_kind=str(item.get("path_kind", "file")),
        )
        for item in raw_cases
        if isinstance(item, dict)
    )
    results = tuple(
        [await probe_case(case, base_dir=path.parent) for case in cases]
    )
    payload = {
        "schema_version": PROBE_SCHEMA_VERSION,
        "manifest": str(path.resolve()),
        "results": [asdict(result) for result in results],
    }
    payload["content_digest"] = _json_digest(payload)
    return payload


class _materialized_source:
    def __init__(self, source: Path, path_kind: str) -> None:
        self.source = source
        self.path_kind = path_kind
        self._temporary: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if self.path_kind == "file":
            if not self.source.is_file():
                raise ValueError(f"expected file source: {self.source}")
            return self.source
        if self.path_kind != "epub_directory":
            raise ValueError(f"unsupported probe path_kind: {self.path_kind}")
        if not self.source.is_dir():
            raise ValueError(f"expected EPUB directory: {self.source}")
        self._temporary = tempfile.TemporaryDirectory(prefix="readwelt-xberg-probe-")
        output = Path(self._temporary.name) / "source.epub"
        _pack_epub(self.source, output)
        return output

    def __exit__(self, *_args: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()


def _pack_epub(source: Path, output: Path) -> None:
    mimetype = source / "mimetype"
    if not mimetype.exists():
        raise ValueError(f"EPUB directory has no mimetype file: {source}")
    with zipfile.ZipFile(output, "w") as archive:
        archive.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            if path == mimetype:
                continue
            archive.write(
                path,
                path.relative_to(source).as_posix(),
                compress_type=zipfile.ZIP_DEFLATED,
            )


def _missing(case: ProbeCase, source: Path, finding: str) -> ProbeResult:
    return ProbeResult(
        schema_version=PROBE_SCHEMA_VERSION,
        label=case.label,
        format=case.format,
        source_path=str(source),
        source_digest=None,
        xberg_version=version("xberg") if finding != "xberg_not_installed" else "unavailable",
        status="missing",
        result_count=0,
        content_characters=0,
        mime_types=(),
        top_level_collections=(),
        nested_collections=(),
        native_id_count=0,
        offset_field_count=0,
        page_value_count=0,
        geometry_value_count=0,
        relationship_value_count=0,
        reading_order_value_count=0,
        native_ids=(),
        offsets=(),
        pages=(),
        geometry=(),
        relationships=(),
        reading_order=(),
        findings=(finding,),
    )


def _collection(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Mapping):
        return tuple(value.values())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _has_value(value: Any, names: Sequence[str]) -> int:
    return int(any(_value(value, name) is not None for name in names))


def _observed_values(
    values: Sequence[Any],
    names: Sequence[str],
    *,
    limit: int = 64,
) -> tuple[tuple[str, str], ...]:
    observed: list[tuple[str, str]] = []
    for value in values:
        for name in names:
            item = _value(value, name)
            if item is None:
                continue
            record = (name, _stable_value(item))
            if record not in observed:
                observed.append(record)
            if len(observed) >= limit:
                return tuple(observed)
    return tuple(observed)


def _stable_value(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        rendered = str(value)
    else:
        try:
            rendered = json.dumps(
                value,
                default=str,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            rendered = str(value)
    return rendered[:512]


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(child for child in path.rglob("*") if child.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _json_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = asyncio.run(run_manifest(args.manifest.resolve()))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

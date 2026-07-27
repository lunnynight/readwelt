"""Deterministically package the pinned local EPUB acceptance source."""

from __future__ import annotations

import zipfile
from pathlib import Path

from benchmarks.articlegraph.corpus import (
    _file_digest,
    _load_manifest_case,
    _tree_digest,
)

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def prepare_epub(manifest_path: Path, case_id: str) -> tuple[Path, str]:
    manifest_path = manifest_path.resolve()
    case = _load_manifest_case(manifest_path, case_id)
    if case.get("format") != "epub":
        raise ValueError(f"case is not an EPUB: {case_id}")
    provenance = case.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("kind") != "local_pinned_corpus":
        raise ValueError("EPUB preparation requires local_pinned_corpus provenance")
    source = (manifest_path.parent / str(provenance["source_path"])).resolve()
    expected_source_digest = str(provenance["source_digest"])
    source_digest = _tree_digest(source)
    if source_digest != expected_source_digest:
        raise ValueError(
            f"source tree digest mismatch: expected {expected_source_digest}, got {source_digest}"
        )
    output = (manifest_path.parent / str(case["path"])).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    _pack_epub(source, output)
    digest = _file_digest(output)
    return output, digest


def _pack_epub(source: Path, output: Path) -> None:
    mimetype = source / "mimetype"
    if mimetype.read_bytes() != b"application/epub+zip":
        raise ValueError("source EPUB mimetype is invalid")
    files = sorted(item for item in source.rglob("*") if item.is_file())
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        _write_member(archive, mimetype, "mimetype")
        for item in files:
            if item == mimetype:
                continue
            _write_member(archive, item, item.relative_to(source).as_posix())


def _write_member(archive: zipfile.ZipFile, source: Path, name: str) -> None:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, source.read_bytes())


def main() -> int:
    manifest = Path(__file__).with_name("corpus_manifest.json")
    output, digest = prepare_epub(manifest, "first-principles-zh-epub")
    print(f"path={output} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

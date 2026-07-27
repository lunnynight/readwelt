"""Probe the optional Docling structural fallback without model downloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

from readwelt.runner.docling import (
    DOCLING_PACKAGE_VERSION,
    DoclingStructuralFallback,
)


def run(
    sources: tuple[tuple[str, Path], ...],
    *,
    artifacts_path: Path | None,
) -> dict[str, Any]:
    if artifacts_path is None:
        with tempfile.TemporaryDirectory(
            prefix="readwelt-docling-empty-models-"
        ) as temporary:
            return _run(sources, Path(temporary), "empty_local_artifacts_control")
    resolved = artifacts_path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"Docling artifacts path is not a directory: {resolved}")
    return _run(sources, resolved, "configured_local_artifacts")


def _run(
    sources: tuple[tuple[str, Path], ...],
    artifacts_path: Path,
    artifact_mode: str,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    fallback = DoclingStructuralFallback(artifacts_path=artifacts_path)
    for label, source in sources:
        resolved = source.resolve()
        if not resolved.is_file():
            raise ValueError(f"probe source is missing: {resolved}")
        started = time.perf_counter()
        result = fallback.project(
            resolved,
            trigger="real_fixture_probe",
        )
        text_layer_characters, source_pages = _pdf_text_layer(resolved)
        geometry = [
            {
                "element_id": item.element_id,
                "kind": item.kind,
                "content_layer": item.content_layer,
                "page": item.page,
                "bounding_box": item.bounding_box,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
            }
            for item in result.structure
            if item.page is not None or item.bounding_box is not None
        ]
        reference_closure = _structure_reference_closure(result.structure)
        results.append(
            {
                "label": label,
                "source_path": str(resolved),
                "source_digest": _file_digest(resolved),
                "elapsed_ms": (time.perf_counter() - started) * 1_000,
                "text_characters": len(result.text or ""),
                "text_sample": (result.text or "")[:400],
                "source_pages": source_pages,
                "source_text_layer_characters": text_layer_characters,
                "ocr_observed": (
                    text_layer_characters == 0 and bool(result.text)
                ),
                "structure_records": len(result.structure),
                "geometry_records": len(geometry),
                "geometry_sample": geometry[:8],
                "structural_reference_closure": reference_closure,
                "pages": sorted(
                    {item.page for item in result.structure if item.page is not None}
                ),
                "kinds": sorted(
                    {item.kind for item in result.structure if item.kind is not None}
                ),
                "content_layers": {
                    layer: sum(item.content_layer == layer for item in result.structure)
                    for layer in sorted(
                        {
                            item.content_layer
                            for item in result.structure
                            if item.content_layer is not None
                        }
                    )
                },
                "findings": list(result.findings),
                "status": (
                    "structure_available"
                    if result.structure
                    else "blocked_or_failed"
                ),
            }
        )
    payload: dict[str, Any] = {
        "schema_version": "docling-structural-fallback-probe.v1",
        "docling_package_version": version("docling"),
        "required_docling_package_version": DOCLING_PACKAGE_VERSION,
        "dependency_versions": {
            package: version(package)
            for package in (
                "docling",
                "docling-core",
                "docling-parse",
                "onnxruntime",
                "rapidocr",
            )
        },
        "model_artifact_mode": artifact_mode,
        "model_artifacts": _artifact_manifest(artifacts_path),
        "implicit_model_download_allowed": False,
        "content_digest_scope": "all_fields_except_elapsed_ms",
        "results": results,
    }
    payload["content_digest"] = _digest(
        {
            **payload,
            "results": [
                {
                    key: value
                    for key, value in result.items()
                    if key != "elapsed_ms"
                }
                for result in results
            ],
        }
    )
    return payload


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _structure_reference_closure(structure: tuple[Any, ...]) -> dict[str, Any]:
    identities = {
        item.element_id
        for item in structure
        if item.element_id is not None
    }
    parent_references = {
        item.parent_element_id
        for item in structure
        if item.parent_element_id is not None
    }
    child_references = {
        child
        for item in structure
        for child in item.child_element_ids
    }
    relation_references = {
        target
        for item in structure
        for _, target in item.structural_relations
    }
    return {
        "identity_records": len(identities),
        "anonymous_records": len(structure) - len(identities),
        "parent_references": len(parent_references),
        "child_references": len(child_references),
        "relation_references": len(relation_references),
        "unresolved_parent_references": sorted(parent_references - identities),
        "unresolved_child_references": sorted(child_references - identities),
        "unresolved_relation_references": sorted(
            relation_references - identities
        ),
    }


def _artifact_manifest(path: Path) -> dict[str, Any]:
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total_bytes = 0
    for item in files:
        relative = item.relative_to(path).as_posix()
        file_digest = _file_digest(item)
        size = item.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\n")
        total_bytes += size
    return {
        "path": str(path.resolve()),
        "download_command": (
            "docling-tools models download layout tableformer rapidocr "
            "-o .research-inputs/docling-artifacts --quiet"
        ),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "tree_digest": f"sha256:{digest.hexdigest()}",
        "sources": [
            {
                "name": "layout",
                "repository": "https://huggingface.co/docling-project/docling-layout-heron",
                "resolved_revisions": _hf_revisions(
                    path / "docling-project--docling-layout-heron"
                ),
            },
            {
                "name": "tableformer",
                "repository": "https://huggingface.co/docling-project/docling-models",
                "resolved_revisions": _hf_revisions(
                    path / "docling-project--docling-models"
                ),
            },
            {
                "name": "rapidocr",
                "repository": "https://www.modelscope.cn/models/RapidAI/RapidOCR",
                "release": "v3.9.0",
            },
        ],
    }


def _hf_revisions(path: Path) -> list[str]:
    return sorted(
        item.stem
        for item in path.glob(".cache/huggingface/trees/*.json")
    )


def _pdf_text_layer(path: Path) -> tuple[int, int]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    characters = 0
    page_count = len(document)
    try:
        for page_index in range(page_count):
            page = document[page_index]
            try:
                text_page = page.get_textpage()
                try:
                    characters += len(text_page.get_text_range())
                finally:
                    text_page.close()
            finally:
                page.close()
    finally:
        document.close()
    return characters, page_count


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--native-pdf",
        type=Path,
        default=Path(
            ".research-checkouts/kag/tests/unit/builder/data/KnowledgeGraphTutorialSub.pdf"
        ),
    )
    parser.add_argument(
        "--scanned-pdf",
        type=Path,
        default=Path(
            ".research-checkouts/docling-graph/tests/fixtures/sample_documents/sample.pdf"
        ),
    )
    parser.add_argument("--artifacts-path", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/docling-structural-fallback-probe-2026-07-27.json"),
    )
    args = parser.parse_args()
    payload = run(
        (
            ("native_pdf", args.native_pdf),
            ("scanned_pdf", args.scanned_pdf),
        ),
        artifacts_path=args.artifacts_path,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

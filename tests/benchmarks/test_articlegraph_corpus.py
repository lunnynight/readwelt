from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.articlegraph.corpus import (
    REQUIRED_FEATURES,
    REQUIRED_FORMATS,
    REQUIRED_LANGUAGES,
    REQUIRED_STRUCTURES,
    validate_corpus_manifest,
)
from benchmarks.articlegraph.corpus_prepare import prepare_epub

_MANIFEST = Path(__file__).parents[2] / "benchmarks" / "articlegraph" / "corpus_manifest.json"


def _manifest_cases() -> list[dict[str, object]]:
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    return payload["cases"]


def _require_case_sources(*case_ids: str) -> None:
    selected = {
        str(case["id"]): case
        for case in _manifest_cases()
        if not case_ids or str(case["id"]) in case_ids
    }
    missing = [
        case_id
        for case_id, case in selected.items()
        if not (_MANIFEST.parent / str(case["path"])).resolve().is_file()
    ]
    if missing:
        pytest.skip("real ArticleGraph corpus is not materialized: " + ", ".join(missing))


def _require_epub_source(case_id: str) -> None:
    case = next(case for case in _manifest_cases() if case["id"] == case_id)
    provenance = case["provenance"]
    assert isinstance(provenance, dict)
    source = (_MANIFEST.parent / str(provenance["source_path"])).resolve()
    if not source.is_dir():
        pytest.skip(f"local EPUB source tree is not materialized: {case_id}")


def test_real_acceptance_corpus_is_complete_and_format_valid() -> None:
    _require_case_sources()
    report = validate_corpus_manifest(_MANIFEST)

    assert report.valid, tuple(
        (issue.case_id, issue.code, issue.detail)
        for issue in (
            *report.issues,
            *(issue for case in report.case_results for issue in case.issues),
        )
    )
    assert set(report.formats) >= REQUIRED_FORMATS
    assert set(report.languages) >= REQUIRED_LANGUAGES
    assert set(report.structures) >= REQUIRED_STRUCTURES
    assert set(report.coverage_tags) >= REQUIRED_FEATURES


def test_local_epub_preparation_is_byte_deterministic() -> None:
    _require_epub_source("first-principles-zh-epub")
    output, first_digest = prepare_epub(_MANIFEST, "first-principles-zh-epub")
    first_bytes = output.read_bytes()
    output, second_digest = prepare_epub(_MANIFEST, "first-principles-zh-epub")

    assert output.read_bytes() == first_bytes
    assert first_digest == second_digest
    assert first_digest == f"sha256:{hashlib.sha256(first_bytes).hexdigest()}"


def test_manifest_digest_change_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    payload["cases"][0]["sha256"] = "sha256:" + ("0" * 64)
    tampered = tmp_path / "corpus_manifest.json"
    tampered.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = validate_corpus_manifest(
        tampered,
        source_base_dir=_MANIFEST.parent,
        repo_root=_MANIFEST.parents[2],
    )

    assert not report.valid
    assert any(
        issue.code in {"digest_mismatch", "path_outside_repository", "source_missing"}
        for issue in (
            *report.issues,
            *(issue for case in report.case_results for issue in case.issues),
        )
    )


def test_manifest_missing_required_coverage_fails_early(tmp_path: Path) -> None:
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    payload["cases"] = [case for case in payload["cases"] if case["format"] != "scanned_pdf"]
    incomplete = tmp_path / "corpus_manifest.json"
    incomplete.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = validate_corpus_manifest(
        incomplete,
        source_base_dir=_MANIFEST.parent,
        repo_root=_MANIFEST.parents[2],
    )

    assert not report.valid
    assert any(
        issue.code == "required_format_missing" and issue.detail == "scanned_pdf"
        for issue in report.issues
    )


def test_native_pdf_cannot_be_relabelled_as_scanned(tmp_path: Path) -> None:
    _require_case_sources(
        "kag-knowledge-graph-tutorial-native-pdf",
        "docling-graph-image-only-scanned-pdf",
    )
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    native_case = next(case for case in payload["cases"] if case["format"] == "native_pdf")
    scanned_case = next(case for case in payload["cases"] if case["format"] == "scanned_pdf")
    native_case["format"] = "scanned_pdf"
    scanned_case["format"] = "native_pdf"
    tampered = tmp_path / "corpus_manifest.json"
    tampered.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = validate_corpus_manifest(
        tampered,
        source_base_dir=_MANIFEST.parent,
        repo_root=_MANIFEST.parents[2],
    )

    assert not report.valid
    issue_codes = {issue.code for case in report.case_results for issue in case.issues}
    assert "scanned_pdf_has_text_layer" in issue_codes
    assert "native_pdf_text_layer_missing" in issue_codes

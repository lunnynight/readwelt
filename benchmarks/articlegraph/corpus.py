"""Strict validation for the real ArticleGraph acceptance corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from benchmarks.articlegraph.corpus_formats import (
    FormatObservation,
    expectation_values,
    inspect_epub,
    inspect_html,
    inspect_pdf,
    inspect_text,
)

CORPUS_SCHEMA_VERSION: Final = "articlegraph-acceptance-corpus.v1"
REQUIRED_FORMATS: Final = frozenset({"txt", "html", "native_pdf", "scanned_pdf", "epub"})
REQUIRED_LANGUAGES: Final = frozenset({"zh", "en"})
REQUIRED_STRUCTURES: Final = frozenset({"argument", "exposition", "narrative"})
REQUIRED_FEATURES: Final = frozenset(
    {
        "repeated_passages",
        "quotations",
        "tables",
        "figures",
        "captions",
        "numbers",
        "missing_structure",
        "long_document",
    }
)


@dataclass(frozen=True, slots=True)
class CorpusIssue:
    code: str
    detail: str
    case_id: str | None = None


@dataclass(frozen=True, slots=True)
class CorpusCaseResult:
    case_id: str
    format: str
    path: str
    digest: str | None
    observation: FormatObservation | None
    issues: tuple[CorpusIssue, ...]


@dataclass(frozen=True, slots=True)
class CorpusValidationReport:
    schema_version: str
    manifest_path: str
    case_results: tuple[CorpusCaseResult, ...]
    formats: tuple[str, ...]
    languages: tuple[str, ...]
    structures: tuple[str, ...]
    coverage_tags: tuple[str, ...]
    issues: tuple[CorpusIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues and all(not case.issues for case in self.case_results)


def validate_corpus_manifest(
    manifest_path: Path,
    *,
    source_base_dir: Path | None = None,
    repo_root: Path | None = None,
) -> CorpusValidationReport:
    manifest_path = manifest_path.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("corpus manifest root must be an object")
    issues: list[CorpusIssue] = []
    schema_version = payload.get("schema_version")
    if schema_version != CORPUS_SCHEMA_VERSION:
        issues.append(
            CorpusIssue(
                "schema_version_mismatch",
                f"expected {CORPUS_SCHEMA_VERSION}, received {schema_version!r}",
            )
        )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("corpus manifest cases must be a non-empty list")

    source_base_dir = (
        manifest_path.parent if source_base_dir is None else source_base_dir.resolve()
    )
    repo_root = _repo_root(manifest_path) if repo_root is None else repo_root.resolve()
    case_results: list[CorpusCaseResult] = []
    identifiers: set[str] = set()
    formats: set[str] = set()
    languages: set[str] = set()
    structures: set[str] = set()
    coverage_tags: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("every corpus case must be an object")
        result = _validate_case(raw_case, source_base_dir, repo_root)
        if result.case_id in identifiers:
            issues.append(
                CorpusIssue("duplicate_case_id", result.case_id, case_id=result.case_id)
            )
        identifiers.add(result.case_id)
        case_results.append(result)
        formats.add(result.format)
        languages.update(_string_set(raw_case.get("languages")))
        structures.update(_string_set(raw_case.get("structures")))
        coverage_tags.update(_string_set(raw_case.get("coverage_tags")))

    _require_coverage("format", REQUIRED_FORMATS, formats, issues)
    _require_coverage("language", REQUIRED_LANGUAGES, languages, issues)
    _require_coverage("structure", REQUIRED_STRUCTURES, structures, issues)
    _require_coverage("feature", REQUIRED_FEATURES, coverage_tags, issues)
    return CorpusValidationReport(
        schema_version=CORPUS_SCHEMA_VERSION,
        manifest_path=str(manifest_path),
        case_results=tuple(case_results),
        formats=tuple(sorted(formats)),
        languages=tuple(sorted(languages)),
        structures=tuple(sorted(structures)),
        coverage_tags=tuple(sorted(coverage_tags)),
        issues=tuple(issues),
    )


def _validate_case(
    case: dict[str, Any],
    base_dir: Path,
    repo_root: Path,
) -> CorpusCaseResult:
    case_id = str(case.get("id", "")).strip()
    format_name = str(case.get("format", "")).strip()
    relative_path = str(case.get("path", "")).strip()
    case_issues: list[CorpusIssue] = []
    if not case_id:
        case_issues.append(CorpusIssue("case_id_missing", "id is required"))
        case_id = "<missing>"
    if format_name not in REQUIRED_FORMATS:
        case_issues.append(
            CorpusIssue(
                "unsupported_format",
                f"unsupported corpus format: {format_name!r}",
                case_id,
            )
        )
    path = (base_dir / relative_path).resolve()
    if not path.is_relative_to(repo_root):
        case_issues.append(
            CorpusIssue("path_outside_repository", str(path), case_id)
        )
    if not path.is_file():
        case_issues.append(CorpusIssue("source_missing", str(path), case_id))
        return CorpusCaseResult(
            case_id,
            format_name,
            str(path),
            None,
            None,
            tuple(case_issues),
        )

    digest = _file_digest(path)
    expected_digest = case.get("sha256")
    if digest != expected_digest:
        case_issues.append(
            CorpusIssue(
                "digest_mismatch",
                f"expected {expected_digest!r}, observed {digest}",
                case_id,
            )
        )
    _validate_provenance(case, base_dir, repo_root, case_id, case_issues)
    try:
        observation = _inspect(format_name, path)
        expected = expectation_values(case.get("expected"))
        _validate_format_invariants(format_name, path, observation, case_id, case_issues)
        _validate_expectations(observation, expected, case_id, case_issues)
        _validate_language_evidence(case, observation, case_id, case_issues)
        _validate_feature_evidence(case, path, observation, case_id, case_issues)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        observation = None
        case_issues.append(CorpusIssue("format_validation_failed", str(exc), case_id))
    return CorpusCaseResult(
        case_id,
        format_name,
        str(path),
        digest,
        observation,
        tuple(case_issues),
    )


def _inspect(format_name: str, path: Path) -> FormatObservation:
    if format_name == "txt":
        return inspect_text(path)
    if format_name == "html":
        return inspect_html(path)
    if format_name in {"native_pdf", "scanned_pdf"}:
        return inspect_pdf(path)
    if format_name == "epub":
        return inspect_epub(path)
    raise ValueError(f"unsupported format: {format_name}")


def _validate_expectations(
    observation: FormatObservation,
    expected: dict[str, int],
    case_id: str,
    issues: list[CorpusIssue],
) -> None:
    observed = asdict(observation)
    for key, threshold in expected.items():
        if key.startswith("min_"):
            field = key.removeprefix("min_")
            actual = observed.get(field)
            if not isinstance(actual, int) or actual < threshold:
                issues.append(
                    CorpusIssue(
                        "minimum_not_met",
                        f"{field}: expected >= {threshold}, observed {actual!r}",
                        case_id,
                    )
                )
        elif key.startswith("max_"):
            field = key.removeprefix("max_")
            actual = observed.get(field)
            if not isinstance(actual, int) or actual > threshold:
                issues.append(
                    CorpusIssue(
                        "maximum_exceeded",
                        f"{field}: expected <= {threshold}, observed {actual!r}",
                        case_id,
                    )
                )


def _validate_format_invariants(
    format_name: str,
    path: Path,
    observation: FormatObservation,
    case_id: str,
    issues: list[CorpusIssue],
) -> None:
    expected_suffix = {
        "txt": ".txt",
        "html": ".html",
        "native_pdf": ".pdf",
        "scanned_pdf": ".pdf",
        "epub": ".epub",
    }.get(format_name)
    if expected_suffix is not None and path.suffix.casefold() != expected_suffix:
        issues.append(
            CorpusIssue(
                "format_extension_mismatch",
                f"{format_name} requires {expected_suffix}, observed {path.suffix}",
                case_id,
            )
        )
    if format_name == "native_pdf" and observation.text_characters == 0:
        issues.append(
            CorpusIssue(
                "native_pdf_text_layer_missing",
                "native PDF must expose a non-empty text layer",
                case_id,
            )
        )
    if format_name == "scanned_pdf":
        if observation.text_characters != 0:
            issues.append(
                CorpusIssue(
                    "scanned_pdf_has_text_layer",
                    (
                        "image-only scanned PDF must expose zero text characters; "
                        f"observed {observation.text_characters}"
                    ),
                    case_id,
                )
            )
        if observation.images == 0:
            issues.append(
                CorpusIssue(
                    "scanned_pdf_image_missing",
                    "image-only scanned PDF must contain at least one raster image",
                    case_id,
                )
            )


def _validate_feature_evidence(
    case: dict[str, Any],
    path: Path,
    observation: FormatObservation,
    case_id: str,
    issues: list[CorpusIssue],
) -> None:
    tags = _string_set(case.get("coverage_tags"))
    expected = expectation_values(case.get("expected"))
    if "long_document" in tags and expected.get("min_text_characters", 0) < 100_000:
        issues.append(
            CorpusIssue(
                "long_document_claim_unbounded",
                "long_document requires min_text_characters >= 100000",
                case_id,
            )
        )
    feature_fields = {
        "quotations": "quote_marks",
        "tables": "tables",
        "figures": "figures",
        "captions": "captions",
        "numbers": "numeric_tokens",
    }
    observed = asdict(observation)
    for tag, field in feature_fields.items():
        if tag in tags and observed[field] < 1:
            issues.append(
                CorpusIssue("feature_not_observed", f"{tag}: {field}=0", case_id)
            )
    if "missing_structure" in tags and observation.structural_markers != 0:
        issues.append(
            CorpusIssue(
                "structure_present",
                (
                    "expected no explicit structure, observed "
                    f"{observation.structural_markers} markers"
                ),
                case_id,
            )
        )
    repeated = case.get("repeated_passage")
    if "repeated_passages" in tags:
        if not isinstance(repeated, dict):
            issues.append(
                CorpusIssue(
                    "repeated_passage_evidence_missing",
                    "repeated_passage assertion is required",
                    case_id,
                )
            )
        else:
            needle = repeated.get("text")
            minimum = repeated.get("min_occurrences")
            if not isinstance(needle, str) or len(needle) < 40:
                issues.append(
                    CorpusIssue(
                        "repeated_passage_too_short",
                        "repeated passage evidence must contain at least 40 characters",
                        case_id,
                    )
                )
            elif not isinstance(minimum, int) or minimum < 2:
                issues.append(
                    CorpusIssue(
                        "repeated_passage_count_invalid",
                        "min_occurrences must be at least 2",
                        case_id,
                    )
                )
            else:
                text = path.read_text(encoding="utf-8")
                if text.count(needle) < minimum:
                    issues.append(
                        CorpusIssue(
                            "repeated_passage_not_observed",
                            f"expected {minimum} occurrences",
                            case_id,
                        )
                    )


def _validate_language_evidence(
    case: dict[str, Any],
    observation: FormatObservation,
    case_id: str,
    issues: list[CorpusIssue],
) -> None:
    languages = _string_set(case.get("languages"))
    if "zh" in languages and observation.chinese_characters == 0:
        issues.append(
            CorpusIssue(
                "language_not_observed",
                "zh requires at least one Chinese character",
                case_id,
            )
        )
    if (
        "en" in languages
        and observation.english_words == 0
        and case.get("format") != "scanned_pdf"
    ):
        issues.append(
            CorpusIssue(
                "language_not_observed",
                "en requires at least one English word",
                case_id,
            )
        )


def _validate_provenance(
    case: dict[str, Any],
    base_dir: Path,
    repo_root: Path,
    case_id: str,
    issues: list[CorpusIssue],
) -> None:
    provenance = case.get("provenance")
    if not isinstance(provenance, dict):
        issues.append(CorpusIssue("provenance_missing", "object required", case_id))
        return
    kind = provenance.get("kind")
    if kind == "git_checkout":
        checkout = (base_dir / str(provenance.get("checkout_root", ""))).resolve()
        if not checkout.is_relative_to(repo_root) or not (checkout / ".git").exists():
            issues.append(CorpusIssue("checkout_missing", str(checkout), case_id))
            return
        declared_source = (checkout / str(provenance.get("source_path", ""))).resolve()
        case_source = (base_dir / str(case.get("path", ""))).resolve()
        if declared_source != case_source:
            issues.append(
                CorpusIssue(
                    "provenance_source_mismatch",
                    f"declared {declared_source}, case uses {case_source}",
                    case_id,
                )
            )
        revision = _git(checkout, "rev-parse", "HEAD")
        if revision != provenance.get("revision"):
            issues.append(
                CorpusIssue(
                    "checkout_revision_mismatch",
                    f"expected {provenance.get('revision')!r}, observed {revision!r}",
                    case_id,
                )
            )
        origin = _git(checkout, "remote", "get-url", "origin")
        if _normalize_repository(origin) != _normalize_repository(
            str(provenance.get("repository", ""))
        ):
            issues.append(
                CorpusIssue(
                    "checkout_origin_mismatch",
                    f"expected {provenance.get('repository')!r}, observed {origin!r}",
                    case_id,
                )
            )
    elif kind == "local_pinned_corpus":
        source = (base_dir / str(provenance.get("source_path", ""))).resolve()
        if not source.is_relative_to(repo_root) or not source.is_dir():
            issues.append(CorpusIssue("pinned_source_missing", str(source), case_id))
            return
        observed_digest = _tree_digest(source)
        if observed_digest != provenance.get("source_digest"):
            issues.append(
                CorpusIssue(
                    "pinned_source_digest_mismatch",
                    (
                        f"expected {provenance.get('source_digest')!r}, "
                        f"observed {observed_digest!r}"
                    ),
                    case_id,
                )
            )
    elif kind == "remote_artifact":
        source_url = provenance.get("source_url")
        source_page = provenance.get("source_page")
        retrieved_at = provenance.get("retrieved_at")
        if not (
            isinstance(source_url, str)
            and source_url.startswith("https://")
            and isinstance(source_page, str)
            and source_page.startswith("https://")
            and isinstance(retrieved_at, str)
            and retrieved_at
        ):
            issues.append(
                CorpusIssue(
                    "remote_provenance_incomplete",
                    "source_url, source_page, and retrieved_at are required",
                    case_id,
                )
            )
    else:
        issues.append(
            CorpusIssue("provenance_kind_invalid", f"unsupported kind: {kind!r}", case_id)
        )
    if not isinstance(provenance.get("license"), str) or not provenance["license"].strip():
        issues.append(CorpusIssue("license_missing", "license is required", case_id))
    benchmark = case.get("benchmark")
    if not isinstance(benchmark, dict):
        issues.append(CorpusIssue("benchmark_annotation_missing", "object required", case_id))
    else:
        queries = benchmark.get("must_hit_queries")
        if case.get("format") == "scanned_pdf":
            if queries not in ([], None):
                issues.append(
                    CorpusIssue(
                        "scanned_pdf_queries_invalid",
                        "image-only scanned PDF cannot declare text must-hits before OCR",
                        case_id,
                    )
                )
        elif not (
            isinstance(queries, list)
            and queries
            and all(isinstance(query, str) and query.strip() for query in queries)
        ):
            issues.append(
                CorpusIssue(
                    "must_hit_queries_missing",
                    "non-scanned cases require text must-hit queries",
                    case_id,
                )
            )


def _git(path: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(path), *arguments),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _load_manifest_case(manifest_path: Path, case_id: str) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("corpus manifest root must be an object")
    if payload.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise ValueError("unsupported corpus manifest schema")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("manifest cases must be a list")
    matches = [
        case
        for case in cases
        if isinstance(case, dict) and case.get("id") == case_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one case named {case_id!r}")
    return matches[0]


def _normalize_repository(value: str) -> str:
    return value.removesuffix(".git").rstrip("/")


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(child for child in path.rglob("*") if child.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _repo_root(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ValueError(f"manifest is not inside a Git repository: {path}")


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return set()
    return {item for item in value if item}


def _require_coverage(
    kind: str,
    required: frozenset[str],
    observed: set[str],
    issues: list[CorpusIssue],
) -> None:
    for value in sorted(required - observed):
        issues.append(CorpusIssue(f"required_{kind}_missing", value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest",
        type=Path,
        nargs="?",
        default=Path(__file__).with_name("corpus_manifest.json"),
    )
    args = parser.parse_args()
    report = validate_corpus_manifest(args.manifest)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

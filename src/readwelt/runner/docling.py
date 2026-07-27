"""Optional Docling PDF/OCR structure projection behind the Xberg entrypoint."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol, cast

from readwelt.runner.snapshot import SectionStructure

DOCLING_PACKAGE_VERSION = "2.114.0"
DOCLING_ARTIFACTS_ENV = "READWELT_DOCLING_ARTIFACTS_PATH"
DOCLING_ADAPTER_VERSION = "readwelt.docling-structural-fallback.v1"
DOCLING_MODEL_ARTIFACT_DIGEST = (
    "sha256:117ce0d7c9486c4bb9b53a11b5fe5f2035bf192997cf4915b5cb99f97389a202"
)


class Converter(Protocol):
    def convert(self, source: Path) -> Any: ...


class StructuralFallback(Protocol):
    def project(self, source: Path, *, trigger: str) -> StructuralFallbackResult: ...


@dataclass(frozen=True, slots=True)
class StructuralFallbackResult:
    text: str | None
    structure: tuple[SectionStructure, ...]
    findings: tuple[str, ...]


class DoclingStructuralFallback:
    """Project a DoclingDocument; never download models implicitly."""

    def __init__(
        self,
        *,
        converter: Converter | None = None,
        artifacts_path: Path | None = None,
        ocr_languages: Sequence[str] = ("english",),
    ) -> None:
        self._injected_converter = converter
        configured_path = (
            artifacts_path
            if artifacts_path is not None
            else (
                Path(configured) if (configured := os.environ.get(DOCLING_ARTIFACTS_ENV)) else None
            )
        )
        self._artifacts_path = (
            configured_path.expanduser().resolve() if configured_path is not None else None
        )
        self._ocr_languages = tuple(ocr_languages)

    def project(self, source: Path, *, trigger: str) -> StructuralFallbackResult:
        findings = [
            f"docling_fallback_invoked:docling=={DOCLING_PACKAGE_VERSION}",
            f"docling_fallback_trigger:{trigger}",
            f"docling_fallback_adapter:{DOCLING_ADAPTER_VERSION}",
        ]
        if self._injected_converter is None:
            findings.extend(
                (
                    "docling_fallback_backend:production",
                    f"docling_fallback_model_artifacts:{DOCLING_MODEL_ARTIFACT_DIGEST}",
                    "docling_fallback_ocr_backend:onnxruntime",
                    "docling_fallback_model_licenses:Apache-2.0,CDLA-Permissive-2.0,Apache-2.0",
                    "docling_fallback_capabilities:"
                    "layout,reading_order,table,figure,caption,page,geometry,ocr",
                    "docling_fallback_ocr_languages:" + ",".join(self._ocr_languages),
                )
            )
        else:
            findings.append("docling_fallback_backend:injected_test_double")
        try:
            converter = self._injected_converter or self._production_converter()
            conversion = converter.convert(source.resolve())
            document = getattr(conversion, "document", None)
            if document is None:
                raise ValueError("conversion result has no DoclingDocument")
            status = _enum_text(getattr(conversion, "status", None))
            if status is not None:
                findings.append(f"docling_fallback_conversion_status:{status}")
            findings.extend(_conversion_error_findings(conversion))
            text, text_finding = _document_text(document)
            if text_finding is not None:
                findings.append(text_finding)
            structure = _document_structure(document)
            findings.extend(
                (
                    f"docling_fallback_text_characters:{len(text or '')}",
                    f"docling_fallback_structure_records:{len(structure)}",
                    "docling_fallback_remote_services:false",
                    "docling_fallback_external_plugins:false",
                )
            )
            if not structure:
                findings.append("docling_fallback_structure_empty")
            return StructuralFallbackResult(
                text=text,
                structure=structure,
                findings=tuple(findings),
            )
        except ModuleNotFoundError:
            findings.append("docling_fallback_unavailable:optional_dependency_missing")
        except PackageNotFoundError:
            findings.append("docling_fallback_unavailable:package_metadata_missing")
        except _LocalArtifactsRequired:
            findings.append(f"docling_fallback_blocked:{DOCLING_ARTIFACTS_ENV}_required")
        except _LocalArtifactsUnavailable:
            findings.append("docling_fallback_blocked:local_model_artifacts_unavailable")
        except _PackageVersionMismatch:
            findings.append("docling_fallback_blocked:package_version_mismatch")
        except Exception as error:  # Docling and OCR engines expose varied failures.
            findings.append(f"docling_fallback_failed:{type(error).__name__}")
        return StructuralFallbackResult(
            text=None,
            structure=(),
            findings=tuple(findings),
        )

    def _production_converter(self) -> Converter:
        if self._artifacts_path is None or not self._artifacts_path.is_dir():
            raise _LocalArtifactsRequired
        if not any(self._artifacts_path.iterdir()):
            raise _LocalArtifactsUnavailable
        if version("docling") != DOCLING_PACKAGE_VERSION:
            raise _PackageVersionMismatch

        base_models = import_module("docling.datamodel.base_models")
        pipeline_models = import_module("docling.datamodel.pipeline_options")
        converter_models = import_module("docling.document_converter")
        input_format = base_models.InputFormat
        pdf_pipeline_options = pipeline_models.PdfPipelineOptions
        rapidocr_options = pipeline_models.RapidOcrOptions
        document_converter = converter_models.DocumentConverter
        pdf_format_option = converter_models.PdfFormatOption

        pipeline_options = pdf_pipeline_options(
            artifacts_path=self._artifacts_path,
            do_ocr=True,
            do_table_structure=True,
            ocr_options=rapidocr_options(
                lang=list(self._ocr_languages),
                backend="onnxruntime",
            ),
            enable_remote_services=False,
            allow_external_plugins=False,
            document_timeout=120.0,
            ocr_batch_size=1,
            layout_batch_size=1,
            table_batch_size=1,
            queue_max_size=2,
        )
        return cast(
            Converter,
            document_converter(
                format_options={
                    input_format.PDF: pdf_format_option(
                        pipeline_options=pipeline_options,
                    )
                }
            ),
        )


class _LocalArtifactsRequired(RuntimeError):
    pass


class _PackageVersionMismatch(RuntimeError):
    pass


class _LocalArtifactsUnavailable(RuntimeError):
    pass


def _conversion_error_findings(conversion: Any) -> tuple[str, ...]:
    errors = _sequence(_value(conversion, "errors"))
    if not errors:
        return ()
    findings = [f"docling_fallback_conversion_errors:{len(errors)}"]
    for error in errors[:8]:
        component = _enum_text(_value(error, "component_type")) or "unknown"
        category = _enum_text(_value(error, "category")) or "unknown"
        message = _text(_value(error, "error_message")) or "unspecified"
        normalized_message = " ".join(message.split())[:240]
        findings.append(
            f"docling_fallback_conversion_error:{component}:{category}:{normalized_message}"
        )
    return tuple(findings)


def _document_text(document: Any) -> tuple[str | None, str | None]:
    export = getattr(document, "export_to_text", None)
    if not callable(export):
        return None, "docling_fallback_text_unavailable:no_export_to_text"
    try:
        value = export()
    except Exception as error:
        return None, f"docling_fallback_text_failed:{type(error).__name__}"
    return (
        (value if isinstance(value, str) and value else None),
        None,
    )


def _document_structure(document: Any) -> tuple[SectionStructure, ...]:
    iterate = getattr(document, "iterate_items", None)
    if not callable(iterate):
        return ()
    records: list[SectionStructure] = []
    headings: list[str] = []
    values = _iterate_document_items(iterate)
    for ordinal, entry in enumerate(_document_items(document, values)):
        item, level, detached = entry
        kind = _enum_text(_value(item, "label"))
        text = _text(_value(item, "text")) or _text(_value(item, "orig"))
        normalized_kind = _normalized_kind(kind)
        if normalized_kind in {"title", "section_header"} and text is not None:
            headings = headings[: max(level, 0)]
            headings.append(text)
        provenance = _first(_value(item, "prov"))
        native_reference = _reference(item)
        record = SectionStructure(
            exact_text=text,
            kind=normalized_kind,
            content_layer=_enum_text(_value(item, "content_layer")),
            parent_element_id=_docling_id(_reference(_value(item, "parent"))),
            child_element_ids=tuple(
                identity
                for child in _sequence(_value(item, "children"))
                if (identity := _docling_id(_reference(child))) is not None
            ),
            structural_relations=_relations(item),
            heading_trail=() if detached else tuple(headings),
            element_id=_docling_id(native_reference),
            reading_order=ordinal,
            page=_positive_int(_value(provenance, "page_no")),
            bounding_box=_bbox(_value(provenance, "bbox")),
            start_offset=_charspan(provenance)[0],
            end_offset=_charspan(provenance)[1],
            native_reference=native_reference,
            raw_payload=_model_payload(item),
        )
        if record.exact_text is not None or record.kind is not None:
            records.append(record)
    return tuple(records)


def _iterate_document_items(iterate: Any) -> Iterable[Any]:
    """Request Docling's complete structural traversal with legacy fallbacks."""

    try:
        content_layer_module = import_module("docling_core.types.doc")
        content_layers = set(content_layer_module.ContentLayer)
    except (ModuleNotFoundError, AttributeError):
        content_layers = None
    if content_layers is not None:
        try:
            return cast(
                Iterable[Any],
                iterate(
                    with_groups=True,
                    traverse_pictures=True,
                    included_content_layers=content_layers,
                ),
            )
        except TypeError:
            pass
    try:
        return cast(
            Iterable[Any],
            iterate(with_groups=True, traverse_pictures=True),
        )
    except TypeError:
        pass
    try:
        return cast(Iterable[Any], iterate(with_groups=True))
    except TypeError:
        return cast(Iterable[Any], iterate())


def _document_items(
    document: Any,
    values: Iterable[Any],
) -> tuple[tuple[Any, int, bool], ...]:
    entries = [(item, level, False) for item, level in _items(values)]
    seen = {reference for item, _, _ in entries if (reference := _reference(item)) is not None}
    for collection_name in (
        "body",
        "furniture",
        "groups",
        "texts",
        "pictures",
        "tables",
        "key_value_items",
        "form_items",
        "field_regions",
        "field_items",
    ):
        value = _value(document, collection_name)
        candidates = _sequence(value) if collection_name not in {"body", "furniture"} else (value,)
        for item in candidates:
            reference = _reference(item)
            if item is None or reference is None or reference in seen:
                continue
            entries.append((item, 0, True))
            seen.add(reference)
    return tuple(entries)


def _items(values: Iterable[Any]) -> Iterable[tuple[Any, int]]:
    for value in values:
        if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], int):
            yield value[0], value[1]
        else:
            yield value, 0


def _relations(item: Any) -> tuple[tuple[str, str], ...]:
    relations: list[tuple[str, str]] = []
    for relation in ("captions", "references", "footnotes"):
        for target in _sequence(_value(item, relation)):
            target_id = _docling_id(_reference(target))
            if target_id is not None:
                relations.append((relation.removesuffix("s"), target_id))
    return tuple(dict.fromkeys(relations))


def _reference(value: Any) -> str | None:
    if value is None:
        return None
    for name in ("cref", "self_ref", "$ref", "ref"):
        found = _value(value, name)
        if isinstance(found, str) and found:
            return found
    if isinstance(value, str) and value:
        return value
    return None


def _docling_id(reference: str | None) -> str | None:
    return f"docling:{reference}" if reference is not None else None


def _first(value: Any) -> Any:
    values = _sequence(value)
    return values[0] if values else None


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _charspan(provenance: Any) -> tuple[int | None, int | None]:
    value = _value(provenance, "charspan")
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(item, int) and item >= 0 for item in value)
    ):
        return value[0], value[1]
    return None, None


def _bbox(value: Any) -> tuple[float, float, float, float] | None:
    coordinates = tuple(_value(value, name) for name in ("l", "t", "r", "b"))
    if len(coordinates) == 4 and all(isinstance(item, (int, float)) for item in coordinates):
        left, top, right, bottom = coordinates
        return float(left), float(top), float(right), float(bottom)
    return None


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 1 else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _enum_text(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw) if str(raw) else None


def _normalized_kind(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.casefold().replace("-", "_").replace(" ", "_")
    return {
        "picture": "figure",
        "caption": "caption",
        "table": "table",
    }.get(normalized, normalized)


def _value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _model_payload(value: Any) -> str | None:
    dump = getattr(value, "model_dump_json", None)
    if callable(dump):
        try:
            rendered = dump()
        except (TypeError, ValueError):
            rendered = None
        if isinstance(rendered, str):
            return rendered
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return None

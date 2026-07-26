"""Storage adapter for canonical bundle and reader-report artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .json_bundle import BUNDLE_SCHEMA, canonical_bundle_document
from .markdown_report import render_reader_markdown


class ArtifactWriter(Protocol):
    def put_json(
        self,
        value: Any,
        *,
        artifact_type: str,
        schema_version: str = "1",
    ) -> Any: ...

    def put_text(
        self,
        text: str,
        *,
        artifact_type: str,
        schema_version: str = "1",
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class ReadingProjectionArtifacts:
    bundle: Any
    report: Any


def write_projection_artifacts(
    bundle: Any,
    writer: ArtifactWriter,
) -> ReadingProjectionArtifacts:
    """Persist projections through the caller's content-addressed artifact writer."""

    bundle_ref = writer.put_json(
        canonical_bundle_document(bundle),
        artifact_type="reading_bundle",
        schema_version=BUNDLE_SCHEMA,
    )
    report_ref = writer.put_text(
        render_reader_markdown(bundle),
        artifact_type="reader_report_markdown",
        schema_version="readwelt.reader-report.v1",
    )
    return ReadingProjectionArtifacts(bundle=bundle_ref, report=report_ref)

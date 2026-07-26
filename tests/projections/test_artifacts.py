from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from readwelt.projections import BUNDLE_SCHEMA, write_projection_artifacts


@dataclass(frozen=True)
class Ref:
    artifact_type: str
    payload: Any


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, str, str]] = []

    def put_json(
        self,
        value: Any,
        *,
        artifact_type: str,
        schema_version: str = "1",
    ) -> Ref:
        self.calls.append(("json", value, artifact_type, schema_version))
        return Ref(artifact_type, value)

    def put_text(
        self,
        text: str,
        *,
        artifact_type: str,
        schema_version: str = "1",
    ) -> Ref:
        self.calls.append(("text", text, artifact_type, schema_version))
        return Ref(artifact_type, text)


def test_projection_writer_uses_artifact_references() -> None:
    writer = FakeWriter()
    bundle = {
        "run_id": "run-1",
        "snapshot_id": "snapshot-1",
        "claims": [],
        "ledger": {"lines": []},
    }

    projected = write_projection_artifacts(bundle, writer)

    assert projected.bundle.artifact_type == "reading_bundle"
    assert projected.report.artifact_type == "reader_report_markdown"
    assert writer.calls[0][3] == BUNDLE_SCHEMA
    assert writer.calls[1][0] == "text"
    assert "# 逆向阅读：snapshot-1" in writer.calls[1][1]

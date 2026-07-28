from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from readwelt.api import create_app
from readwelt.application import ReadweltApplicationService
from readwelt.cli.main import main
from readwelt.domain import ReadingStage
from readwelt.providers import StageRequest
from tests.interfaces.fakes import DeterministicFakeProvider


def _candidate(request: StageRequest) -> dict[str, Any]:
    stage = ReadingStage(request.stage)
    anchors = request.evidence_packet["anchors"]
    count = 2 if stage is ReadingStage.AUTHOR_MODEL else 1
    claims = [
        {
            "claim_id": f"{stage.value}:claim:{index}",
            "text": f"{stage.value} claim {index}",
            "anchor_ids": [anchors[0]["anchor_id"]],
            "decision": "accepted",
            **(
                {"provenance": {"interpretation_id": f"lens-{index}"}}
                if stage is ReadingStage.AUTHOR_MODEL
                else {}
            ),
        }
        for index in range(count)
    ]
    if stage not in (ReadingStage.MAINLINE, ReadingStage.STRUCTURE):
        for claim in claims:
            claim["source_claim_ids"] = [request.evidence_packet["upstream_claims"][0]["claim_id"]]
    return {"claims": claims, "gaps": [], "warnings": []}


def _service(tmp_path: Path) -> ReadweltApplicationService:
    return ReadweltApplicationService(
        tmp_path / ".readwelt",
        ingestion_backend="plain_text",
        candidate_providers=(DeterministicFakeProvider(_candidate),),
    )


def test_cli_uses_real_application_engine_and_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("正文证据。", encoding="utf-8")
    service = _service(tmp_path)
    output = io.StringIO()

    exit_code = main(
        ["read", str(source), "--provider", "local", "--json"],
        service=service,
        stdout=output,
    )

    result = json.loads(output.getvalue())
    assert exit_code == 0
    assert result["execution_status"] == "completed"
    assert {item["artifact_type"] for item in result["artifacts"]} >= {
        "reading_bundle",
        "reader_report_markdown",
        "stage_artifact",
    }
    manifest = json.loads(
        (service.root / "runs" / result["run_id"] / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["provider_invocations"]) == 6
    assert all(item["request"] and item["candidate"] for item in manifest["provider_invocations"])


def test_fastapi_real_chain_and_artifact_read(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("正文证据。", encoding="utf-8")
    service = _service(tmp_path)
    client = TestClient(create_app(service, project_root=service.root))

    imported = client.post("/v1/documents", json={"source": str(source)})
    assert imported.status_code == 200
    document_id = imported.json()["document_id"]
    prepared = client.post(f"/v1/documents/{document_id}/prepare", json={})
    assert prepared.status_code == 200
    started = client.post(
        "/v1/runs",
        json={
            "source_or_document_id": document_id,
            "provider": "local",
        },
    )
    assert started.status_code == 202
    run = started.json()
    assert client.get(f"/v1/runs/{run['run_id']}").status_code == 200
    report = next(
        item for item in run["artifacts"] if item["artifact_type"] == "reader_report_markdown"
    )
    artifact = client.get(f"/v1/artifacts/{report['content_digest']}")
    assert artifact.status_code == 200
    assert "Readwelt 六阶段逆向阅读报告" in artifact.json()["content"]

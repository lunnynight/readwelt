from __future__ import annotations

import pytest

from readwelt.api import create_app
from readwelt.application import ReadweltApplicationService

from .fakes import FakeService

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")


def test_health_and_run_status(tmp_path) -> None:
    client = testclient.TestClient(create_app(FakeService(tmp_path), project_root=tmp_path))

    health = client.get("/health")
    status = client.get("/v1/runs/run-1")

    assert health.status_code == 200
    assert health.json()["storage"] == "local"
    assert status.json()["run_id"] == "run-1"


def test_api_reports_provider_conflict(tmp_path) -> None:
    client = testclient.TestClient(create_app(FakeService(tmp_path), project_root=tmp_path))

    response = client.post(
        "/v1/runs",
        json={
            "source_or_document_id": "doc-1",
            "provider": "local",
            "provider_mode": "primary",
            "candidate_providers": ["api"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "provider_conflict"


def test_unimplemented_core_operation_is_explicit(tmp_path) -> None:
    class ReadOnlyService:
        pass

    client = testclient.TestClient(create_app(ReadOnlyService(), project_root=tmp_path))

    response = client.post("/v1/documents/doc-1/prepare", json={})

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "application_service_unavailable"


def test_http_agent_session_completes_without_internal_provider(tmp_path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("第一段提出主张。\n\n第二段说明限制。", encoding="utf-8")
    project = tmp_path / ".readwelt"
    service = ReadweltApplicationService(
        project,
        ingestion_backend="plain_text",
        candidate_providers=(),
    )
    client = testclient.TestClient(create_app(service, project_root=project))

    response = client.post(
        "/v1/agent-sessions",
        json={
            "source_or_document_id": str(source),
            "idempotency_key": "http-agent-session",
        },
    )
    assert response.status_code == 202
    turn = response.json()

    for expected_stage in (
        "stage_1_mainline",
        "stage_2_structure",
        "stage_3_decompression",
        "stage_4_author_model",
        "stage_5_boundaries",
        "stage_6_transfer",
    ):
        assert turn["stage"] == expected_stage
        request = turn["request"]
        anchors = request["evidence_packet"]["anchors"]
        upstream = request["evidence_packet"]["upstream_claims"]
        claims = []
        for index in range(2 if expected_stage == "stage_4_author_model" else 1):
            claim = {
                "claim_id": f"{expected_stage}:http:{index}",
                "text": f"{expected_stage} claim {index}",
                "anchor_ids": [anchors[0]["anchor_id"]],
                "decision": "accepted",
            }
            if expected_stage not in ("stage_1_mainline", "stage_2_structure"):
                claim["source_claim_ids"] = [upstream[0]["claim_id"]]
            if expected_stage == "stage_4_author_model":
                claim["provenance"] = {"interpretation_id": f"http-lens-{index}"}
            claims.append(claim)
        response = client.post(
            f"/v1/agent-sessions/{turn['run_id']}/turns",
            json={
                "candidate": {"claims": claims, "gaps": [], "warnings": []},
                "agent_name": "generic-http-agent",
                "model": "external-test-model",
            },
        )
        assert response.status_code == 200
        turn = response.json()

    assert turn["action"] == "completed"

from __future__ import annotations

import pytest

from readwelt.api import create_app

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

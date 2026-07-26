from __future__ import annotations

import pytest

from readwelt.api import create_app

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")


# Regression: ISSUE-002 — Swagger exposed Agent payloads as arbitrary objects
# and successful responses as strings, hiding the host-neutral contract.
# Found by /qa on 2026-07-27
# Report: .gstack/qa-reports/qa-report-127-0-0-1-2026-07-27.md
def test_openapi_exposes_agent_request_fields_and_object_response(tmp_path) -> None:
    client = testclient.TestClient(create_app(object(), project_root=tmp_path))

    document = client.get("/openapi.json").json()
    operation = document["paths"]["/v1/agent-sessions"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"][
        "schema"
    ]
    agent_schema = document["components"]["schemas"]["StartAgentSessionPayload"]
    response_schema = operation["responses"]["202"]["content"]["application/json"][
        "schema"
    ]

    assert request_schema == {
        "$ref": "#/components/schemas/StartAgentSessionPayload"
    }
    assert agent_schema["required"] == ["source_or_document_id"]
    assert set(agent_schema["properties"]) == {
        "source_or_document_id",
        "purpose",
        "token_budget",
        "idempotency_key",
    }
    assert response_schema["type"] == "object"

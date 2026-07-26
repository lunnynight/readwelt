from __future__ import annotations

import pytest

from readwelt.api import create_app

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")


class MissingRunService:
    def get_run_status(self, run_id: str) -> object:
        raise FileNotFoundError(run_id)


# Regression: ISSUE-001 — missing runs escaped the API as HTTP 500 responses
# Found by /qa on 2026-07-27
# Report: .gstack/qa-reports/qa-report-127-0-0-1-2026-07-27.md
@pytest.mark.parametrize(
    "path",
    (
        "/v1/runs/not-found",
        "/v1/agent-sessions/not-found",
    ),
)
def test_missing_run_routes_return_structured_404(tmp_path, path: str) -> None:
    client = testclient.TestClient(
        create_app(MissingRunService(), project_root=tmp_path)
    )

    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "not_found",
            "message": "run not found: not-found",
        }
    }

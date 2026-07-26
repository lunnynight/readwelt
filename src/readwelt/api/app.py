"""Optional FastAPI shell over the shared Readwelt application service."""

# mypy: disable-error-code="import-not-found,untyped-decorator"

from pathlib import Path
from typing import Any

from readwelt.providers.contracts import (
    ProviderContractError,
    ProviderSelection,
)
from readwelt.providers.external_agent import ExternalAgentAdapter
from readwelt.providers.projection import (
    ensure_within_project,
    resolve_project_root,
    to_jsonable,
)
from readwelt.providers.service_port import (
    ApplicationServiceUnavailable,
    invoke,
    invoke_read,
    load_application_service,
)


class FastAPIUnavailable(RuntimeError):
    code = "optional_dependency_missing"


def create_app(
    service: object | None = None,
    *,
    project_root: str | Path = ".readwelt",
) -> Any:
    """Create an ASGI app without making FastAPI a core dependency."""

    try:
        from fastapi import FastAPI, HTTPException, status
    except (ImportError, ModuleNotFoundError) as exc:
        raise FastAPIUnavailable(
            "FastAPI support requires the optional 'fastapi' dependency"
        ) from exc

    root = resolve_project_root(project_root)
    active_service = service or load_application_service(root)
    agent = ExternalAgentAdapter(active_service)
    app = FastAPI(title="Readwelt API", version="1")
    app.state.project_root = root
    app.state.readwelt_service = active_service

    @app.exception_handler(ApplicationServiceUnavailable)
    async def application_service_unavailable(_request: Any, exc: Exception) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content={
                "error": {
                    "code": "application_service_unavailable",
                    "message": str(exc),
                }
            },
        )

    def request_error(exc: Exception) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT
            if getattr(exc, "code", "") == "provider_conflict"
            else status.HTTP_400_BAD_REQUEST,
            detail={
                "code": getattr(exc, "code", "invalid_request"),
                "message": str(exc),
            },
        )

    def not_found_error(resource: str, identifier: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"{resource} not found: {identifier}",
            },
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "project_root": str(root),
            "storage": "local",
        }

    @app.post("/v1/documents")
    async def import_document(payload: dict[str, Any]) -> Any:
        source = str(payload.get("source", "")).strip()
        if not source:
            raise request_error(ValueError("source is required"))
        candidate = Path(source)
        if candidate.exists():
            try:
                ensure_within_project(root.parent, candidate)
            except ValueError as exc:
                raise request_error(exc) from exc
        return to_jsonable(await invoke(active_service, "import_document", source))

    @app.post("/v1/documents/{document_id}/prepare")
    async def prepare_document(document_id: str, payload: dict[str, Any] | None = None) -> Any:
        options = (payload or {}).get("options", {})
        if not isinstance(options, dict):
            raise request_error(ValueError("options must be an object"))
        return to_jsonable(await invoke(active_service, "prepare", document_id, **options))

    @app.post("/v1/batches/prepare", status_code=status.HTTP_202_ACCEPTED)
    async def batch_prepare(payload: dict[str, Any]) -> Any:
        raw_sources = payload.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise request_error(ValueError("sources must be a non-empty array"))
        sources = [str(source) for source in raw_sources]
        for source in sources:
            candidate = Path(source)
            if candidate.exists():
                try:
                    ensure_within_project(root.parent, candidate)
                except ValueError as exc:
                    raise request_error(exc) from exc
        concurrency = int(payload.get("concurrency", 8))
        return to_jsonable(
            await invoke(
                active_service,
                "batch_prepare",
                sources,
                concurrency=concurrency,
            )
        )

    @app.post("/v1/runs", status_code=status.HTTP_202_ACCEPTED)
    async def start_run(payload: dict[str, Any]) -> Any:
        source = str(payload.get("source_or_document_id", "")).strip()
        if not source:
            raise request_error(ValueError("source_or_document_id is required"))
        candidate = Path(source)
        if candidate.exists():
            try:
                ensure_within_project(root.parent, candidate)
            except ValueError as exc:
                raise request_error(exc) from exc
        try:
            selection = ProviderSelection.build(
                mode=str(payload.get("provider_mode", "primary")),
                primary=payload.get("provider"),
                candidates=payload.get("candidate_providers", []),
            )
        except ProviderContractError as exc:
            raise request_error(exc) from exc
        try:
            result = await invoke_read(active_service, source, selection)
        except ProviderContractError as exc:
            raise request_error(exc) from exc
        return to_jsonable(result)

    @app.post("/v1/agent-sessions", status_code=status.HTTP_202_ACCEPTED)
    async def start_agent_session(payload: dict[str, Any]) -> Any:
        source = str(payload.get("source_or_document_id", "")).strip()
        if not source:
            raise request_error(ValueError("source_or_document_id is required"))
        candidate = Path(source)
        if candidate.exists():
            try:
                ensure_within_project(root.parent, candidate)
            except ValueError as exc:
                raise request_error(exc) from exc
        try:
            return await agent.start(
                source,
                purpose=str(payload.get("purpose", "完整逆向阅读")),
                token_budget=(
                    int(payload["token_budget"])
                    if payload.get("token_budget") is not None
                    else None
                ),
                idempotency_key=(
                    str(payload["idempotency_key"])
                    if payload.get("idempotency_key") is not None
                    else None
                ),
            )
        except ProviderContractError as exc:
            raise request_error(exc) from exc

    @app.get("/v1/agent-sessions/{run_id}")
    async def get_agent_session(run_id: str) -> Any:
        try:
            return await agent.current(run_id)
        except FileNotFoundError as exc:
            raise not_found_error("run", run_id) from exc
        except ProviderContractError as exc:
            raise request_error(exc) from exc

    @app.post("/v1/agent-sessions/{run_id}/turns")
    async def submit_agent_turn(run_id: str, payload: dict[str, Any]) -> Any:
        candidate = payload.get("candidate")
        if not isinstance(candidate, dict):
            raise request_error(ValueError("candidate must be an object"))
        try:
            return await agent.advance(
                run_id,
                candidate,
                agent_name=str(payload.get("agent_name", "")),
                model=(
                    str(payload["model"]) if payload.get("model") is not None else None
                ),
                agent_provenance=(
                    payload["agent_provenance"]
                    if isinstance(payload.get("agent_provenance"), dict)
                    else None
                ),
            )
        except ProviderContractError as exc:
            raise request_error(exc) from exc

    @app.get("/v1/runs/{run_id}")
    async def get_run_status(run_id: str) -> Any:
        try:
            return to_jsonable(await invoke(active_service, "get_run_status", run_id))
        except FileNotFoundError as exc:
            raise not_found_error("run", run_id) from exc

    @app.get("/v1/artifacts/{digest}")
    async def get_artifact(digest: str) -> Any:
        try:
            return to_jsonable(await invoke(active_service, "get_artifact", digest))
        except (FileNotFoundError, ValueError) as exc:
            raise request_error(exc) from exc

    @app.get("/v1/runs/{run_id}/stage-request/{stage_name}")
    async def pull_stage_request(run_id: str, stage_name: str) -> Any:
        try:
            return await agent.pull(run_id, stage_name)
        except ProviderContractError as exc:
            raise request_error(exc) from exc

    @app.post("/v1/runs/{run_id}/stage-candidate/{stage_name}")
    async def submit_stage_candidate(run_id: str, stage_name: str, payload: dict[str, Any]) -> Any:
        try:
            return await agent.submit(run_id, stage_name, payload)
        except ProviderContractError as exc:
            raise request_error(exc) from exc

    return app


def run() -> None:
    """Run the local API on loopback with the default relative project."""

    try:
        import uvicorn
    except (ImportError, ModuleNotFoundError) as exc:
        raise FastAPIUnavailable("API serving requires the optional 'api' dependencies") from exc
    uvicorn.run(
        create_app(project_root=".readwelt"),
        host="127.0.0.1",
        port=8000,
    )

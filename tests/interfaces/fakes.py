from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from readwelt.providers import ProviderKind, StageCandidate, StageRequest
from readwelt.providers.model_protocol import JsonSchema
from readwelt.providers.openai_compatible import validate_json_schema

CandidateFactory = Callable[[StageRequest], Mapping[str, Any]]


class DeterministicFakeProvider:
    """Deterministic provider used only by tests."""

    def __init__(
        self,
        candidate: Mapping[str, Any] | CandidateFactory,
        *,
        kind: ProviderKind = ProviderKind.LOCAL,
        name: str = "deterministic-fake",
        model: str = "fake-v1",
    ) -> None:
        self._candidate = candidate
        self._kind = kind
        self._name = name
        self._model = model

    @property
    def kind(self) -> ProviderKind:
        return self._kind

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate:
        started = time.perf_counter()
        value = self._candidate(request) if callable(self._candidate) else self._candidate
        candidate = dict(value)
        validate_json_schema(candidate, response_schema)
        return StageCandidate(
            schema_version=request.schema_version,
            run_id=request.run_id,
            stage=request.stage,
            candidate=candidate,
            provider=self.name,
            model=self.model,
            provenance={
                **dict(request.provenance),
                "provider_kind": self.kind.value,
                "provider": self.name,
                "model": self.model,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "token_usage": {},
            },
        )


class FakeService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def import_document(self, source: str, **options: Any) -> dict[str, Any]:
        self.calls.append(("import_document", (source,), options))
        return {"document_id": "doc-1", "status": "imported"}

    async def prepare(self, document_id: str, **options: Any) -> dict[str, Any]:
        self.calls.append(("prepare", (document_id,), options))
        return {"document_id": document_id, "status": "prepared"}

    def read(self, source: str, **options: Any) -> dict[str, Any]:
        self.calls.append(("read", (source,), options))
        return {"run_id": "run-1", "status": "queued"}

    def get_run_status(self, run_id: str) -> dict[str, Any]:
        self.calls.append(("get_run_status", (run_id,), {}))
        return {"run_id": run_id, "status": "awaiting_agent", "stage": "stage-3"}

    def pull_stage_request(self, run_id: str, stage: str) -> dict[str, Any]:
        self.calls.append(("pull_stage_request", (run_id, stage), {}))
        return {
            "schema_version": "1",
            "run_id": run_id,
            "stage": stage,
            "evidence_packet": {"anchors": ["a-1"]},
            "capabilities": ["structured_output"],
        }

    def submit_stage_candidate(
        self, run_id: str, stage: str, candidate: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(("submit_stage_candidate", (run_id, stage, candidate), {}))
        return {"run_id": run_id, "stage": stage, "accepted": True}

    def get_artifact(self, digest: str) -> dict[str, Any]:
        self.calls.append(("get_artifact", (digest,), {}))
        return {
            "digest": digest,
            "path": str(self.project_root / "objects" / digest),
            "content": "small",
        }

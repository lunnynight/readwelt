"""Project facade shared by CLI, API, and SDK adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from readwelt.article_graph import (
    ArticleGraphBuilder,
    ArticleGraphBuildResult,
)
from readwelt.batch import BatchResult, LocalBatchPipeline
from readwelt.domain import (
    ExecutionStatus,
    ReadingRun,
    ReadingStage,
    SourceDocumentSnapshot,
)
from readwelt.extraction import (
    DeterministicSemanticExtractionBackend,
    configured_argument_semantic_backend,
)
from readwelt.providers import (
    CandidateProvider,
    ExternalAgentMailboxProvider,
    ProviderKind,
    ProviderResolver,
    ProviderSelection,
    ProviderUnavailableError,
    StageCandidate,
    StageRequest,
    configured_model_providers,
)
from readwelt.runner import DocumentRunner
from readwelt.semantic import (
    DenseEncoder,
    HybridRetriever,
    SemanticAtlas,
    SemanticPreprocessor,
    configured_dense_encoder,
)
from readwelt.stage_views import StageViewProjector
from readwelt.storage import ArtifactStore, EventLog, ManifestStore, ProjectLayout

from .project_artifacts import get_artifact as _get_artifact
from .project_artifacts import prepare_document as _prepare_document
from .project_artifacts import prepare_snapshot as _prepare_snapshot_impl
from .project_artifacts import validate_run_artifacts as _validate_run_artifacts_impl
from .project_selection import default_selection as _default_selection_impl
from .project_selection import new_run_id as _new_run_id_impl
from .project_selection import normalize_selection as _normalize_selection_impl
from .read_execution import execute_read as _execute_read_impl
from .run_lifecycle import emit_run_event as _emit_run_event
from .run_lifecycle import write_application_run as _write_run
from .run_store import ApplicationRunStore

_PIPELINE_POLICY = "readwelt-six-stage-v1"
_DEFAULT_PURPOSE = "完整逆向阅读"


def _run_sync[T](operation: Coroutine[object, object, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(operation)
    operation.close()
    raise RuntimeError("a running event loop was detected; use the corresponding async method")


class ReadweltApplicationService:
    def __init__(
        self,
        project: str | Path = ".readwelt",
        *,
        base_directory: Path | None = None,
        ingestion_backend: str = "xberg",
        candidate_providers: Sequence[CandidateProvider] | None = None,
        provider_resolver: ProviderResolver | None = None,
        semantic_preprocessor: SemanticPreprocessor | None = None,
        dense_encoder: DenseEncoder | None = None,
    ) -> None:
        self._layout = ProjectLayout.resolve(project, base_directory=base_directory)
        self._layout.initialize()
        if ingestion_backend == "xberg":
            self._runner = DocumentRunner(self._layout)
        elif ingestion_backend == "plain_text":
            self._runner = DocumentRunner.with_plain_text_fallback(self._layout)
        else:
            raise ValueError(f"unsupported ingestion backend: {ingestion_backend}")
        self._artifacts = ArtifactStore(self._layout)
        self._run_store = ApplicationRunStore(self._layout, self._artifacts)
        self._manifests = ManifestStore()
        self._events = EventLog()
        self._semantic = semantic_preprocessor or SemanticPreprocessor()
        configured_argument_backend = configured_argument_semantic_backend()
        self._article_graph = ArticleGraphBuilder(
            semantic_backends=(
                None
                if configured_argument_backend is None
                else (
                    configured_argument_backend,
                    DeterministicSemanticExtractionBackend(),
                )
            )
        )
        self._stage_views = StageViewProjector()
        self._retriever = HybridRetriever(
            dense_encoder=(
                dense_encoder
                if dense_encoder is not None
                else configured_dense_encoder(self._layout.root)
            ),
            cache_dir=self._layout.root / "cache" / "embeddings",
        )
        self._mailbox = ExternalAgentMailboxProvider(self._layout)
        self._configured_providers = (
            configured_model_providers()
            if candidate_providers is None
            else tuple(candidate_providers)
        )
        resolver_providers = (
            *self._configured_providers,
            *(
                ()
                if any(
                    provider.kind is ProviderKind.AGENT for provider in self._configured_providers
                )
                else (self._mailbox,)
            ),
        )
        self._resolver = provider_resolver or ProviderResolver(resolver_providers)

    @classmethod
    def open(cls, project_root: str | Path) -> ReadweltApplicationService:
        return cls(project_root)

    @property
    def root(self) -> Path:
        return self._layout.root

    async def import_document_async(self, source: str | Path) -> SourceDocumentSnapshot:
        return await self._runner.ingest(Path(source))

    def import_document(self, source: str | Path) -> SourceDocumentSnapshot:
        return _run_sync(self.import_document_async(source))

    async def batch_prepare_async(
        self,
        sources: Sequence[str | Path],
        *,
        concurrency: int = 8,
    ) -> BatchResult:
        pipeline = LocalBatchPipeline(
            self,
            self._layout,
            concurrency=concurrency,
        )
        return await pipeline.run(sources, prepare=True)

    def batch_prepare(
        self,
        sources: Sequence[str | Path],
        *,
        concurrency: int = 8,
    ) -> BatchResult:
        return _run_sync(self.batch_prepare_async(sources, concurrency=concurrency))

    def prepare(
        self,
        document_id: str,
        *,
        purpose: str = _DEFAULT_PURPOSE,
        token_budget: int | None = None,
    ) -> SemanticAtlas:
        del purpose, token_budget
        return _prepare_document(self, document_id)

    async def prepare_async(
        self,
        document_id: str,
        *,
        purpose: str = _DEFAULT_PURPOSE,
        token_budget: int | None = None,
    ) -> SemanticAtlas:
        return await asyncio.to_thread(
            self.prepare,
            document_id,
            purpose=purpose,
            token_budget=token_budget,
        )

    async def read_async(
        self,
        source: str | Path,
        *,
        provider_selection: ProviderSelection | Mapping[str, Any] | None = None,
        purpose: str = _DEFAULT_PURPOSE,
        token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> ReadingRun:
        selection = self._normalize_selection(provider_selection)
        snapshot = await self._resolve_snapshot(source)
        run_id = self._new_run_id(
            snapshot,
            selection,
            idempotency_key=idempotency_key or uuid4().hex,
        )
        if self._layout.run_manifest(run_id).exists():
            return await self.resume_async(run_id)
        return await self._execute_read(
            snapshot,
            selection,
            run_id=run_id,
            purpose=purpose,
            token_budget=token_budget,
            hard_serialized_token_budget=token_budget,
            created_at=datetime.now(UTC),
        )

    def read(
        self,
        source: str | Path,
        *,
        provider_selection: ProviderSelection | Mapping[str, Any] | None = None,
        purpose: str = _DEFAULT_PURPOSE,
        token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> ReadingRun:
        return _run_sync(
            self.read_async(
                source,
                provider_selection=provider_selection,
                purpose=purpose,
                token_budget=token_budget,
                idempotency_key=idempotency_key,
            )
        )

    def run_document(self, source: str | Path) -> ReadingRun:
        """Deprecated alias for the real reading pipeline."""
        return self.read(source)

    def resume(self, run_id: str) -> ReadingRun:
        return _run_sync(self.resume_async(run_id))

    def resume_stage_page(
        self,
        run_id: str,
        stage: str | ReadingStage,
        *,
        targeted_anchor_ids: tuple[str, ...] = (),
        rescue_level: str = "section",
    ) -> ReadingRun:
        parsed_stage = ReadingStage(stage)
        self._run_store.configure_stage_navigation(
            run_id,
            parsed_stage,
            targeted_anchor_ids=targeted_anchor_ids,
            rescue_level=rescue_level,
        )
        return self.resume(run_id)

    async def resume_async(self, run_id: str) -> ReadingRun:
        manifest = self._manifests.read(self._layout.run_manifest(run_id))
        if manifest.get("pipeline_policy") != _PIPELINE_POLICY:
            raise ProviderUnavailableError(
                "run uses an unsupported pipeline policy and cannot be resumed"
            )
        run = self._runner.get(run_id)
        self._run_store.load_stage_artifacts(run_id)
        if run.execution_status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            self._validate_run_artifacts(run)
            return run
        selection_value = manifest.get("provider_selection")
        if not isinstance(selection_value, Mapping):
            raise ValueError(f"run has no provider selection: {run_id}")
        selection = self._normalize_selection(selection_value)
        snapshot = self._runner.get_snapshot_by_id(run.snapshot_id)
        return await self._execute_read(
            snapshot,
            selection,
            run_id=run_id,
            purpose=str(manifest.get("purpose", _DEFAULT_PURPOSE)),
            token_budget=(
                int(manifest["token_budget"]) if manifest.get("token_budget") is not None else None
            ),
            hard_serialized_token_budget=(
                int(manifest["hard_serialized_token_budget"])
                if manifest.get("hard_serialized_token_budget") is not None
                else None
            ),
            created_at=run.created_at,
        )

    def get_run(self, run_id: str) -> ReadingRun:
        return self._runner.get(run_id)

    def get_run_status(self, run_id: str) -> ReadingRun:
        return self.get_run(run_id)

    def get_artifact(self, digest: str) -> dict[str, Any]:
        return _get_artifact(self, digest)

    def pull_stage_request(self, run_id: str, stage: str) -> StageRequest:
        return self._mailbox.pull(run_id, stage)

    def submit_stage_candidate(
        self,
        run_id: str,
        stage: str,
        candidate: StageCandidate | Mapping[str, Any],
    ) -> ReadingRun:
        parsed = (
            candidate
            if isinstance(candidate, StageCandidate)
            else StageCandidate.from_mapping(candidate)
        )
        if parsed.run_id != run_id or parsed.stage != stage:
            raise ValueError("candidate run_id and stage must match submission target")
        self._mailbox.submit(parsed)
        manifest = self._manifests.read(self._layout.run_manifest(run_id))
        selection_value = manifest.get("provider_selection")
        if not isinstance(selection_value, Mapping):
            raise ValueError(f"run has no provider selection: {run_id}")
        selection = self._normalize_selection(selection_value)
        snapshot = self._runner.get_snapshot_by_id(str(manifest["snapshot_id"]))
        return _run_sync(
            self._execute_read(
                snapshot,
                selection,
                run_id=run_id,
                purpose=str(manifest.get("purpose", _DEFAULT_PURPOSE)),
                token_budget=(
                    int(manifest["token_budget"])
                    if manifest.get("token_budget") is not None
                    else None
                ),
                hard_serialized_token_budget=(
                    int(manifest["hard_serialized_token_budget"])
                    if manifest.get("hard_serialized_token_budget") is not None
                    else None
                ),
                created_at=datetime.fromisoformat(str(manifest["created_at"])),
            )
        )

    async def _resolve_snapshot(self, source: str | Path) -> SourceDocumentSnapshot:
        candidate = Path(source)
        if candidate.exists():
            return await self.import_document_async(candidate)
        return self._runner.get_snapshot(str(source))

    def _prepare_snapshot(
        self,
        snapshot: SourceDocumentSnapshot,
    ) -> tuple[SemanticAtlas, Any, ArticleGraphBuildResult, tuple[Any, ...]]:
        return _prepare_snapshot_impl(self, snapshot)

    async def _execute_read(
        self,
        snapshot: SourceDocumentSnapshot,
        selection: ProviderSelection,
        *,
        run_id: str,
        purpose: str,
        token_budget: int | None,
        hard_serialized_token_budget: int | None,
        created_at: datetime,
    ) -> ReadingRun:
        return await _execute_read_impl(
            self,
            snapshot,
            selection,
            run_id=run_id,
            purpose=purpose,
            token_budget=token_budget,
            hard_serialized_token_budget=hard_serialized_token_budget,
            created_at=created_at,
        )

    def _normalize_selection(
        self,
        value: ProviderSelection | Mapping[str, Any] | None,
    ) -> ProviderSelection:
        return _normalize_selection_impl(self, value)

    def _default_selection(self) -> ProviderSelection:
        return _default_selection_impl(self)

    @staticmethod
    def _new_run_id(
        snapshot: SourceDocumentSnapshot,
        selection: ProviderSelection,
        *,
        idempotency_key: str,
    ) -> str:
        return _new_run_id_impl(
            snapshot,
            selection,
            pipeline_policy=_PIPELINE_POLICY,
            idempotency_key=idempotency_key,
        )

    def _write_application_run(
        self,
        run: ReadingRun,
        *,
        selection: ProviderSelection,
        purpose: str,
        token_budget: int,
        hard_serialized_token_budget: int | None,
    ) -> None:
        _write_run(
            self._run_store,
            run,
            pipeline_policy=_PIPELINE_POLICY,
            selection=selection,
            purpose=purpose,
            token_budget=token_budget,
            hard_serialized_token_budget=hard_serialized_token_budget,
        )

    def _emit(self, run_id: str, event_type: str, task: str) -> None:
        _emit_run_event(self._events, self._layout, run_id, event_type, task)

    def _validate_run_artifacts(self, run: ReadingRun) -> None:
        _validate_run_artifacts_impl(self, run)


ReadweltProject = ReadweltApplicationService

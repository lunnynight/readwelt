"""Project facade shared by CLI, API and MCP adapters."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from readwelt.article_graph import ArticleGraphBuilder, ArticleGraphBuildResult
from readwelt.batch import BatchResult, LocalBatchPipeline
from readwelt.domain import (
    EpistemicStatus,
    EvidencePacket,
    ExecutionStatus,
    ModelStatus,
    PublicationStatus,
    ReadingRun,
    ReadingStage,
    SourceDocumentSnapshot,
    StageArtifact,
    stable_id,
)
from readwelt.projections import write_projection_artifacts
from readwelt.providers import (
    AgentInputRequired,
    CandidateProvider,
    ExternalAgentMailboxProvider,
    ProviderConflictError,
    ProviderKind,
    ProviderMode,
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
    SemanticEvidencePacket,
    SemanticPreprocessor,
    build_stage_retrieval_plan,
    configured_dense_encoder,
)
from readwelt.stage_views import StageContext, StageView, StageViewProjector
from readwelt.stages import AgentCandidateRejected, SixStageReadingEngine
from readwelt.storage import ArtifactStore, EventLog, ManifestStore, ProjectLayout

from .provider_runtime import AuditedCandidateProvider, ResolvingCandidateProvider
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
        self._article_graph = ArticleGraphBuilder()
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
        snapshot = self._runner.get_snapshot(document_id)
        atlas, atlas_ref, graph_build, graph_refs = self._prepare_snapshot(snapshot)
        manifest_path = self._layout.document_manifest(snapshot.document_id)
        manifest = self._manifests.read(manifest_path)
        manifest["semantic_atlas"] = atlas
        manifest["semantic_atlas_artifact"] = atlas_ref
        manifest["article_graph"] = graph_build.graph
        manifest["article_graph_artifact"] = next(
            item for item in graph_refs if item.artifact_type == "article_graph"
        )
        manifest["article_graph_build_artifacts"] = graph_refs
        self._manifests.write(manifest_path, manifest)
        return atlas

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
            created_at=run.created_at,
        )

    def get_run(self, run_id: str) -> ReadingRun:
        return self._runner.get(run_id)

    def get_run_status(self, run_id: str) -> ReadingRun:
        return self.get_run(run_id)

    def get_artifact(self, digest: str) -> dict[str, Any]:
        hexadecimal = digest.removeprefix("sha256:")
        if len(hexadecimal) != 64 or any(
            char not in "0123456789abcdefABCDEF" for char in hexadecimal
        ):
            raise ValueError("artifact digest must be a sha256 hex digest")
        hexadecimal = hexadecimal.lower()
        path = (
            self._layout.root
            / "objects"
            / "sha256"
            / hexadecimal[:2]
            / hexadecimal[2:4]
            / hexadecimal
        ).resolve()
        path.relative_to(self._layout.root)
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != hexadecimal:
            raise ValueError(f"artifact digest mismatch: sha256:{hexadecimal}")
        result: dict[str, Any] = {
            "digest": f"sha256:{hexadecimal}",
            "path": self._layout.relative(path),
            "size": len(content),
        }
        try:
            result["content"] = content.decode("utf-8")
            result["content_encoding"] = "utf-8"
        except UnicodeDecodeError:
            result["content"] = base64.b64encode(content).decode("ascii")
            result["content_encoding"] = "base64"
        return result

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
        normalized_path = (self._layout.root / snapshot.normalized_text_ref).resolve()
        normalized_path.relative_to(self._layout.root)
        normalized_text = normalized_path.read_text(encoding="utf-8")
        digest = f"sha256:{hashlib.sha256(normalized_text.encode()).hexdigest()}"
        if digest != snapshot.content_digest:
            raise ValueError(f"normalized text digest mismatch: {snapshot.snapshot_id}")
        atlas = self._semantic.prepare(snapshot, normalized_text)
        atlas_ref = self._artifacts.put_json(
            atlas,
            artifact_type="semantic_atlas",
            schema_version=atlas.schema_version,
        )
        graph_build = self._article_graph.build(snapshot, normalized_text)
        graph_refs = (
            self._artifacts.put_json(
                graph_build.unitization,
                artifact_type="anchored_text_unitization",
                schema_version=graph_build.unitization.schema_version,
            ),
            *(
                self._artifacts.put_json(
                    extraction,
                    artifact_type="graph_extraction",
                    schema_version=extraction.schema_version,
                )
                for extraction in graph_build.extractions
            ),
            self._artifacts.put_json(
                graph_build.merge_report,
                artifact_type="article_graph_merge_report",
                schema_version=graph_build.merge_report.schema_version,
            ),
            self._artifacts.put_json(
                graph_build.provenance_ledger,
                artifact_type="article_graph_provenance_ledger",
                schema_version=graph_build.provenance_ledger.schema_version,
            ),
            self._artifacts.put_json(
                graph_build.source_index,
                artifact_type="article_graph_source_index",
                schema_version=graph_build.source_index.schema_version,
            ),
            self._artifacts.put_json(
                graph_build.graph,
                artifact_type="article_graph",
                schema_version=graph_build.graph.schema_version,
            ),
            self._artifacts.put_json(
                graph_build,
                artifact_type="article_graph_build",
                schema_version=graph_build.schema_version,
            ),
        )
        return atlas, atlas_ref, graph_build, graph_refs

    async def _execute_read(
        self,
        snapshot: SourceDocumentSnapshot,
        selection: ProviderSelection,
        *,
        run_id: str,
        purpose: str,
        token_budget: int | None,
        created_at: datetime,
    ) -> ReadingRun:
        atlas, atlas_ref, graph_build, graph_refs = self._prepare_snapshot(snapshot)
        effective_budget = (
            token_budget
            if token_budget is not None
            else sum(segment.statistics.token_count for segment in atlas.segments)
        )
        base_plan = build_stage_retrieval_plan(
            ReadingStage.MAINLINE,
            purpose=purpose,
            token_budget=effective_budget,
        )
        semantic_packet = self._retriever.retrieve(atlas, base_plan)
        stage_packets: dict[ReadingStage, SemanticEvidencePacket] = {
            ReadingStage.MAINLINE: semantic_packet,
        }
        stage_view_refs: dict[ReadingStage, Any] = {}
        evidence = cast(EvidencePacket, semantic_packet.to_stage_packet(run_id))
        initial_artifacts = self._run_store.load_stage_artifacts(run_id)
        if selection.mode is ProviderMode.AGENT_TAKEOVER:
            selected_provider: CandidateProvider = self._mailbox
        else:
            selected_provider = ResolvingCandidateProvider(self._resolver, selection)
        provider: CandidateProvider = AuditedCandidateProvider(
            selected_provider,
            self._run_store,
        )
        engine = SixStageReadingEngine(
            provider,
            retry_invalid_candidates=selection.mode is ProviderMode.AGENT_TAKEOVER,
        )

        def evidence_for_stage(
            stage: ReadingStage,
            artifacts: Sequence[StageArtifact],
        ) -> EvidencePacket:
            if stage is ReadingStage.MAINLINE and not artifacts:
                return evidence
            if stage is ReadingStage.TRANSFER and artifacts:
                upstream_claims = artifacts[-1].accepted_claims
            else:
                upstream_claims = tuple(
                    claim for artifact in artifacts for claim in artifact.accepted_claims
                )
            plan = build_stage_retrieval_plan(
                stage,
                purpose=purpose,
                token_budget=effective_budget,
                upstream_claims=upstream_claims,
            )
            packet = self._retriever.retrieve(atlas, plan)
            stage_packets[stage] = packet
            return cast(EvidencePacket, packet.to_stage_packet(run_id))

        def stage_view_for_stage(
            stage: ReadingStage,
            artifacts: Sequence[StageArtifact],
        ) -> StageView:
            upstream_claims = (
                artifacts[-1].accepted_claims
                if stage is ReadingStage.TRANSFER and artifacts
                else tuple(
                    claim for artifact in artifacts for claim in artifact.accepted_claims
                )
            )
            view = self._stage_views.project(
                graph_build,
                StageContext(
                    stage=stage,
                    task_intent=purpose,
                    token_budget=effective_budget,
                    upstream_claim_ids=tuple(claim.claim_id for claim in upstream_claims),
                    unresolved_gap_ids=tuple(
                        gap.gap_id
                        for artifact in artifacts
                        for gap in artifact.gaps
                        if not gap.resolved
                    ),
                ),
                upstream_claims=upstream_claims,
                locator_packet=stage_packets.get(stage),
            )
            stage_view_refs[stage] = self._artifacts.put_json(
                view,
                artifact_type="stage_view",
                schema_version=view.schema_version,
            )
            return view

        source_ref = self._artifacts.put_json(snapshot, artifact_type="source_snapshot")
        manifest_path = self._layout.run_manifest(run_id)
        if manifest_path.exists():
            prior = self._runner.get(run_id)
            running = replace(
                prior,
                execution_status=ExecutionStatus.RUNNING,
                current_task="six_stage_reading",
                completed_at=None,
            )
        else:
            running = ReadingRun(
                run_id=run_id,
                schema_version="1",
                snapshot_id=snapshot.snapshot_id,
                execution_status=ExecutionStatus.RUNNING,
                epistemic_status=EpistemicStatus.UNDERDETERMINED,
                model_status=ModelStatus.READY,
                publication_status=PublicationStatus.WITHHELD,
                current_task="six_stage_reading",
                artifacts=(source_ref, atlas_ref, *graph_refs),
                warnings=(),
                created_at=created_at,
            )
        self._write_application_run(
            running,
            selection=selection,
            purpose=purpose,
            token_budget=effective_budget,
        )
        self._emit(run_id, "run_started", "six_stage_reading")

        async def persist_stage(artifact: StageArtifact) -> None:
            reference = self._run_store.append_stage_artifact(run_id, artifact)
            self._emit(run_id, "stage_settled", artifact.stage.value)
            if reference.status.value != "completed":
                raise ValueError("settled stage artifact was not completed")

        try:
            bundle = await engine.run(
                snapshot,
                evidence,
                initial_artifacts=initial_artifacts,
                artifact_sink=persist_stage,
                evidence_factory=evidence_for_stage,
                stage_view_factory=stage_view_for_stage,
            )
        except AgentCandidateRejected as exc:
            self._mailbox.reject(run_id, exc.stage, exc.reason)
            persisted = self._runner.get(run_id)
            awaiting_retry = replace(
                persisted,
                artifacts=tuple(
                    dict.fromkeys((*persisted.artifacts, *stage_view_refs.values()))
                ),
                execution_status=ExecutionStatus.PENDING,
                model_status=ModelStatus.READY,
                current_task=f"awaiting_agent:{exc.stage}",
                warnings=(f"{exc.stage}: candidate rejected: {exc.reason}",),
                completed_at=None,
            )
            self._write_application_run(
                awaiting_retry,
                selection=selection,
                purpose=purpose,
                token_budget=effective_budget,
            )
            self._emit(run_id, "agent_candidate_rejected", exc.stage)
            return awaiting_retry
        except AgentInputRequired as exc:
            persisted = self._runner.get(run_id)
            awaiting = replace(
                persisted,
                artifacts=tuple(
                    dict.fromkeys((*persisted.artifacts, *stage_view_refs.values()))
                ),
                execution_status=ExecutionStatus.PENDING,
                current_task=f"awaiting_agent:{exc.request.stage}",
            )
            self._write_application_run(
                awaiting,
                selection=selection,
                purpose=purpose,
                token_budget=effective_budget,
            )
            self._emit(run_id, "agent_input_required", exc.request.stage)
            return awaiting

        projections = write_projection_artifacts(bundle, self._artifacts)
        failed = bundle.execution_status is ExecutionStatus.FAILED
        persisted = self._runner.get(run_id)
        completed = replace(
            persisted,
            execution_status=bundle.execution_status,
            epistemic_status=bundle.epistemic_status,
            model_status=ModelStatus.FAILED if failed else ModelStatus.READY,
            publication_status=(
                PublicationStatus.WITHHELD if failed else PublicationStatus.INTERNAL
            ),
            current_task="failed" if failed else "completed",
            artifacts=(
                *persisted.artifacts,
                *(
                    reference
                    for reference in stage_view_refs.values()
                    if reference not in persisted.artifacts
                ),
                projections.bundle,
                projections.report,
            ),
            warnings=((bundle.failure,) if bundle.failure else ()),
            completed_at=None if failed else datetime.now(UTC),
            content_digest=projections.bundle.content_digest,
        )
        self._write_application_run(
            completed,
            selection=selection,
            purpose=purpose,
            token_budget=effective_budget,
        )
        self._emit(
            run_id,
            "run_failed" if failed else "run_completed",
            completed.current_task,
        )
        return completed

    def _normalize_selection(
        self,
        value: ProviderSelection | Mapping[str, Any] | None,
    ) -> ProviderSelection:
        if isinstance(value, ProviderSelection):
            selection = value
        elif isinstance(value, Mapping):
            selection = ProviderSelection.build(
                mode=str(value.get("mode", ProviderMode.PRIMARY)),
                primary=value.get("primary"),
                candidates=value.get("candidates", ()),
            )
        elif value is None:
            selection = self._default_selection()
        else:
            raise TypeError("provider_selection must be a ProviderSelection or mapping")
        if (
            selection.mode is ProviderMode.PRIMARY
            and selection.primary is None
            and not selection.candidates
        ):
            selection = self._default_selection()
        if selection.mode is not ProviderMode.AGENT_TAKEOVER and selection.primary is None:
            raise ProviderUnavailableError("provider selection has no primary provider")
        return selection

    def _default_selection(self) -> ProviderSelection:
        model_kinds = tuple(
            dict.fromkeys(
                provider.kind
                for provider in self._configured_providers
                if provider.kind is not ProviderKind.AGENT
            )
        )
        if not model_kinds:
            raise ProviderUnavailableError(
                "no model provider is configured; select agent_takeover or configure "
                "a local/API provider"
            )
        if len(model_kinds) > 1:
            raise ProviderConflictError(
                "multiple providers are configured; select primary, compare, or fallback"
            )
        return ProviderSelection.build(primary=model_kinds[0])

    @staticmethod
    def _new_run_id(
        snapshot: SourceDocumentSnapshot,
        selection: ProviderSelection,
        *,
        idempotency_key: str,
    ) -> str:
        policy = json.dumps(selection.to_dict(), sort_keys=True, separators=(",", ":"))
        return stable_id(
            "run",
            snapshot.snapshot_id,
            _PIPELINE_POLICY,
            policy,
            "schema:1",
            idempotency_key,
        )

    def _write_application_run(
        self,
        run: ReadingRun,
        *,
        selection: ProviderSelection,
        purpose: str,
        token_budget: int,
    ) -> None:
        self._run_store.write(
            run,
            pipeline_policy=_PIPELINE_POLICY,
            selection=selection,
            purpose=purpose,
            token_budget=token_budget,
        )

    def _emit(self, run_id: str, event_type: str, task: str) -> None:
        self._events.append(
            self._layout.run_events(run_id),
            {
                "schema_version": "1",
                "event_type": event_type,
                "run_id": run_id,
                "task": task,
                "occurred_at": datetime.now(UTC),
            },
        )

    def _validate_run_artifacts(self, run: ReadingRun) -> None:
        for artifact in run.artifacts:
            try:
                self._artifacts.read_bytes(artifact)
            except (FileNotFoundError, ValueError) as exc:
                raise ValueError(
                    f"run artifact is missing or corrupt: {artifact.artifact_id}"
                ) from exc


ReadweltProject = ReadweltApplicationService

"""Deterministic gates around model-provided six-stage candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from readwelt.domain.documents import SourceDocumentSnapshot
from readwelt.domain.ids import stable_id
from readwelt.domain.reading import (
    EvidencePacket,
    LedgerDecision,
    LedgerLine,
    ReadingBundle,
    ReadingClaim,
    ReadingClaimLedger,
    ReadingGap,
    ReadingStage,
    StageArtifact,
)
from readwelt.domain.status import EpistemicStatus, ExecutionStatus
from readwelt.providers.contracts import AgentInputRequired, StageCandidate, StageRequest
from readwelt.providers.model_protocol import CandidateProvider

_STAGES = (
    ReadingStage.MAINLINE,
    ReadingStage.STRUCTURE,
    ReadingStage.DECOMPRESSION,
    ReadingStage.AUTHOR_MODEL,
    ReadingStage.BOUNDARIES,
    ReadingStage.TRANSFER,
)
_ARTICLE_ONLY = frozenset((ReadingStage.MAINLINE, ReadingStage.STRUCTURE))
_ACCEPTED = frozenset((LedgerDecision.ACCEPTED, LedgerDecision.QUALIFIED))
_STAGE_POLICIES: Mapping[ReadingStage, Mapping[str, Any]] = {
    ReadingStage.MAINLINE: {
        "goal": "Recover the article's main line using only the supplied source anchors.",
        "produce": (
            "core idea, core question, major claims, internal evidence, "
            "reasoning chain, and source-underdetermined gaps"
        ),
        "constraints": (
            "Every strong claim must cite anchor_ids; do not use biography, "
            "historical background, external research, or imported theory."
        ),
    },
    ReadingStage.STRUCTURE: {
        "goal": "Map how the article's argument is constructed.",
        "produce": (
            "paragraph functions and claim/premise/evidence/example/objection/"
            "qualification/conclusion relationships"
        ),
        "constraints": (
            "Separate explicit structure from inference and the author's claims "
            "from quoted claims; use only source anchors and accepted stage-1 claims."
        ),
    },
    ReadingStage.DECOMPRESSION: {
        "goal": "Decompress knowledge assumed or compressed by the article.",
        "produce": (
            "prerequisites, concepts, context, verification targets, and conflicts "
            "linked to specific source or upstream claim ids"
        ),
        "constraints": (
            "External evidence may support, qualify, or challenge frozen article "
            "understanding, but must not rewrite stages 1-2."
        ),
    },
    ReadingStage.AUTHOR_MODEL: {
        "goal": "Recover a bounded model of how the author sees and selects the problem.",
        "produce": (
            "core assumptions, salient objects, problem genesis, chosen and rejected "
            "methods, plus at least two competing interpretations"
        ),
        "constraints": (
            "Mark interpretation distance and evidence; do not present speculation "
            "as author fact. Every competing claim must include a distinct "
            "provenance.interpretation_id."
        ),
    },
    ReadingStage.BOUNDARIES: {
        "goal": "Pressure-test the settled reading.",
        "produce": (
            "implicit assumptions, validity conditions, counterexamples, temporal/"
            "regional/institutional boundaries, alternatives, and missing evidence"
        ),
        "constraints": "Qualify or reject claims that do not survive the boundary test.",
    },
    ReadingStage.TRANSFER: {
        "goal": "Transfer only claims that survived the stage-5 boundary test.",
        "produce": (
            "original method, abstract principle, invariant mechanism, prerequisites, "
            "non-transferable contingencies, new-domain example, and failure test"
        ),
        "constraints": (
            "Do not derive a transfer principle directly from an attractive sentence; "
            "every transfer must cite accepted or qualified stage-5 source_claim_ids."
        ),
    },
}

_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "anchor_ids"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "text": {"type": "string"},
                    "anchor_ids": {"type": "array", "items": {"type": "string"}},
                    "decision": {
                        "enum": [decision.value for decision in LedgerDecision],
                    },
                    "source_claim_ids": {"type": "array", "items": {"type": "string"}},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                    "provenance": {"type": "object"},
                },
            },
        },
        "gaps": {"type": "array"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}

StageArtifactSink = Callable[[StageArtifact], Awaitable[None]]


class SixStageReadingEngine:
    """Execute the fixed stage order and freeze every accepted result."""

    def __init__(self, provider: CandidateProvider) -> None:
        self._provider = provider

    async def run(
        self,
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
        *,
        initial_artifacts: Sequence[StageArtifact] = (),
        artifact_sink: StageArtifactSink | None = None,
    ) -> ReadingBundle:
        if evidence.run_id == "":
            raise ValueError("evidence run_id is required")
        anchor_ids = self._validate_evidence(snapshot, evidence)
        self._validate_initial_artifacts(evidence.run_id, initial_artifacts)
        artifacts = list(initial_artifacts)
        transitions: list[str] = ["created", "entry_check"]
        transitions.extend(f"resumed:{artifact.stage.value}" for artifact in artifacts)
        known_claim_ids = {claim.claim_id for artifact in artifacts for claim in artifact.claims}

        for stage in _STAGES[len(artifacts) :]:
            transitions.append(stage.value)
            eligible = self._eligible_upstream_claims(stage, artifacts)
            try:
                request = self._build_request(
                    stage=stage,
                    snapshot=snapshot,
                    evidence=evidence,
                    artifacts=artifacts,
                    upstream_claims=eligible,
                )
                candidate = await self._provider.generate(request, _RESPONSE_SCHEMA)
                artifact = self._settle_candidate(
                    candidate=candidate,
                    stage=stage,
                    run_id=evidence.run_id,
                    input_artifacts=artifacts,
                    allowed_anchor_ids=anchor_ids,
                    allowed_source_claim_ids={claim.claim_id for claim in eligible},
                    known_claim_ids=known_claim_ids,
                )
                if stage is ReadingStage.MAINLINE:
                    artifact = self._add_entry_gaps(artifact, snapshot, evidence)
                if stage is ReadingStage.STRUCTURE:
                    artifacts.append(artifact)
                    if artifact_sink is not None:
                        await artifact_sink(artifact)
                    known_claim_ids.update(claim.claim_id for claim in artifact.claims)
                    gap_state = self._gap_gate(artifacts)
                    transitions.append(f"gap_gate:{gap_state.value}")
                    continue
                if stage is ReadingStage.AUTHOR_MODEL:
                    transitions.append("mediation")
                    artifact = self._mediate_author_model(artifact)
                artifacts.append(artifact)
                if artifact_sink is not None:
                    await artifact_sink(artifact)
                known_claim_ids.update(claim.claim_id for claim in artifact.claims)
            except AgentInputRequired:
                raise
            except Exception as exc:
                transitions.append("failed")
                return self._bundle(
                    run_id=evidence.run_id,
                    snapshot_id=snapshot.snapshot_id,
                    artifacts=artifacts,
                    transitions=transitions,
                    execution_status=ExecutionStatus.FAILED,
                    failure=f"{stage.value}: {type(exc).__name__}: {exc}",
                )

        transitions.extend(("final_ledger", "completed"))
        return self._bundle(
            run_id=evidence.run_id,
            snapshot_id=snapshot.snapshot_id,
            artifacts=artifacts,
            transitions=transitions,
            execution_status=ExecutionStatus.COMPLETED,
        )

    @staticmethod
    def _validate_initial_artifacts(
        run_id: str,
        artifacts: Sequence[StageArtifact],
    ) -> None:
        if len(artifacts) > len(_STAGES):
            raise ValueError("too many initial stage artifacts")
        previous_ids: list[str] = []
        known_claim_ids: set[str] = set()
        for expected_stage, artifact in zip(_STAGES, artifacts, strict=False):
            if artifact.run_id != run_id:
                raise ValueError("initial artifact belongs to a different run")
            if artifact.stage is not expected_stage:
                raise ValueError("initial artifacts must form the fixed stage prefix")
            if artifact.input_artifact_ids != tuple(previous_ids):
                raise ValueError("initial artifact lineage does not match its prefix")
            claim_ids = {claim.claim_id for claim in artifact.claims}
            if known_claim_ids & claim_ids:
                raise ValueError("initial artifacts contain duplicate claim ids")
            known_claim_ids.update(claim_ids)
            previous_ids.append(artifact.artifact_id)

    @staticmethod
    def _validate_evidence(
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
    ) -> frozenset[str]:
        section_anchors = tuple(section.anchor for section in snapshot.sections)
        all_anchors = (*section_anchors, *evidence.anchors)
        if any(anchor.snapshot_id != snapshot.snapshot_id for anchor in all_anchors):
            raise ValueError("all evidence anchors must belong to the source snapshot")
        return frozenset(anchor.anchor_id for anchor in all_anchors)

    @staticmethod
    def _eligible_upstream_claims(
        stage: ReadingStage,
        artifacts: Sequence[StageArtifact],
    ) -> tuple[ReadingClaim, ...]:
        if not artifacts:
            return ()
        if stage is ReadingStage.TRANSFER:
            boundary = artifacts[-1]
            if boundary.stage is not ReadingStage.BOUNDARIES:
                raise ValueError("stage 6 requires the settled stage 5 artifact")
            return boundary.accepted_claims
        return tuple(claim for artifact in artifacts for claim in artifact.accepted_claims)

    def _build_request(
        self,
        *,
        stage: ReadingStage,
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
        artifacts: Sequence[StageArtifact],
        upstream_claims: Sequence[ReadingClaim],
    ) -> StageRequest:
        external_allowed = stage not in _ARTICLE_ONLY
        packet: dict[str, Any] = {
            "stage_policy": dict(_STAGE_POLICIES[stage]),
            "response_policy": {
                "claims": (
                    "Return atomic claims with anchor_ids, decision, source_claim_ids "
                    "when derived from upstream claims, limitations, and provenance. "
                    "The decision is a proposal that deterministic runtime gates may "
                    "downgrade or reject."
                ),
                "uncertainty": (
                    "Use gaps and qualified/underdetermined decisions instead of "
                    "inventing missing evidence."
                ),
            },
            "snapshot_id": snapshot.snapshot_id,
            "document_id": snapshot.document_id,
            "title": snapshot.title,
            "language": snapshot.language,
            "normalized_text_ref": snapshot.normalized_text_ref,
            "retrieval_queries": list(evidence.retrieval_queries),
            "coverage_complete": evidence.coverage_complete,
            "omitted_anchor_ids": list(evidence.omitted_anchor_ids),
            "anchors": [
                {
                    "anchor_id": anchor.anchor_id,
                    "section_id": anchor.section_id,
                    "start_offset": anchor.start_offset,
                    "end_offset": anchor.end_offset,
                    "exact_text": anchor.exact_text,
                }
                for anchor in evidence.anchors
            ],
            "omitted_sections": list(evidence.omitted_sections),
            "external_evidence": (list(evidence.external_evidence) if external_allowed else []),
            "external_evidence_allowed": external_allowed,
            "upstream_artifacts": [
                {"artifact_id": item.artifact_id, "stage": item.stage.value} for item in artifacts
            ],
            "upstream_claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "stage": claim.stage.value,
                    "decision": claim.decision.value,
                    "anchor_ids": list(claim.anchor_ids),
                }
                for claim in upstream_claims
            ],
        }
        return StageRequest(
            schema_version="1",
            run_id=evidence.run_id,
            stage=stage.value,
            evidence_packet=packet,
            capabilities=("external_evidence",) if external_allowed else (),
            provenance={
                "provider": self._provider.name,
                "article_only": not external_allowed,
            },
        )

    def _settle_candidate(
        self,
        *,
        candidate: StageCandidate,
        stage: ReadingStage,
        run_id: str,
        input_artifacts: Sequence[StageArtifact],
        allowed_anchor_ids: frozenset[str],
        allowed_source_claim_ids: set[str],
        known_claim_ids: set[str],
    ) -> StageArtifact:
        if candidate.schema_version != "1":
            raise ValueError("unsupported candidate schema")
        if candidate.run_id != run_id or candidate.stage != stage.value:
            raise ValueError("candidate run_id and stage must match the request")
        payload = candidate.candidate
        raw_claims = _mapping_sequence(payload.get("claims", ()), "claims")
        raw_gaps = _mapping_sequence(payload.get("gaps", ()), "gaps")
        claims = tuple(
            self._parse_claim(
                item,
                stage=stage,
                allowed_anchor_ids=allowed_anchor_ids,
                allowed_source_claim_ids=allowed_source_claim_ids,
                known_claim_ids=known_claim_ids,
                provider=candidate.provider,
            )
            for item in raw_claims
        )
        claim_ids = [claim.claim_id for claim in claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("candidate claim ids must be unique")
        gaps = tuple(self._parse_gap(item, stage) for item in raw_gaps)
        warnings = _string_tuple(payload.get("warnings", ()), "warnings")
        status = _epistemic_status(claims, gaps)
        digest_payload = {
            "run_id": run_id,
            "stage": stage.value,
            "claims": [_claim_dict(claim) for claim in claims],
            "gaps": [_gap_dict(gap) for gap in gaps],
            "warnings": warnings,
            "inputs": [item.artifact_id for item in input_artifacts],
            "provider": candidate.provider,
            "model": candidate.model,
            "status": status.value,
        }
        digest = _digest(digest_payload)
        return StageArtifact(
            artifact_id=stable_id("stage_artifact", run_id, stage.value, digest),
            run_id=run_id,
            stage=stage,
            claims=claims,
            gaps=gaps,
            warnings=warnings,
            input_artifact_ids=tuple(item.artifact_id for item in input_artifacts),
            provider=candidate.provider,
            model=candidate.model,
            status=status,
            content_digest=digest,
            provider_provenance=_provenance_tuple(candidate.provenance),
        )

    @staticmethod
    def _parse_claim(
        value: Mapping[str, Any],
        *,
        stage: ReadingStage,
        allowed_anchor_ids: frozenset[str],
        allowed_source_claim_ids: set[str],
        known_claim_ids: set[str],
        provider: str,
    ) -> ReadingClaim:
        text = str(value.get("text", "")).strip()
        anchors = _string_tuple(value.get("anchor_ids", ()), "anchor_ids")
        decision = LedgerDecision(str(value.get("decision", "accepted")))
        source_claim_ids = _string_tuple(value.get("source_claim_ids", ()), "source_claim_ids")
        if not text:
            raise ValueError("claim text is required")
        if decision in _ACCEPTED and not anchors:
            raise ValueError("accepted and qualified claims require an article anchor")
        if stage not in _ARTICLE_ONLY and decision in _ACCEPTED and not source_claim_ids:
            raise ValueError(
                "accepted and qualified stages 3-6 claims require an eligible upstream source claim"
            )
        unknown_anchors = set(anchors) - allowed_anchor_ids
        if unknown_anchors:
            raise ValueError(f"unknown anchor ids: {sorted(unknown_anchors)}")
        unknown_sources = set(source_claim_ids) - allowed_source_claim_ids
        if unknown_sources:
            raise ValueError(f"ineligible source claim ids: {sorted(unknown_sources)}")
        explicit_id = str(value.get("claim_id", "")).strip()
        claim_id = explicit_id or stable_id("claim", stage.value, text, *anchors, *source_claim_ids)
        if claim_id in known_claim_ids:
            raise ValueError(f"claim id already exists: {claim_id}")
        raw_provenance = value.get("provenance", {})
        if not isinstance(raw_provenance, Mapping):
            raise ValueError("claim provenance must be an object")
        provenance = tuple(sorted((str(key), str(item)) for key, item in raw_provenance.items()))
        if not provenance:
            provenance = (("provider", provider),)
        return ReadingClaim(
            claim_id=claim_id,
            text=text,
            stage=stage,
            anchor_ids=anchors,
            decision=decision,
            source_claim_ids=source_claim_ids,
            limitations=_string_tuple(value.get("limitations", ()), "limitations"),
            provenance=provenance,
        )

    @staticmethod
    def _parse_gap(value: Mapping[str, Any], stage: ReadingStage) -> ReadingGap:
        kind = str(value.get("kind", "unspecified")).strip()
        description = str(value.get("description", "")).strip()
        if not description:
            raise ValueError("gap description is required")
        affected = _string_tuple(value.get("affected_claim_ids", ()), "affected_claim_ids")
        explicit_id = str(value.get("gap_id", "")).strip()
        return ReadingGap(
            gap_id=explicit_id or stable_id("gap", stage.value, kind, description, *affected),
            kind=kind,
            description=description,
            origin_stage=stage,
            affected_claim_ids=affected,
            critical=bool(value.get("critical", False)),
            repairable=bool(value.get("repairable", False)),
            resolved=bool(value.get("resolved", False)),
        )

    @staticmethod
    def _add_entry_gaps(
        artifact: StageArtifact,
        snapshot: SourceDocumentSnapshot,
        evidence: EvidencePacket,
    ) -> StageArtifact:
        additions = [
            ReadingGap(
                gap_id=stable_id("gap", artifact.stage.value, "omitted_section", section),
                kind="missing_section",
                description=f"section omitted from evidence packet: {section}",
                origin_stage=artifact.stage,
                critical=True,
            )
            for section in evidence.omitted_sections
        ]
        if evidence.omitted_anchor_ids:
            additions.append(
                ReadingGap(
                    gap_id=stable_id(
                        "gap",
                        artifact.stage.value,
                        "omitted_anchors",
                        *evidence.omitted_anchor_ids,
                    ),
                    kind="evidence_budget_omission",
                    description=(
                        f"{len(evidence.omitted_anchor_ids)} source anchors were omitted "
                        "from the bounded evidence packet"
                    ),
                    origin_stage=artifact.stage,
                    critical=True,
                )
            )
        if not evidence.coverage_complete and not additions:
            additions.append(
                ReadingGap(
                    gap_id=stable_id(
                        "gap",
                        artifact.stage.value,
                        "incomplete_source_coverage",
                    ),
                    kind="incomplete_source_coverage",
                    description="semantic preprocessing did not cover the complete source",
                    origin_stage=artifact.stage,
                    critical=True,
                )
            )
        warnings = (*artifact.warnings, *snapshot.parse_findings)
        if not additions and warnings == artifact.warnings:
            return artifact
        return _rebuild_artifact(artifact, gaps=(*artifact.gaps, *additions), warnings=warnings)

    @staticmethod
    def _gap_gate(artifacts: Sequence[StageArtifact]) -> EpistemicStatus:
        gaps = tuple(gap for artifact in artifacts for gap in artifact.gaps)
        if any(gap.critical and not gap.resolved for gap in gaps):
            return EpistemicStatus.UNDERDETERMINED
        if any(not gap.resolved for gap in gaps):
            return EpistemicStatus.PARTIAL
        return EpistemicStatus.SUFFICIENT

    @staticmethod
    def _mediate_author_model(artifact: StageArtifact) -> StageArtifact:
        eligible = artifact.accepted_claims
        interpretations = {dict(claim.provenance).get("interpretation_id") for claim in eligible}
        interpretations.discard(None)
        interpretations.discard("")
        if len(interpretations) >= 2:
            return artifact
        mediated_claims = tuple(
            replace(
                claim,
                decision=LedgerDecision.UNDERDETERMINED,
                limitations=(
                    *claim.limitations,
                    "author model lacks two explicitly identified competing interpretations",
                ),
            )
            if claim.decision in _ACCEPTED
            else claim
            for claim in artifact.claims
        )
        gap = ReadingGap(
            gap_id=stable_id(
                "gap",
                artifact.stage.value,
                "competing_interpretation",
                artifact.artifact_id,
            ),
            kind="competing_interpretation",
            description=(
                "stage 4 requires at least two distinct provenance.interpretation_id values"
            ),
            origin_stage=artifact.stage,
            affected_claim_ids=tuple(claim.claim_id for claim in eligible),
            critical=True,
        )
        return _rebuild_artifact(
            artifact,
            claims=mediated_claims,
            gaps=(*artifact.gaps, gap),
        )

    @staticmethod
    def _bundle(
        *,
        run_id: str,
        snapshot_id: str,
        artifacts: Sequence[StageArtifact],
        transitions: Sequence[str],
        execution_status: ExecutionStatus,
        failure: str | None = None,
    ) -> ReadingBundle:
        lines = tuple(
            LedgerLine(
                claim_id=claim.claim_id,
                stage=claim.stage,
                decision=claim.decision,
                supporting_anchor_ids=claim.anchor_ids,
                source_claim_ids=claim.source_claim_ids,
                limitations=claim.limitations,
            )
            for artifact in artifacts
            for claim in artifact.claims
        )
        unresolved = tuple(
            line.claim_id
            for line in lines
            if line.decision in (LedgerDecision.CONTESTED, LedgerDecision.UNDERDETERMINED)
        )
        rejected = tuple(
            line.claim_id for line in lines if line.decision is LedgerDecision.REJECTED
        )
        ledger_payload = {
            "run_id": run_id,
            "policy_version": "six-stage-v1",
            "lines": [
                {
                    "claim_id": line.claim_id,
                    "stage": line.stage.value,
                    "decision": line.decision.value,
                    "anchors": line.supporting_anchor_ids,
                    "sources": line.source_claim_ids,
                    "limitations": line.limitations,
                }
                for line in lines
            ],
        }
        ledger_digest = _digest(ledger_payload)
        ledger = ReadingClaimLedger(
            ledger_id=stable_id("reading_ledger", run_id, ledger_digest),
            run_id=run_id,
            policy_version="six-stage-v1",
            lines=lines,
            unresolved_claim_ids=unresolved,
            rejected_claim_ids=rejected,
            content_digest=ledger_digest,
        )
        epistemic = _bundle_epistemic_status(artifacts, execution_status)
        return ReadingBundle(
            run_id=run_id,
            snapshot_id=snapshot_id,
            artifacts=tuple(artifacts),
            ledger=ledger,
            transitions=tuple(transitions),
            execution_status=execution_status,
            epistemic_status=epistemic,
            failure=failure,
        )


def _mapping_sequence(value: object, field: str) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    result: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{field} entries must be objects")
        result.append(item)
    return tuple(result)


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return tuple(str(item) for item in value)


def _provenance_tuple(value: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                str(key),
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                if isinstance(item, (Mapping, list, tuple))
                else str(item),
            )
            for key, item in value.items()
        )
    )


def _epistemic_status(
    claims: Sequence[ReadingClaim],
    gaps: Sequence[ReadingGap],
) -> EpistemicStatus:
    if any(gap.critical and not gap.resolved for gap in gaps):
        return EpistemicStatus.UNDERDETERMINED
    if not any(claim.decision in _ACCEPTED for claim in claims):
        return EpistemicStatus.UNDERDETERMINED
    if any(not gap.resolved for gap in gaps) or any(
        claim.decision in (LedgerDecision.CONTESTED, LedgerDecision.UNDERDETERMINED)
        for claim in claims
    ):
        return EpistemicStatus.PARTIAL
    return EpistemicStatus.SUFFICIENT


def _bundle_epistemic_status(
    artifacts: Sequence[StageArtifact],
    execution_status: ExecutionStatus,
) -> EpistemicStatus:
    if execution_status is ExecutionStatus.FAILED:
        return EpistemicStatus.INVALID
    statuses = {artifact.status for artifact in artifacts}
    if EpistemicStatus.INVALID in statuses:
        return EpistemicStatus.INVALID
    if EpistemicStatus.UNDERDETERMINED in statuses:
        return EpistemicStatus.UNDERDETERMINED
    if EpistemicStatus.PARTIAL in statuses:
        return EpistemicStatus.PARTIAL
    return EpistemicStatus.SUFFICIENT


def _claim_dict(claim: ReadingClaim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "stage": claim.stage.value,
        "anchor_ids": claim.anchor_ids,
        "decision": claim.decision.value,
        "source_claim_ids": claim.source_claim_ids,
        "limitations": claim.limitations,
        "provenance": claim.provenance,
    }


def _gap_dict(gap: ReadingGap) -> dict[str, Any]:
    return {
        "gap_id": gap.gap_id,
        "kind": gap.kind,
        "description": gap.description,
        "stage": gap.origin_stage.value,
        "affected_claim_ids": gap.affected_claim_ids,
        "critical": gap.critical,
        "repairable": gap.repairable,
        "resolved": gap.resolved,
    }


def _rebuild_artifact(
    artifact: StageArtifact,
    *,
    claims: Sequence[ReadingClaim] | None = None,
    gaps: Sequence[ReadingGap] | None = None,
    warnings: Sequence[str] | None = None,
) -> StageArtifact:
    settled_claims = tuple(claims) if claims is not None else artifact.claims
    settled_gaps = tuple(gaps) if gaps is not None else artifact.gaps
    settled_warnings = tuple(warnings) if warnings is not None else artifact.warnings
    payload = {
        "run_id": artifact.run_id,
        "stage": artifact.stage.value,
        "claims": [_claim_dict(claim) for claim in settled_claims],
        "gaps": [_gap_dict(gap) for gap in settled_gaps],
        "warnings": settled_warnings,
        "inputs": artifact.input_artifact_ids,
        "provider": artifact.provider,
        "model": artifact.model,
    }
    digest = _digest(payload)
    return StageArtifact(
        artifact_id=stable_id("stage_artifact", artifact.run_id, artifact.stage.value, digest),
        run_id=artifact.run_id,
        stage=artifact.stage,
        claims=settled_claims,
        gaps=settled_gaps,
        warnings=settled_warnings,
        input_artifact_ids=artifact.input_artifact_ids,
        provider=artifact.provider,
        model=artifact.model,
        status=_epistemic_status(settled_claims, settled_gaps),
        content_digest=digest,
        provider_provenance=artifact.provider_provenance,
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

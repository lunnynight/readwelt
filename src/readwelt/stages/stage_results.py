"""Stage artifact repair, mediation, gating, and final bundle assembly."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, replace

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
    StageArtifact,
)
from readwelt.domain.status import EpistemicStatus, ExecutionStatus

from .candidate_settlement import (
    claim_dict,
    digest_value,
    epistemic_status,
    gap_dict,
)
from .policies import ACCEPTED


def add_entry_gaps(
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
    return rebuild_artifact(
        artifact,
        gaps=(*artifact.gaps, *additions),
        warnings=warnings,
    )


def gap_gate(artifacts: Sequence[StageArtifact]) -> EpistemicStatus:
    gaps = tuple(gap for artifact in artifacts for gap in artifact.gaps)
    if any(gap.critical and not gap.resolved for gap in gaps):
        return EpistemicStatus.UNDERDETERMINED
    if any(not gap.resolved for gap in gaps):
        return EpistemicStatus.PARTIAL
    return EpistemicStatus.SUFFICIENT


def mediate_author_model(artifact: StageArtifact) -> StageArtifact:
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
        if claim.decision in ACCEPTED
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
        description=("stage 4 requires at least two distinct provenance.interpretation_id values"),
        origin_stage=artifact.stage,
        affected_claim_ids=tuple(claim.claim_id for claim in eligible),
        critical=True,
    )
    return rebuild_artifact(
        artifact,
        claims=mediated_claims,
        gaps=(*artifact.gaps, gap),
    )


def build_bundle(
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
            source_citations=claim.source_citations,
        )
        for artifact in artifacts
        for claim in artifact.claims
    )
    unresolved = tuple(
        line.claim_id
        for line in lines
        if line.decision in (LedgerDecision.CONTESTED, LedgerDecision.UNDERDETERMINED)
    )
    rejected = tuple(line.claim_id for line in lines if line.decision is LedgerDecision.REJECTED)
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
                "source_citations": [
                    {
                        "schema_version": citation.schema_version,
                        "kind": citation.kind.value,
                        "identity": citation.identity,
                    }
                    for citation in line.source_citations
                ],
                "limitations": line.limitations,
            }
            for line in lines
        ],
    }
    ledger_digest = digest_value(ledger_payload)
    ledger = ReadingClaimLedger(
        ledger_id=stable_id("reading_ledger", run_id, ledger_digest),
        run_id=run_id,
        policy_version="six-stage-v1",
        lines=lines,
        unresolved_claim_ids=unresolved,
        rejected_claim_ids=rejected,
        content_digest=ledger_digest,
    )
    return ReadingBundle(
        run_id=run_id,
        snapshot_id=snapshot_id,
        artifacts=tuple(artifacts),
        ledger=ledger,
        transitions=tuple(transitions),
        execution_status=execution_status,
        epistemic_status=bundle_epistemic_status(artifacts, execution_status),
        failure=failure,
    )


def bundle_epistemic_status(
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


def rebuild_artifact(
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
        "claims": [claim_dict(claim) for claim in settled_claims],
        "gaps": [gap_dict(gap) for gap in settled_gaps],
        "warnings": settled_warnings,
        "inputs": artifact.input_artifact_ids,
        "provider": artifact.provider,
        "model": artifact.model,
        "input_state": (asdict(artifact.input_state) if artifact.input_state is not None else None),
    }
    digest = digest_value(payload)
    return StageArtifact(
        artifact_id=stable_id(
            "stage_artifact",
            artifact.run_id,
            artifact.stage.value,
            digest,
        ),
        run_id=artifact.run_id,
        stage=artifact.stage,
        claims=settled_claims,
        gaps=settled_gaps,
        warnings=settled_warnings,
        input_artifact_ids=artifact.input_artifact_ids,
        provider=artifact.provider,
        model=artifact.model,
        status=epistemic_status(settled_claims, settled_gaps),
        content_digest=digest,
        provider_provenance=artifact.provider_provenance,
        input_state=artifact.input_state,
    )

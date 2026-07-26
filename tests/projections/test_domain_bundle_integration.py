from __future__ import annotations

from readwelt.domain.reading import (
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
from readwelt.projections import canonical_bundle_document, render_reader_markdown


def test_current_domain_bundle_projects_without_projection_domain_coupling() -> None:
    claim = ReadingClaim(
        claim_id="claim-mainline",
        text="实践构成认识的检验环节。",
        stage=ReadingStage.MAINLINE,
        anchor_ids=("anchor-1",),
        decision=LedgerDecision.ACCEPTED,
        provenance=(("provider", "agent"), ("model", "codex")),
    )
    gap = ReadingGap(
        gap_id="gap-source",
        kind="broken_reference",
        description="引文缺少版本信息。",
        origin_stage=ReadingStage.MAINLINE,
    )
    artifact = StageArtifact(
        artifact_id="stage-artifact-1",
        run_id="run-1",
        stage=ReadingStage.MAINLINE,
        claims=(claim,),
        gaps=(gap,),
        warnings=(),
        input_artifact_ids=(),
        provider="agent",
        model="codex",
        status=EpistemicStatus.PARTIAL,
        content_digest=f"sha256:{'0' * 64}",
    )
    ledger = ReadingClaimLedger(
        ledger_id="ledger-1",
        run_id="run-1",
        policy_version="1",
        lines=(
            LedgerLine(
                claim_id=claim.claim_id,
                stage=claim.stage,
                decision=claim.decision,
                supporting_anchor_ids=claim.anchor_ids,
                source_claim_ids=(),
                limitations=(),
            ),
        ),
        unresolved_claim_ids=(),
        rejected_claim_ids=(),
        content_digest=f"sha256:{'1' * 64}",
    )
    bundle = ReadingBundle(
        run_id="run-1",
        snapshot_id="snapshot-1",
        artifacts=(artifact,),
        ledger=ledger,
        transitions=("stage_1_mainline:completed",),
        execution_status=ExecutionStatus.COMPLETED,
        epistemic_status=EpistemicStatus.PARTIAL,
    )

    document = canonical_bundle_document(bundle)
    report = render_reader_markdown(bundle)

    assert document["run_id"] == "run-1"
    assert document["artifacts"][0]["stage"] == "stage_1_mainline"
    assert "实践构成认识的检验环节。" in report
    assert "`anchor-1`" in report
    assert "provider=agent；model=codex" in report
    assert "broken_reference / open" in report

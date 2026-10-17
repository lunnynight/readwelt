"""Deterministic settlement of model-proposed stage candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from readwelt.article_graph.digest import content_digest
from readwelt.domain.ids import stable_id
from readwelt.domain.reading import (
    DecompressionArtifact,
    DecompressionUnit,
    LedgerDecision,
    ReadingClaim,
    ReadingGap,
    ReadingStage,
    SourceCitation,
    SourceCitationKind,
    StageArtifact,
    StageInputState,
    StageInputStatus,
)
from readwelt.domain.status import EpistemicStatus
from readwelt.providers.contracts import StageCandidate
from readwelt.stage_views import StageView

from .ai_boundary import settle_stage_provenance, validate_candidate_fields
from .policies import ACCEPTED, ARTICLE_ONLY


def settle_candidate(
    *,
    candidate: StageCandidate,
    stage: ReadingStage,
    run_id: str,
    input_artifacts: Sequence[StageArtifact],
    allowed_anchor_ids: frozenset[str],
    allowed_source_claim_ids: set[str],
    allowed_graph_object_ids: frozenset[str],
    allowed_source_citations: frozenset[SourceCitation] | None = None,
    known_claim_ids: set[str],
) -> StageArtifact:
    if candidate.schema_version != "1":
        raise ValueError("unsupported candidate schema")
    if candidate.run_id != run_id or candidate.stage != stage.value:
        raise ValueError("candidate run_id and stage must match the request")
    payload = candidate.candidate
    raw_claims = mapping_sequence(payload.get("claims", ()), "claims")
    raw_gaps = mapping_sequence(payload.get("gaps", ()), "gaps")
    claims = tuple(
        parse_claim(
            item,
            stage=stage,
            allowed_anchor_ids=allowed_anchor_ids,
            allowed_source_claim_ids=allowed_source_claim_ids,
            allowed_graph_object_ids=allowed_graph_object_ids,
            allowed_source_citations=allowed_source_citations,
            known_claim_ids=known_claim_ids,
            provider=candidate.provider,
        )
        for item in raw_claims
    )
    claim_ids = [claim.claim_id for claim in claims]
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError("candidate claim ids must be unique")
    gaps = tuple(parse_gap(item, stage) for item in raw_gaps)
    warnings = string_tuple(payload.get("warnings", ()), "warnings")
    if stage is ReadingStage.DECOMPRESSION:
        decompression_artifact = parse_decompression_artifact(
            payload.get("decompression_units", ()),
            run_id=run_id,
            claims=claims,
            allowed_anchor_ids=allowed_anchor_ids,
            allowed_graph_object_ids=allowed_graph_object_ids,
            allowed_source_citations=allowed_source_citations,
        )
    else:
        if "decompression_units" in payload:
            raise ValueError("decompression units are only valid for stage three")
        decompression_artifact = None
    status = epistemic_status(claims, gaps)
    digest_payload = {
        "run_id": run_id,
        "stage": stage.value,
        "claims": [claim_dict(claim) for claim in claims],
        "gaps": [gap_dict(gap) for gap in gaps],
        "warnings": warnings,
        "inputs": [item.artifact_id for item in input_artifacts],
        "provider": candidate.provider,
        "model": candidate.model,
        "status": status.value,
    }
    if decompression_artifact is not None:
        digest_payload["decompression_artifact"] = decompression_artifact_dict(
            decompression_artifact
        )
    digest = digest_value(digest_payload)
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
        provider_provenance=provenance_tuple(candidate.provenance),
        decompression_artifact=decompression_artifact,
    )


def bind_stage_input(
    artifact: StageArtifact,
    stage_view: StageView | None,
) -> StageArtifact:
    """Bind the candidate to complete, provisional, or blocked StageView input."""

    if stage_view is None:
        return artifact
    coverage = stage_view.coverage
    completed_units = set(coverage.completed_unit_ids) if coverage is not None else set()
    completed_ranges = set(coverage.completed_range_ids) if coverage is not None else set()
    completed_elements = set(coverage.completed_element_ids) if coverage is not None else set()
    unresolved_critical = (
        tuple(
            (
                *(
                    f"unit:{identity}"
                    for identity in coverage.critical_unit_ids
                    if identity not in completed_units
                ),
                *(
                    f"range:{identity}"
                    for identity in coverage.critical_range_ids
                    if identity not in completed_ranges
                ),
                *(
                    f"element:{identity}"
                    for identity in coverage.critical_element_ids
                    if identity not in completed_elements
                ),
            )
        )
        if coverage is not None
        else ()
    )
    blocking_reasons = tuple(dict.fromkeys(item.reason for item in stage_view.blocking_records))
    if blocking_reasons or unresolved_critical:
        input_status = StageInputStatus.BLOCKED
    elif stage_view.continuation is not None:
        input_status = StageInputStatus.PROVISIONAL
    else:
        input_status = StageInputStatus.COMPLETE
    state = StageInputState(
        status=input_status,
        stage_view_digest=stage_view.content_digest,
        coverage_digest=(content_digest(coverage) if coverage is not None else None),
        continuation_digest=(
            stage_view.continuation.content_digest if stage_view.continuation is not None else None
        ),
        blocking_reasons=blocking_reasons,
        unresolved_critical_ids=unresolved_critical,
    )
    digest = digest_value(
        {
            "candidate_digest": artifact.content_digest,
            "input_state": {
                "schema_version": state.schema_version,
                "status": state.status.value,
                "stage_view_digest": state.stage_view_digest,
                "coverage_digest": state.coverage_digest,
                "continuation_digest": state.continuation_digest,
                "blocking_reasons": state.blocking_reasons,
                "unresolved_critical_ids": state.unresolved_critical_ids,
            },
        }
    )
    return replace(
        artifact,
        artifact_id=stable_id(
            "stage_artifact",
            artifact.run_id,
            artifact.stage.value,
            digest,
        ),
        content_digest=digest,
        input_state=state,
    )


def parse_claim(
    value: Mapping[str, Any],
    *,
    stage: ReadingStage,
    allowed_anchor_ids: frozenset[str],
    allowed_source_claim_ids: set[str],
    allowed_graph_object_ids: frozenset[str],
    allowed_source_citations: frozenset[SourceCitation] | None = None,
    known_claim_ids: set[str],
    provider: str,
) -> ReadingClaim:
    text = str(value.get("text", "")).strip()
    anchors = string_tuple(value.get("anchor_ids", ()), "anchor_ids")
    decision = LedgerDecision(str(value.get("decision", "accepted")))
    source_claim_ids = string_tuple(
        value.get("source_claim_ids", ()),
        "source_claim_ids",
    )
    graph_object_ids = string_tuple(
        value.get("graph_object_ids", ()),
        "graph_object_ids",
    )
    citations = list(parse_source_citations(value.get("source_citations", ())))
    for kind, identities in (
        (SourceCitationKind.ANCHOR, anchors),
        (SourceCitationKind.GRAPH_OBJECT, graph_object_ids),
    ):
        for identity in identities:
            citation = SourceCitation(kind, identity)
            if citation not in citations:
                citations.append(citation)
    anchors = tuple(
        citation.identity for citation in citations if citation.kind is SourceCitationKind.ANCHOR
    )
    graph_object_ids = tuple(
        citation.identity
        for citation in citations
        if citation.kind is SourceCitationKind.GRAPH_OBJECT
    )
    validate_candidate_fields(value)
    if not text:
        raise ValueError("claim text is required")
    if decision in ACCEPTED and not citations:
        raise ValueError("accepted and qualified claims require an admitted source citation")
    if stage not in ARTICLE_ONLY and decision in ACCEPTED and not source_claim_ids:
        raise ValueError(
            "accepted and qualified stages 3-6 claims require an eligible upstream source claim"
        )
    unknown_anchors = set(anchors) - allowed_anchor_ids
    if unknown_anchors:
        raise ValueError(
            f"anchor ids outside the admitted evidence packet: {sorted(unknown_anchors)}"
        )
    unknown_sources = set(source_claim_ids) - allowed_source_claim_ids
    if unknown_sources:
        raise ValueError(f"ineligible source claim ids: {sorted(unknown_sources)}")
    unknown_graph_objects = set(graph_object_ids) - allowed_graph_object_ids
    if unknown_graph_objects:
        raise ValueError(
            f"graph object ids outside the presented StageView: {sorted(unknown_graph_objects)}"
        )
    admitted_citations = (
        allowed_source_citations
        if allowed_source_citations is not None
        else frozenset(
            (
                *(
                    SourceCitation(SourceCitationKind.ANCHOR, identity)
                    for identity in allowed_anchor_ids
                ),
                *(
                    SourceCitation(SourceCitationKind.GRAPH_OBJECT, identity)
                    for identity in allowed_graph_object_ids
                ),
            )
        )
    )
    unknown_citations = tuple(
        citation for citation in citations if citation not in admitted_citations
    )
    if unknown_citations:
        raise ValueError(
            "source citations outside the presented provider material: "
            f"{[(item.kind.value, item.identity) for item in unknown_citations]}"
        )
    explicit_id = str(value.get("claim_id", "")).strip()
    claim_id = explicit_id or stable_id(
        "claim",
        stage.value,
        text,
        *(f"{item.kind.value}:{item.identity}" for item in citations),
        *source_claim_ids,
    )
    if claim_id in known_claim_ids:
        raise ValueError(f"claim id already exists: {claim_id}")
    provenance = settle_stage_provenance(
        value.get("provenance", {}),
        provider=provider,
        graph_object_ids=graph_object_ids,
    )
    return ReadingClaim(
        claim_id=claim_id,
        text=text,
        stage=stage,
        anchor_ids=anchors,
        decision=decision,
        source_claim_ids=source_claim_ids,
        limitations=string_tuple(value.get("limitations", ()), "limitations"),
        provenance=provenance,
        source_citations=tuple(citations),
    )


def parse_gap(value: Mapping[str, Any], stage: ReadingStage) -> ReadingGap:
    kind = str(value.get("kind", "unspecified")).strip()
    description = str(value.get("description", "")).strip()
    if not description:
        raise ValueError("gap description is required")
    affected = string_tuple(value.get("affected_claim_ids", ()), "affected_claim_ids")
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


def parse_decompression_artifact(
    value: object,
    *,
    run_id: str,
    claims: Sequence[ReadingClaim],
    allowed_anchor_ids: frozenset[str],
    allowed_graph_object_ids: frozenset[str],
    allowed_source_citations: frozenset[SourceCitation] | None,
) -> DecompressionArtifact:
    raw_units = mapping_sequence(value, "decompression_units")
    if not raw_units:
        raise ValueError("decompression stage requires at least one unit")
    claims_by_id = {claim.claim_id: claim for claim in claims}
    admitted_citations = (
        allowed_source_citations
        if allowed_source_citations is not None
        else frozenset(
            (
                *(
                    SourceCitation(SourceCitationKind.ANCHOR, identity)
                    for identity in allowed_anchor_ids
                ),
                *(
                    SourceCitation(SourceCitationKind.GRAPH_OBJECT, identity)
                    for identity in allowed_graph_object_ids
                ),
            )
        )
    )
    units: list[DecompressionUnit] = []
    for item in raw_units:
        claim_ids = string_tuple(item.get("claim_ids", ()), "claim_ids")
        if not claim_ids:
            raise ValueError("decompression unit requires linked stage claims")
        unknown_claim_ids = set(claim_ids) - set(claims_by_id)
        if unknown_claim_ids:
            raise ValueError(
                f"decompression unit references unknown stage claims: "
                f"{sorted(unknown_claim_ids)}"
            )
        source_citations = parse_source_citations(item.get("source_citations", ()))
        if not source_citations:
            raise ValueError("decompression unit requires source citations")
        unknown_citations = tuple(
            citation for citation in source_citations if citation not in admitted_citations
        )
        if unknown_citations:
            raise ValueError(
                "decompression unit cites material outside the presented source: "
                f"{[(item.kind.value, item.identity) for item in unknown_citations]}"
            )
        linked_citations = {
            citation
            for claim_id in claim_ids
            for citation in claims_by_id[claim_id].source_citations
        }
        if not set(source_citations).issubset(linked_citations):
            raise ValueError(
                "decompression unit citations must be grounded by linked claims"
            )

        def text_values(field: str) -> tuple[str, ...]:
            return tuple(item.strip() for item in string_tuple(item.get(field, ()), field))

        units.append(
            DecompressionUnit(
                unit_id=str(item.get("unit_id", "")).strip(),
                explanation=str(item.get("explanation", "")).strip(),
                claim_ids=claim_ids,
                source_citations=source_citations,
                concepts_introduced=text_values("concepts_introduced"),
                concepts_assumed=text_values("concepts_assumed"),
                mechanism_steps=text_values("mechanism_steps"),
                dependencies=text_values("dependencies"),
                missing_prerequisites=text_values("missing_prerequisites"),
                tacit_practices=text_values("tacit_practices"),
                assumptions=text_values("assumptions"),
                inferred_relations=text_values("inferred_relations"),
                boundary_conditions=text_values("boundary_conditions"),
                alternatives=text_values("alternatives"),
                changed_condition_examples=text_values("changed_condition_examples"),
                uncertainties=text_values("uncertainties"),
            )
        )
    payload = {
        "schema_version": "decompression-artifact.v1",
        "run_id": run_id,
        "units": [decompression_unit_dict(unit) for unit in units],
    }
    identity_digest = digest_value(payload)
    return DecompressionArtifact(
        artifact_id=stable_id("decompression_artifact", run_id, identity_digest),
        run_id=run_id,
        units=tuple(units),
    )


def decompression_artifact_dict(artifact: DecompressionArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "run_id": artifact.run_id,
        "schema_version": artifact.schema_version,
        "units": [decompression_unit_dict(unit) for unit in artifact.units],
    }


def decompression_unit_dict(unit: DecompressionUnit) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "explanation": unit.explanation,
        "claim_ids": unit.claim_ids,
        "source_citations": tuple(
            {
                "schema_version": citation.schema_version,
                "kind": citation.kind.value,
                "identity": citation.identity,
            }
            for citation in unit.source_citations
        ),
        "concepts_introduced": unit.concepts_introduced,
        "concepts_assumed": unit.concepts_assumed,
        "mechanism_steps": unit.mechanism_steps,
        "dependencies": unit.dependencies,
        "missing_prerequisites": unit.missing_prerequisites,
        "tacit_practices": unit.tacit_practices,
        "assumptions": unit.assumptions,
        "inferred_relations": unit.inferred_relations,
        "boundary_conditions": unit.boundary_conditions,
        "alternatives": unit.alternatives,
        "changed_condition_examples": unit.changed_condition_examples,
        "uncertainties": unit.uncertainties,
    }


def mapping_sequence(value: object, field: str) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    result: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{field} entries must be objects")
        result.append(item)
    return tuple(result)


def string_tuple(value: object, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return tuple(str(item) for item in value)


def parse_source_citations(value: object) -> tuple[SourceCitation, ...]:
    citations = mapping_sequence(value, "source_citations")
    return tuple(
        SourceCitation(
            kind=SourceCitationKind(str(item.get("kind", ""))),
            identity=str(item.get("identity", "")).strip(),
            schema_version=str(item.get("schema_version", "source-citation.v1")),
        )
        for item in citations
    )


def provenance_tuple(value: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
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


def epistemic_status(
    claims: Sequence[ReadingClaim],
    gaps: Sequence[ReadingGap],
) -> EpistemicStatus:
    if any(gap.critical and not gap.resolved for gap in gaps):
        return EpistemicStatus.UNDERDETERMINED
    if not any(claim.decision in ACCEPTED for claim in claims):
        return EpistemicStatus.UNDERDETERMINED
    if any(not gap.resolved for gap in gaps) or any(
        claim.decision in (LedgerDecision.CONTESTED, LedgerDecision.UNDERDETERMINED)
        for claim in claims
    ):
        return EpistemicStatus.PARTIAL
    return EpistemicStatus.SUFFICIENT


def claim_dict(claim: ReadingClaim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "stage": claim.stage.value,
        "anchor_ids": claim.anchor_ids,
        "decision": claim.decision.value,
        "source_claim_ids": claim.source_claim_ids,
        "source_citations": tuple(
            {
                "schema_version": citation.schema_version,
                "kind": citation.kind.value,
                "identity": citation.identity,
            }
            for citation in claim.source_citations
        ),
        "limitations": claim.limitations,
        "provenance": claim.provenance,
    }


def gap_dict(gap: ReadingGap) -> dict[str, Any]:
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


def digest_value(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

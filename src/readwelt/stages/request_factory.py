"""Build and budget final provider requests for one reading stage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from readwelt.domain.documents import SourceDocumentSnapshot
from readwelt.domain.reading import (
    EvidencePacket,
    ReadingClaim,
    ReadingStage,
    StageArtifact,
)
from readwelt.providers.contracts import (
    DEFAULT_TOKEN_COUNTER,
    InputTokenCounter,
    StageRequest,
)
from readwelt.providers.request_budget import settle_stage_request
from readwelt.stage_views import StageView

from .policies import ARTICLE_ONLY, RESPONSE_SCHEMA, STAGE_POLICIES


def build_stage_request(
    *,
    provider_name: str,
    stage: ReadingStage,
    snapshot: SourceDocumentSnapshot,
    evidence: EvidencePacket,
    artifacts: Sequence[StageArtifact],
    upstream_claims: Sequence[ReadingClaim],
    stage_view: StageView | None = None,
    request_provenance: Mapping[str, Any] | None = None,
    hard_serialized_token_budget: int | None = None,
    provider_kind: str | None = None,
    provider_model: str = "host-default",
    token_counter: InputTokenCounter = DEFAULT_TOKEN_COUNTER,
) -> StageRequest:
    external_allowed = stage not in ARTICLE_ONLY
    admitted_external = stage_view.external_evidence if stage_view is not None else ()
    stage_view_digest = stage_view.content_digest if stage_view is not None else None
    admitted_ids = {item.evidence_id for item in admitted_external}
    stage_view_omissions = stage_view.external_evidence_omissions if stage_view is not None else ()
    omission_by_id = {
        item.evidence_id: {
            "schema_version": item.schema_version,
            "evidence_id": item.evidence_id,
            "reason": item.reason,
            "detail": item.detail,
        }
        for item in stage_view_omissions
    }
    for item in evidence.external_evidence:
        if item.evidence_id not in admitted_ids and item.evidence_id not in omission_by_id:
            omission_by_id[item.evidence_id] = {
                "schema_version": "stage-view-external-evidence-omission.v1",
                "evidence_id": item.evidence_id,
                "reason": (
                    "article_only_stage" if not external_allowed else "not_admitted_by_stage_view"
                ),
                "detail": "EvidencePacket material cannot bypass StageView admission",
            }
    packet: dict[str, Any] = {
        "stage_policy": dict(STAGE_POLICIES[stage]),
        "response_policy": {
            "claims": (
                "Return atomic claims with decision, typed source_citations, "
                "limitations, and provenance. Use source_claim_ids for upstream "
                "derivations; anchor_ids and graph_object_ids are legacy aliases. "
                "Cite only presented material. Graph objects locate evidence and "
                "are not conclusions. Runtime may downgrade or reject decisions."
            ),
            "ai_boundary": (
                "Claims are stage conclusions, not source facts. Stage 1 remains "
                "responsible for the main line; Stage 2 remains responsible for "
                "argument structure. Machine candidates are locating hints only."
            ),
            "uncertainty": (
                "Use gaps or qualified/underdetermined decisions when evidence is missing."
            ),
        },
        "snapshot_id": snapshot.snapshot_id,
        "document_id": snapshot.document_id,
        "title": snapshot.title,
        "language": snapshot.language,
        "normalized_text_ref": snapshot.normalized_text_ref,
        "retrieval_queries": list(evidence.retrieval_queries),
        "retrieval_backend": evidence.retrieval_backend,
        "retrieval_hits": [
            {
                "anchor_id": hit.anchor_id,
                "section_id": hit.section_id,
                "lexical_rank": hit.lexical_rank,
                "lexical_score": hit.lexical_score,
                "dense_rank": hit.dense_rank,
                "dense_score": hit.dense_score,
                "fused_score": hit.fused_score,
            }
            for hit in evidence.retrieval_hits
        ],
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
        "external_evidence": [
            {
                "schema_version": item.schema_version,
                "evidence_id": item.evidence_id,
                "stage_view_digest": stage_view_digest,
            }
            for item in admitted_external
        ],
        "external_evidence_omissions": list(omission_by_id.values()),
        "external_evidence_allowed": external_allowed,
        "article_graph_boundary": {
            "object_role": "machine_locating_candidate",
            "may_be_final_stage_conclusion": False,
            "may_be_written_as_source_fact": False,
            "ai_responsibility": (
                "Stage 1 determines mainline; Stage 2 determines argument structure."
            ),
        },
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
                "source_citations": [
                    {
                        "schema_version": citation.schema_version,
                        "kind": citation.kind.value,
                        "identity": citation.identity,
                    }
                    for citation in claim.source_citations
                ],
            }
            for claim in upstream_claims
        ],
    }
    if stage_view is not None:
        packet["stage_view"] = stage_view.to_mapping()
    packet["estimated_evidence_tokens"] = serialized_token_estimate(packet)
    request = StageRequest(
        schema_version="1",
        run_id=evidence.run_id,
        stage=stage.value,
        evidence_packet=packet,
        response_schema=RESPONSE_SCHEMA,
        capabilities=("external_evidence",) if external_allowed else (),
        provenance={
            "provider": provider_name,
            "article_only": not external_allowed,
            **dict(request_provenance or {}),
        },
    )
    if hard_serialized_token_budget is None:
        return request
    return settle_stage_request(
        request,
        hard_serialized_token_budget=hard_serialized_token_budget,
        critical_anchor_ids=(stage_view.anchor_ids if stage_view is not None else ()),
        provider_name=provider_name,
        provider_kind=provider_kind,
        provider_model=provider_model,
        token_counter=token_counter,
    )


def serialized_token_estimate(value: object) -> int:
    """Conservative estimate used before final provider-envelope settlement."""

    return DEFAULT_TOKEN_COUNTER.count_json(value).tokens

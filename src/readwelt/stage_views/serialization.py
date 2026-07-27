"""Bounded provider serialization for persisted StageView artifacts."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from readwelt.article_graph.digest import content_digest
from readwelt.token_budget import DEFAULT_TOKEN_COUNTER

from .models import (
    CoverageOmission,
    StageViewContinuationCursor,
    StageViewCoverageManifest,
)

if TYPE_CHECKING:
    from .models import StageView

_OMISSION_CURSOR_SCHEMA = "stage-view-omission-cursor.v1"
_CONFLICT_CURSOR_SCHEMA = "stage-view-conflict-cursor.v1"
_CAPABILITY_CURSOR_SCHEMA = "stage-view-capability-cursor.v1"
_COMPACT_COVERAGE_SCHEMA = "stage-view-coverage-envelope.v1"


class StageViewBudgetExceeded(ValueError):
    """Carries the measured envelope size for bounded proportional fitting."""

    def __init__(self, estimated_tokens: int, budget: int) -> None:
        super().__init__("complete StageView serialization exceeds hard provider budget")
        self.estimated_tokens = estimated_tokens
        self.budget = budget


def stage_view_mapping(view: StageView) -> dict[str, object]:
    """Return a provider mapping and enforce the complete serialized budget."""

    compact = view.hard_serialized_token_budget is not None
    mapping = _base_mapping(view, compact=compact)
    conflict_page_limit = 16
    capability_page_limit = 8
    if compact:
        mapping["unresolved_conflicts"] = conflict_id_page(
            view.unresolved_conflict_ids,
            limit=conflict_page_limit,
        )
        mapping["missing_capabilities"] = _capability_page(
            view.missing_capabilities,
            limit=capability_page_limit,
        )
    coverage_digest = content_digest(view.coverage) if view.coverage is not None else None
    if view.coverage is not None:
        mapping["coverage"] = (
            _compact_coverage(
                view.coverage,
                page_limit=16,
                manifest_digest=coverage_digest,
            )
            if compact
            else _full_coverage(view.coverage)
        )
    if view.continuation is not None:
        mapping["continuation"] = (
            _compact_continuation(view.continuation)
            if compact
            else _full_continuation(view.continuation)
        )
    if view.blocking_records:
        mapping["blocking_records"] = [
            {
                "source_unit_id": item.source_unit_id,
                "source_range_id": item.source_range_id,
                "source_element_id": item.source_element_id,
                "reason": item.reason,
                "estimated_tokens": item.estimated_tokens,
                "budget": item.budget,
                "detail": item.detail,
            }
            for item in view.blocking_records
        ]
    mapping["hard_serialized_token_budget"] = view.hard_serialized_token_budget
    mapping["budget_scope"] = "complete_stage_view_serialization" if compact else "selected_text"
    mapping["token_counter"] = {
        "counter_id": DEFAULT_TOKEN_COUNTER.counter_id,
        "mode": DEFAULT_TOKEN_COUNTER.mode.value,
        "guarantee": DEFAULT_TOKEN_COUNTER.guarantee,
    }

    budget = view.hard_serialized_token_budget
    if compact and budget is not None:
        estimated = _stabilize_estimate(mapping)
        if estimated > budget:
            # Diagnostic pages are independently recoverable. Drop their inline
            # items in one constant-time settlement instead of re-hashing the
            # full coverage manifest once per removed identity.
            if view.coverage is not None:
                mapping["coverage"] = _compact_coverage(
                    view.coverage,
                    page_limit=0,
                    manifest_digest=coverage_digest,
                )
            mapping["unresolved_conflicts"] = conflict_id_page(
                view.unresolved_conflict_ids,
                limit=0,
            )
            mapping["missing_capabilities"] = _capability_page(
                view.missing_capabilities,
                limit=0,
            )

    estimated = _stabilize_estimate(mapping)
    if budget is not None and estimated > budget:
        raise StageViewBudgetExceeded(estimated, budget)
    return mapping


def coverage_omission_page(
    coverage: StageViewCoverageManifest,
    *,
    cursor: str | None = None,
    limit: int = 64,
    manifest_digest: str | None = None,
) -> dict[str, object]:
    """Resolve one deterministic omission page from the persisted manifest."""

    if limit < 0:
        raise ValueError("coverage omission page limit cannot be negative")
    ordered = _ordered_omissions(coverage)
    settled_digest = manifest_digest or content_digest(coverage)
    offset = _cursor_offset(cursor, settled_digest) if cursor is not None else 0
    if offset > len(ordered):
        raise ValueError("coverage omission cursor offset is out of range")
    page = ordered[offset : offset + limit]
    next_offset = offset + len(page)
    next_cursor = (
        _omission_cursor(settled_digest, next_offset) if next_offset < len(ordered) else None
    )
    critical_ids = _critical_ids(coverage)
    result: dict[str, object] = {
        "schema_version": "stage-view-omission-page.v1",
        "manifest_digest": settled_digest,
        "offset": offset,
        "returned_count": len(page),
        "total_count": len(ordered),
        "items": [
            {
                "identity": item.identity,
                "reason": item.reason,
                "detail": item.detail,
                "object_type": item.object_type,
                "critical": item.identity in critical_ids,
            }
            for item in page
        ],
        "next_cursor": next_cursor,
    }
    return result


def conflict_id_page(
    conflict_ids: tuple[str, ...],
    *,
    cursor: str | None = None,
    limit: int = 64,
) -> dict[str, object]:
    """Resolve a deterministic page from persisted unresolved conflict IDs."""

    return _identity_page(
        conflict_ids,
        cursor=cursor,
        limit=limit,
        cursor_schema=_CONFLICT_CURSOR_SCHEMA,
        page_schema="stage-view-conflict-page.v1",
        item_key="conflict_ids",
    )


def serialized_token_estimate(value: object) -> int:
    return DEFAULT_TOKEN_COUNTER.count_json(value).tokens


def _base_mapping(view: StageView, *, compact: bool) -> dict[str, object]:
    mapping: dict[str, object] = {
        "schema_version": view.schema_version,
        "snapshot_id": view.snapshot_id,
        "stage": view.stage.value,
        "task_intent": view.task_intent,
        "nodes": [
            {
                "node_id": item.node_id,
                "kind": item.kind,
                "epistemic_status": item.epistemic_status,
                "source_unit_ids": list(item.source_unit_ids),
                "confidence": item.confidence,
                "confidence_method": item.confidence_method,
                **({"label": item.label} if not compact or item.label is not None else {}),
                **(
                    {"source_element_ids": list(item.source_element_ids)}
                    if not compact or item.source_element_ids
                    else {}
                ),
                **(
                    {
                        "confidence_lineage": [
                            [
                                source.candidate_id,
                                source.mention_id,
                                source.score,
                                source.method,
                            ]
                            for source in item.confidence_sources
                        ]
                    }
                    if not compact or item.confidence_sources
                    else {}
                ),
                **({"ambiguity": list(item.ambiguity)} if not compact or item.ambiguity else {}),
            }
            for item in view.nodes
        ],
        "edges": [
            {
                "edge_id": item.edge_id,
                "relation": item.relation,
                "source_node_id": item.source_node_id,
                "target_node_id": item.target_node_id,
                "epistemic_status": item.epistemic_status,
                "source_unit_ids": list(item.source_unit_ids),
                "confidence": item.confidence,
                "confidence_method": item.confidence_method,
                **(
                    {"source_element_ids": list(item.source_element_ids)}
                    if not compact or item.source_element_ids
                    else {}
                ),
                **(
                    {
                        "confidence_lineage": [
                            [
                                source.candidate_id,
                                source.mention_id,
                                source.score,
                                source.method,
                            ]
                            for source in item.confidence_sources
                        ]
                    }
                    if not compact or item.confidence_sources
                    else {}
                ),
                **({"ambiguity": list(item.ambiguity)} if not compact or item.ambiguity else {}),
            }
            for item in view.edges
        ],
        "claim_candidates": [
            {
                "claim_id": item.claim_id,
                "evidence_unit_ids": list(item.evidence_unit_ids),
                "confidence": [item.confidence, item.confidence_method],
                "confidence_lineage": [
                    [
                        source.candidate_id,
                        source.mention_id,
                        source.score,
                        source.method,
                    ]
                    for source in item.confidence_sources
                ],
                **(
                    {"evidence_element_ids": list(item.evidence_element_ids)}
                    if item.evidence_element_ids
                    else {}
                ),
                **({"ambiguity": list(item.ambiguity)} if item.ambiguity else {}),
            }
            for item in view.claim_candidates
        ],
        "text_units": [
            {
                "unit_id": item.unit_id,
                "kind": item.kind,
                "anchor_ids": list(item.anchor_ids),
                "ordinal": item.ordinal,
                "selected_text_tokens": item.estimated_tokens,
                **(
                    {
                        "slice_id": item.slice_id,
                        "slice_start": item.slice_start,
                        "slice_end": item.slice_end,
                    }
                    if not compact or item.slice_id is not None
                    else {}
                ),
            }
            for item in view.text_units
        ],
        "source_ranges": [
            {
                "range_id": item.range_id,
                "kind": item.kind,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
                "content_hash": item.content_hash,
                "unit_count": len(item.unit_ids),
                "unit_ids_digest": item.unit_ids_digest,
                **({"reason": item.reason} if not compact or item.reason is not None else {}),
            }
            for item in view.source_ranges
        ],
        "source_elements": [
            {
                "element_id": item.element_id,
                "projection_status": item.projection_status,
                "ordinal": item.ordinal,
                "reading_order": item.reading_order,
                "child_count": item.child_count,
                "child_ids_digest": item.child_ids_digest,
                "structural_relation_count": item.structural_relation_count,
                "structural_relations_digest": item.structural_relations_digest,
                **({"kind": item.kind} if not compact or item.kind is not None else {}),
                **(
                    {"content_layer": item.content_layer}
                    if not compact or item.content_layer is not None
                    else {}
                ),
                **({"page": item.page} if not compact or item.page is not None else {}),
                **(
                    {"bounding_box": item.bounding_box}
                    if not compact or item.bounding_box is not None
                    else {}
                ),
                **(
                    {"native_reference": item.native_reference}
                    if not compact or item.native_reference is not None
                    else {}
                ),
                **(
                    {"raw_payload_ref": item.raw_payload_ref}
                    if not compact or item.raw_payload_ref is not None
                    else {}
                ),
                **(
                    {"parent_element_id": item.parent_element_id}
                    if not compact or item.parent_element_id is not None
                    else {}
                ),
                **(
                    {"previous_element_id": item.previous_element_id}
                    if not compact or item.previous_element_id is not None
                    else {}
                ),
                **(
                    {"next_element_id": item.next_element_id}
                    if not compact or item.next_element_id is not None
                    else {}
                ),
                **(
                    {"heading_trail": list(item.heading_trail)}
                    if not compact or item.heading_trail
                    else {}
                ),
                **({"text": item.text} if not compact or item.text is not None else {}),
                **(
                    {
                        "slice_id": item.slice_id,
                        "slice_start": item.slice_start,
                        "slice_end": item.slice_end,
                    }
                    if not compact or item.slice_id is not None
                    else {}
                ),
                **(
                    {"source_unit_ids": list(item.source_unit_ids)}
                    if not compact or item.source_unit_ids
                    else {}
                ),
                **(
                    {"child_element_ids": list(item.child_element_ids)}
                    if item.child_element_ids
                    else {}
                ),
                **(
                    {
                        "structural_relations": [
                            {"kind": kind, "target_element_id": target_id}
                            for kind, target_id in item.structural_relations
                        ]
                    }
                    if item.structural_relations
                    else {}
                ),
            }
            for item in view.source_elements
        ],
        "upstream_claim_ids": [item.claim_id for item in view.upstream_claims],
        "external_evidence": [
            {
                "schema_version": item.schema_version,
                "evidence_id": item.evidence_id,
                "content": item.content,
                "selection_reason": item.selection_reason,
                "provenance": [list(pair) for pair in item.provenance],
                "stage_policy": item.stage_policy,
            }
            for item in view.external_evidence
        ],
        "external_evidence_omissions": [
            {
                "schema_version": item.schema_version,
                "evidence_id": item.evidence_id,
                "reason": item.reason,
                "detail": item.detail,
            }
            for item in view.external_evidence_omissions
        ],
        "coverage_complete": view.coverage_complete,
        "token_budget": view.token_budget,
        "selected_text_tokens": view.estimated_tokens,
        "locator_backend": view.locator_backend,
        "lineage": {
            "graph_digest": view.graph_digest,
            "source_index_digest": view.source_index_digest,
            "provenance_ledger_digest": view.provenance_ledger_digest,
        },
        "content_digest": view.content_digest,
    }
    if not view.external_evidence:
        mapping.pop("external_evidence")
    if not view.external_evidence_omissions:
        mapping.pop("external_evidence_omissions")
    if view.fallback_backend is not None:
        mapping["fallback_backend"] = view.fallback_backend
    if not compact:
        mapping["unresolved_conflict_ids"] = list(view.unresolved_conflict_ids)
        mapping["missing_capabilities"] = list(view.missing_capabilities)
    return mapping


def _full_coverage(coverage: StageViewCoverageManifest) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": coverage.schema_version,
        "source_unit_ids": list(coverage.source_unit_ids),
        "visited_unit_ids": list(coverage.visited_unit_ids),
        "selected_unit_ids": list(coverage.selected_unit_ids),
        "serialized_identities": list(coverage.serialized_identities),
        "presented_identities": list(coverage.presented_identities),
        "cited_unit_ids": list(coverage.cited_unit_ids),
        "cited_range_ids": list(coverage.cited_range_ids),
        "cited_element_ids": list(coverage.cited_element_ids),
        "critical_unit_ids": list(coverage.critical_unit_ids),
        "critical_range_ids": list(coverage.critical_range_ids),
        "critical_element_ids": list(coverage.critical_element_ids),
        "source_range_ids": list(coverage.source_range_ids),
        "visited_range_ids": list(coverage.visited_range_ids),
        "selected_range_ids": list(coverage.selected_range_ids),
        "presented_range_ids": list(coverage.presented_range_ids),
        "source_element_ids": list(coverage.source_element_ids),
        "visited_element_ids": list(coverage.visited_element_ids),
        "selected_element_ids": list(coverage.selected_element_ids),
        "presented_element_ids": list(coverage.presented_element_ids),
        "completed_unit_ids": list(coverage.completed_unit_ids),
        "completed_range_ids": list(coverage.completed_range_ids),
        "completed_element_ids": list(coverage.completed_element_ids),
        "omitted": [
            {
                "identity": item.identity,
                "reason": item.reason,
                "detail": item.detail,
                "object_type": item.object_type,
            }
            for item in coverage.omitted
        ],
        "source_complete": coverage.source_complete,
        "stage_input_complete": coverage.stage_input_complete,
    }
    return result


def _compact_coverage(
    coverage: StageViewCoverageManifest,
    *,
    page_limit: int,
    manifest_digest: str | None = None,
) -> dict[str, object]:
    omission_counts = Counter(item.reason for item in coverage.omitted)
    presented = set(coverage.presented_identities)
    presented_ranges = set(coverage.presented_range_ids)
    presented_elements = set(coverage.presented_element_ids)
    critical_ids = _critical_ids(coverage)
    critical_omitted = tuple(item for item in coverage.omitted if item.identity in critical_ids)
    settled_digest = manifest_digest or content_digest(coverage)
    page = coverage_omission_page(
        coverage,
        limit=page_limit,
        manifest_digest=settled_digest,
    )
    result: dict[str, object] = {
        "schema_version": _COMPACT_COVERAGE_SCHEMA,
        "persisted_schema_version": coverage.schema_version,
        "manifest_digest": settled_digest,
        "source": {
            "count": len(coverage.source_unit_ids),
            "complete": coverage.source_complete,
        },
        "visited": {
            "count": len(coverage.visited_unit_ids),
        },
        "selected": _identity_summary(coverage.selected_unit_ids),
        "serialized": _identity_summary(coverage.serialized_identities),
        "presented_identities": list(coverage.presented_identities),
        "cited": {
            "count": (
                len(coverage.cited_unit_ids)
                + len(coverage.cited_range_ids)
                + len(coverage.cited_element_ids)
            ),
        },
        "critical": {
            "count": (
                len(coverage.critical_unit_ids)
                + len(coverage.critical_range_ids)
                + len(coverage.critical_element_ids)
            ),
            "presented_count": (
                sum(unit_id in presented for unit_id in coverage.critical_unit_ids)
                + sum(range_id in presented_ranges for range_id in coverage.critical_range_ids)
                + sum(
                    element_id in presented_elements for element_id in coverage.critical_element_ids
                )
            ),
            "omitted_count": len(critical_omitted),
        },
        "omission_counts": dict(sorted(omission_counts.items())),
        "omission_page": page,
        "stage_input_complete": coverage.stage_input_complete,
    }
    if coverage.source_range_ids:
        result["source_ranges"] = {
            "count": len(coverage.source_range_ids),
            "visited_count": len(coverage.visited_range_ids),
            "completed_count": len(coverage.completed_range_ids),
            "selected": _identity_summary(coverage.selected_range_ids),
            "presented_ids": list(coverage.presented_range_ids),
        }
    if coverage.source_element_ids:
        result["source_elements"] = {
            "count": len(coverage.source_element_ids),
            "visited_count": len(coverage.visited_element_ids),
            "completed_count": len(coverage.completed_element_ids),
            "selected": _identity_summary(coverage.selected_element_ids),
            "presented_ids": list(coverage.presented_element_ids),
        }
    return result


def _identity_summary(identities: tuple[str, ...]) -> dict[str, object]:
    result: dict[str, object] = {"count": len(identities)}
    if identities:
        result["digest"] = content_digest(identities)
    return result


def _full_continuation(
    cursor: StageViewContinuationCursor,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": cursor.schema_version,
        "snapshot_id": cursor.snapshot_id,
        "source_plane_schema_version": cursor.source_plane_schema_version,
        "stage": cursor.stage.value,
        "policy_digest": cursor.policy_digest,
        "index_digest": cursor.index_digest,
        "frontier": [
            {"unit_id": item.unit_id, "start_offset": item.start_offset} for item in cursor.frontier
        ],
        "visited_unit_ids": list(cursor.visited_unit_ids),
        "range_frontier": list(cursor.range_frontier),
        "element_frontier": [
            {
                "element_id": item.element_id,
                "start_offset": item.start_offset,
            }
            for item in cursor.element_frontier
        ],
        "visited_range_ids": list(cursor.visited_range_ids),
        "visited_element_ids": list(cursor.visited_element_ids),
        "content_digest": cursor.content_digest,
    }
    return result


def _compact_continuation(
    cursor: StageViewContinuationCursor,
) -> dict[str, object]:
    head = cursor.frontier[:1]
    result: dict[str, object] = {
        "schema_version": "stage-view-cursor-reference.v1",
        "persisted_schema_version": cursor.schema_version,
        "cursor_ref": cursor.content_digest,
        "snapshot_id": cursor.snapshot_id,
        "stage": cursor.stage.value,
        "frontier_head": [
            {"unit_id": item.unit_id, "start_offset": item.start_offset} for item in head
        ],
        "frontier_count": len(cursor.frontier),
        "visited_count": len(cursor.visited_unit_ids),
        "recovery": "readwelt_persisted_stage_view",
    }
    if cursor.range_frontier or cursor.visited_range_ids:
        result.update(
            {
                "range_frontier_count": len(cursor.range_frontier),
                "visited_range_count": len(cursor.visited_range_ids),
            }
        )
    if cursor.element_frontier or cursor.visited_element_ids:
        result.update(
            {
                "element_frontier_count": len(cursor.element_frontier),
                "visited_element_count": len(cursor.visited_element_ids),
            }
        )
    return result


def _ordered_omissions(
    coverage: StageViewCoverageManifest,
) -> tuple[CoverageOmission, ...]:
    critical_ids = _critical_ids(coverage)
    return tuple(item for item in coverage.omitted if item.identity in critical_ids) + tuple(
        item for item in coverage.omitted if item.identity not in critical_ids
    )


def _critical_ids(coverage: StageViewCoverageManifest) -> set[str]:
    return set(
        (
            *coverage.critical_unit_ids,
            *coverage.critical_range_ids,
            *coverage.critical_element_ids,
        )
    )


def _omission_cursor(manifest_digest: str, offset: int) -> str:
    payload = {
        "schema_version": _OMISSION_CURSOR_SCHEMA,
        "manifest_digest": manifest_digest,
        "offset": offset,
    }
    return f"{_OMISSION_CURSOR_SCHEMA}:{offset}:{content_digest(payload)}"


def _capability_page(
    capabilities: tuple[str, ...],
    *,
    cursor: str | None = None,
    limit: int,
) -> dict[str, object]:
    return _identity_page(
        capabilities,
        cursor=cursor,
        limit=limit,
        cursor_schema=_CAPABILITY_CURSOR_SCHEMA,
        page_schema="stage-view-capability-page.v1",
        item_key="capabilities",
    )


def _identity_page(
    identities: tuple[str, ...],
    *,
    cursor: str | None,
    limit: int,
    cursor_schema: str,
    page_schema: str,
    item_key: str,
) -> dict[str, object]:
    if limit < 0:
        raise ValueError("diagnostic page limit cannot be negative")
    manifest_digest = content_digest(identities)
    offset = (
        _diagnostic_cursor_offset(cursor, cursor_schema, manifest_digest)
        if cursor is not None
        else 0
    )
    if offset > len(identities):
        raise ValueError("diagnostic cursor offset is out of range")
    page = identities[offset : offset + limit]
    next_offset = offset + len(page)
    next_cursor = (
        _diagnostic_cursor(cursor_schema, manifest_digest, next_offset)
        if next_offset < len(identities)
        else None
    )
    return {
        "schema_version": page_schema,
        "manifest_digest": manifest_digest,
        "offset": offset,
        "returned_count": len(page),
        "total_count": len(identities),
        item_key: list(page),
        "next_cursor": next_cursor,
    }


def _diagnostic_cursor(
    schema_version: str,
    manifest_digest: str,
    offset: int,
) -> str:
    payload = {
        "schema_version": schema_version,
        "manifest_digest": manifest_digest,
        "offset": offset,
    }
    return f"{schema_version}:{offset}:{content_digest(payload)}"


def _diagnostic_cursor_offset(
    cursor: str,
    expected_schema: str,
    manifest_digest: str,
) -> int:
    try:
        schema_version, raw_offset, digest = cursor.split(":", 2)
        offset = int(raw_offset)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid diagnostic cursor") from error
    payload = {
        "schema_version": schema_version,
        "manifest_digest": manifest_digest,
        "offset": offset,
    }
    if schema_version != expected_schema or digest != content_digest(payload):
        raise ValueError("stale or incompatible diagnostic cursor")
    return offset


def _cursor_offset(cursor: str, manifest_digest: str) -> int:
    try:
        schema_version, raw_offset, digest = cursor.split(":", 2)
        offset = int(raw_offset)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid coverage omission cursor") from error
    payload = {
        "schema_version": schema_version,
        "manifest_digest": manifest_digest,
        "offset": offset,
    }
    if schema_version != _OMISSION_CURSOR_SCHEMA or digest != content_digest(payload):
        raise ValueError("stale or incompatible coverage omission cursor")
    return offset


def _stabilize_estimate(mapping: dict[str, object]) -> int:
    estimate = 0
    for _ in range(8):
        mapping["estimated_serialized_tokens"] = estimate
        next_estimate = serialized_token_estimate(mapping)
        if next_estimate == estimate:
            return estimate
        estimate = next_estimate
    mapping["estimated_serialized_tokens"] = estimate
    return estimate

"""Hard boundary between ArticleGraph locating hints and six-stage conclusions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from readwelt.domain.reading import (
    ReadingClaim,
    SourceCitation,
    SourceCitationKind,
)
from readwelt.stage_views import StageView

_FORBIDDEN_STAGE_CLAIM_FIELDS = frozenset(
    {
        "canonical_object_id",
        "epistemic_status",
        "is_source_fact",
        "object_role",
        "source_fact",
        "write_back",
        "writeback",
    }
)
_RESERVED_STAGE_PROVENANCE_KEYS = frozenset(
    {
        "artifact_role",
        "epistemic_status",
        "is_source_fact",
        "object_role",
        "source_fact",
        "write_back",
        "writeback",
    }
)


def validate_candidate_fields(value: Mapping[str, Any]) -> None:
    forbidden_fields = sorted(_FORBIDDEN_STAGE_CLAIM_FIELDS.intersection(value))
    if forbidden_fields:
        raise ValueError(
            "stage conclusions cannot declare source-fact or ArticleGraph roles: "
            f"{forbidden_fields}"
        )


def settle_stage_provenance(
    raw_provenance: object,
    *,
    provider: str,
    graph_object_ids: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw_provenance, Mapping):
        raise ValueError("claim provenance must be an object")
    reserved = sorted(
        _RESERVED_STAGE_PROVENANCE_KEYS.intersection(str(key) for key in raw_provenance)
    )
    if reserved:
        raise ValueError(f"provider provenance cannot reclassify a stage conclusion: {reserved}")
    values = {str(key): str(item) for key, item in raw_provenance.items()}
    values.setdefault("provider", provider)
    values["artifact_role"] = "stage_conclusion"
    values["source_fact"] = "false"
    if graph_object_ids:
        values["graph_object_ids"] = json.dumps(
            graph_object_ids,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return tuple(sorted(values.items()))


def stage_view_graph_object_ids(stage_view: StageView | None) -> frozenset[str]:
    if stage_view is None:
        return frozenset()
    return frozenset(
        (
            *(node.node_id for node in stage_view.nodes),
            *(edge.edge_id for edge in stage_view.edges),
            *(claim.claim_id for claim in stage_view.claim_candidates),
        )
    )


def stage_view_source_citations(
    stage_view: StageView | None,
    *,
    presented_anchor_ids: frozenset[str],
) -> frozenset[SourceCitation]:
    """Return only typed identities visible in the settled provider request."""

    citations = {
        SourceCitation(SourceCitationKind.ANCHOR, identity) for identity in presented_anchor_ids
    }
    if stage_view is None:
        return frozenset(citations)
    citations.update(
        SourceCitation(SourceCitationKind.ANCHOR, anchor_id)
        for unit in stage_view.text_units
        for anchor_id in unit.anchor_ids
    )
    citations.update(
        SourceCitation(SourceCitationKind.UNIT, unit.unit_id) for unit in stage_view.text_units
    )
    citations.update(
        SourceCitation(SourceCitationKind.RANGE, source_range.range_id)
        for source_range in stage_view.source_ranges
    )
    citations.update(
        SourceCitation(SourceCitationKind.ELEMENT, element.element_id)
        for element in stage_view.source_elements
    )
    citations.update(
        SourceCitation(SourceCitationKind.GRAPH_OBJECT, identity)
        for identity in stage_view_graph_object_ids(stage_view)
    )
    return frozenset(citations)


def validate_stage_claim_boundary(claim: ReadingClaim) -> None:
    provenance = dict(claim.provenance)
    artifact_role = provenance.get("artifact_role")
    if artifact_role is not None and artifact_role != "stage_conclusion":
        raise ValueError("stage claims cannot be reclassified as ArticleGraph or source objects")
    source_fact = provenance.get("source_fact")
    if source_fact is not None and source_fact.casefold() != "false":
        raise ValueError("stage claims cannot be reclassified as source facts")

from __future__ import annotations

import pytest

from readwelt.article_graph import Canonicalizer
from readwelt.article_graph.models import (
    ArticleNode,
    EpistemicStatus,
    GraphObjectRole,
)


def _extraction() -> dict[str, object]:
    return {
        "extraction_id": "ai-boundary",
        "snapshot_id": "snapshot-1",
        "candidate_nodes": (
            {
                "candidate_id": "entity-a",
                "kind": "entity",
                "label": "A",
                "confidence": 1.0,
                "source_unit_ids": ("unit-1",),
                "epistemic_status": "explicit",
            },
            {
                "candidate_id": "evidence-a",
                "kind": "evidence",
                "text": "Evidence for A",
                "confidence": 1.0,
                "source_unit_ids": ("unit-1",),
                "epistemic_status": "semantic_inference",
            },
            {
                "candidate_id": "claim-a",
                "kind": "claim",
                "text": "A is supported",
                "confidence": 0.9,
                "source_unit_ids": ("unit-1",),
                "epistemic_status": "semantic_inference",
            },
        ),
        "candidate_edges": (
            {
                "candidate_id": "supports-a",
                "relation": "support",
                "source_candidate_id": "evidence-a",
                "target_candidate_id": "claim-a",
                "confidence": 0.9,
                "source_unit_ids": ("unit-1",),
                "epistemic_status": "semantic_inference",
            },
        ),
    }


def test_semantic_graph_objects_are_explicit_machine_locating_candidates() -> None:
    graph = Canonicalizer().canonicalize((_extraction(),)).graph

    assert graph.claims
    assert graph.edges
    assert all(
        item.object_role is GraphObjectRole.MACHINE_LOCATING_CANDIDATE
        for collection in (graph.mentions, graph.nodes, graph.edges, graph.claims)
        for item in collection
    )
    assert all(node.source_unit_ids for node in graph.nodes)
    assert all(edge.source_unit_ids for edge in graph.edges)
    assert all(claim.evidence_unit_ids for claim in graph.claims)


def test_article_graph_object_cannot_be_reclassified_as_a_source_fact() -> None:
    with pytest.raises(ValueError, match="machine locating candidates"):
        ArticleNode(
            node_id="node-1",
            kind="entity",
            label="A",
            epistemic_status=EpistemicStatus.CANONICALIZED,
            mention_ids=("mention-1",),
            source_unit_ids=("unit-1",),
            object_role="source_fact",  # type: ignore[arg-type]
        )


def test_semantic_object_without_source_grounding_is_rejected() -> None:
    with pytest.raises(ValueError, match="grounded locating candidates"):
        ArticleNode(
            node_id="node-1",
            kind="claim",
            label="A",
            epistemic_status=EpistemicStatus.CANONICALIZED,
            mention_ids=("mention-1",),
            source_unit_ids=(),
        )

"""Rebuildable bidirectional projection between knowledge and source units."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from readwelt.article_graph.digest import content_digest
from readwelt.article_graph.models import ArticleGraph, MergeReport

from .ledger import ProvenanceLedger

SOURCE_INDEX_SCHEMA_VERSION = "source-index.v1"


@dataclass(frozen=True, slots=True)
class UnitKnowledge:
    node_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceIndex:
    schema_version: str
    graph_digest: str
    ledger_head_digest: str
    node_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    edge_to_units: tuple[tuple[str, tuple[str, ...]], ...]
    claim_to_evidence_units: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_nodes: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_edges: tuple[tuple[str, tuple[str, ...]], ...]
    unit_to_claims: tuple[tuple[str, tuple[str, ...]], ...]
    content_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_INDEX_SCHEMA_VERSION:
            raise ValueError(f"unsupported source index schema: {self.schema_version}")
        if _reverse(dict(self.node_to_units)) != self.unit_to_nodes:
            raise ValueError("node source index directions disagree")
        if _reverse(dict(self.edge_to_units)) != self.unit_to_edges:
            raise ValueError("edge source index directions disagree")
        if _reverse(dict(self.claim_to_evidence_units)) != self.unit_to_claims:
            raise ValueError("claim source index directions disagree")
        payload = {
            "schema_version": self.schema_version,
            "graph_digest": self.graph_digest,
            "ledger_head_digest": self.ledger_head_digest,
            "node_to_units": self.node_to_units,
            "edge_to_units": self.edge_to_units,
            "claim_to_evidence_units": self.claim_to_evidence_units,
            "unit_to_nodes": self.unit_to_nodes,
            "unit_to_edges": self.unit_to_edges,
            "unit_to_claims": self.unit_to_claims,
        }
        if self.content_digest != content_digest(payload):
            raise ValueError("source index content digest mismatch")

    @classmethod
    def rebuild(
        cls,
        graph: ArticleGraph,
        ledger: ProvenanceLedger | None = None,
        merge_report: MergeReport | None = None,
    ) -> SourceIndex:
        """Rebuild solely from canonical references, lineage, and ledger events."""

        node_units = {node.node_id: set(node.source_unit_ids) for node in graph.nodes}
        edge_units = {edge.edge_id: set(edge.source_unit_ids) for edge in graph.edges}
        claim_units = {claim.claim_id: set(claim.evidence_unit_ids) for claim in graph.claims}
        # Merge decisions explain a projection; they are not an independent
        # grounding authority. Separate/deferred objects must retain their own
        # source sets rather than inheriting a group's evidence refs.
        del merge_report

        if ledger is not None:
            verification = ledger.verify_chain()
            if not verification.valid:
                raise ValueError("cannot project SourceIndex from an invalid ledger")
            # v1 treats the graph and merge lineage as the source mapping facts.
            # Ledger events prove how those facts were produced but never expand
            # grounding: projection/synthesis outputs must not be able to inject
            # new source relationships.

        frozen_nodes = _freeze_forward(node_units)
        frozen_edges = _freeze_forward(edge_units)
        frozen_claims = _freeze_forward(claim_units)
        reverse_nodes = _reverse(node_units)
        reverse_edges = _reverse(edge_units)
        reverse_claims = _reverse(claim_units)
        payload = {
            "schema_version": SOURCE_INDEX_SCHEMA_VERSION,
            "graph_digest": graph.content_digest,
            "ledger_head_digest": ledger.head_digest if ledger is not None else "",
            "node_to_units": frozen_nodes,
            "edge_to_units": frozen_edges,
            "claim_to_evidence_units": frozen_claims,
            "unit_to_nodes": reverse_nodes,
            "unit_to_edges": reverse_edges,
            "unit_to_claims": reverse_claims,
        }
        return cls(
            schema_version=SOURCE_INDEX_SCHEMA_VERSION,
            graph_digest=graph.content_digest,
            ledger_head_digest=ledger.head_digest if ledger is not None else "",
            node_to_units=frozen_nodes,
            edge_to_units=frozen_edges,
            claim_to_evidence_units=frozen_claims,
            unit_to_nodes=reverse_nodes,
            unit_to_edges=reverse_edges,
            unit_to_claims=reverse_claims,
            content_digest=content_digest(payload),
        )

    def units_for_node(self, node_id: str) -> tuple[str, ...]:
        return dict(self.node_to_units).get(node_id, ())

    def units_for_edge(self, edge_id: str) -> tuple[str, ...]:
        return dict(self.edge_to_units).get(edge_id, ())

    def evidence_units_for_claim(self, claim_id: str) -> tuple[str, ...]:
        return dict(self.claim_to_evidence_units).get(claim_id, ())

    def knowledge_for_unit(self, unit_id: str) -> UnitKnowledge:
        return UnitKnowledge(
            node_ids=dict(self.unit_to_nodes).get(unit_id, ()),
            edge_ids=dict(self.unit_to_edges).get(unit_id, ()),
            claim_ids=dict(self.unit_to_claims).get(unit_id, ()),
        )


def _freeze_forward(
    mapping: Mapping[str, set[str]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (object_id, tuple(sorted(unit_ids))) for object_id, unit_ids in sorted(mapping.items())
    )


def _reverse(
    mapping: Mapping[str, set[str] | tuple[str, ...]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    reverse: dict[str, set[str]] = {}
    for object_id, unit_ids in mapping.items():
        for unit_id in unit_ids:
            reverse.setdefault(unit_id, set()).add(object_id)
    return tuple(
        (unit_id, tuple(sorted(object_ids))) for unit_id, object_ids in sorted(reverse.items())
    )

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from readwelt.article_graph import ArticleGraphBuilder, ArticleGraphBuildResult
from readwelt.article_graph.digest import content_digest
from readwelt.provenance import (
    ProvenanceLedger,
    SourceCandidateKind,
    SourceCandidateMatch,
    SourceIndex,
    SourceLookup,
)
from readwelt.runner.snapshot import SectionStructure, snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


def _build(tmp_path: Path) -> ArticleGraphBuildResult:
    text = "Cache policy\n\nCache entries require revision keys."
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    snapshot = snapshot_from_text(
        source=tmp_path / "source.txt",
        text=text,
        source_kind="text/plain",
        artifacts=ArtifactStore(layout),
        adapter_finding="test",
        structure=(
            SectionStructure(
                exact_text="Cache policy",
                kind="heading",
                child_element_ids=("body-1",),
                heading_trail=("Cache policy",),
                element_id="heading-1",
                reading_order=0,
                page=1,
            ),
            SectionStructure(
                exact_text="Cache entries require revision keys.",
                kind="paragraph",
                parent_element_id="heading-1",
                heading_trail=("Cache policy",),
                element_id="body-1",
                reading_order=1,
                page=2,
            ),
        ),
    )
    return ArticleGraphBuilder().build(snapshot, text)


def test_rebuild_adds_source_first_projections_without_losing_knowledge(
    tmp_path: Path,
) -> None:
    build = _build(tmp_path)
    index = build.source_index
    heading, body = build.unitization.units
    gap = next(item for item in build.unitization.source_ranges if item.kind == "gap")

    assert index.validate_closure().valid
    assert index.source_unit_ids == (heading.unit_id, body.unit_id)
    assert index.unit_at_ordinal(0) == heading.unit_id
    assert index.unit_at_ordinal(1) == body.unit_id
    assert index.ordered_units() == (heading.unit_id, body.unit_id)
    assert index.ordered_units(1, 2) == (body.unit_id,)
    assert index.range_at_offset(gap.start_offset) == gap.range_id
    assert index.locate_offsets(gap.start_offset, gap.end_offset) == SourceLookup(
        range_ids=(gap.range_id,)
    )

    heading_section = heading.source_references[0].section_id
    assert heading_section is not None
    assert index.units_for_section(heading_section) == (heading.unit_id,)
    assert index.units_for_heading("Cache policy") == (
        heading.unit_id,
        body.unit_id,
    )
    assert index.units_for_element("heading-1") == (heading.unit_id,)
    assert index.units_for_element("body-1") == (body.unit_id,)
    assert index.locate_page(1).unit_ids == (heading.unit_id,)
    assert index.locate_page(2).element_ids == ("body-1",)
    assert index.locate_lexical("revision").unit_ids == (body.unit_id,)

    assert index.neighborhood(heading.unit_id).next_unit_id == body.unit_id
    assert index.neighborhood(heading.unit_id).child_unit_ids == (body.unit_id,)
    assert index.neighborhood(body.unit_id).parent_unit_id == heading.unit_id
    assert index.neighborhood(body.unit_id).previous_unit_id == heading.unit_id
    assert index.parent_element("body-1") == "heading-1"
    assert index.child_elements("heading-1") == ("body-1",)
    assert index.next_element("heading-1") == "body-1"
    assert index.previous_element("body-1") == "heading-1"

    for node in build.graph.nodes:
        assert index.units_for_node(node.node_id) == tuple(sorted(node.source_unit_ids))
        for unit_id in node.source_unit_ids:
            assert node.node_id in index.knowledge_for_unit(unit_id).node_ids


def test_source_first_lookup_survives_empty_semantic_graph(tmp_path: Path) -> None:
    build = _build(tmp_path)
    empty_graph = replace(
        build.graph,
        mentions=(),
        nodes=(),
        edges=(),
        claims=(),
    )
    index = SourceIndex.rebuild(empty_graph, build.unitization)

    assert index.ordered_units() == tuple(unit.unit_id for unit in build.unitization.units)
    assert index.locate_lexical("cache").unit_ids == tuple(
        unit.unit_id for unit in build.unitization.units
    )
    assert index.locate_offsets(0, build.unitization.coverage.source_length).range_ids
    assert index.validate_closure().valid


def test_exact_candidates_preserve_seed_order_and_source_ownership(tmp_path: Path) -> None:
    build = _build(tmp_path)
    unit_id = build.unitization.units[0].unit_id
    node = build.graph.nodes[0]
    edge = build.graph.edges[0]
    claim = build.graph.claims[0]

    candidates = build.source_index.retrieve_exact_candidates(
        (claim.claim_id, unit_id, edge.edge_id, node.node_id, "unknown", claim.claim_id)
    )

    assert tuple(item.object_id for item in candidates) == (
        claim.claim_id,
        unit_id,
        edge.edge_id,
        node.node_id,
    )
    assert tuple(item.object_kind for item in candidates) == (
        SourceCandidateKind.CLAIM,
        SourceCandidateKind.SOURCE_UNIT,
        SourceCandidateKind.RELATION,
        SourceCandidateKind.NODE,
    )
    assert all(item.match_kind is SourceCandidateMatch.EXACT_ID for item in candidates)
    assert all(item.source_unit_ids for item in candidates)


def test_lexical_candidates_cover_source_and_grounded_knowledge_deterministically(
    tmp_path: Path,
) -> None:
    build = _build(tmp_path)

    first = build.source_index.retrieve_lexical_candidates("revision cache")
    second = build.source_index.retrieve_lexical_candidates("revision cache")

    assert first == second
    assert first
    assert {candidate.object_kind for candidate in first}.issuperset(
        {
            SourceCandidateKind.SOURCE_UNIT,
            SourceCandidateKind.NODE,
            SourceCandidateKind.RELATION,
            SourceCandidateKind.CLAIM,
        }
    )
    assert all(candidate.match_kind is SourceCandidateMatch.LEXICAL for candidate in first)
    assert all(candidate.source_unit_ids for candidate in first)
    assert build.source_index.retrieve_lexical_candidates("not-present") == ()


def test_unknown_queries_and_grounding_fail_empty_with_diagnostic(
    tmp_path: Path,
) -> None:
    build = _build(tmp_path)
    ledger = ProvenanceLedger.from_artifact(build.provenance_ledger)
    node = build.graph.nodes[0]
    graph = replace(
        build.graph,
        nodes=(replace(node, source_unit_ids=("unit:unknown",)),),
        edges=(),
        claims=(),
    )

    index = SourceIndex.rebuild(graph, build.unitization, ledger)

    assert index.units_for_node(node.node_id) == ()
    assert index.units_for_range("range:unknown") == ()
    assert index.units_for_section("section:unknown") == ()
    assert index.units_for_element("element:unknown") == ()
    assert index.unit_at_ordinal(999) is None
    assert index.range_at_offset(-1) is None
    assert index.locate_offsets(-1, 2) == SourceLookup()
    assert index.locate_page(0) == SourceLookup()
    assert index.locate_lexical("not-present") == SourceLookup()
    assert index.retrieve_exact_candidates((node.node_id,)) == ()
    assert index.neighborhood("unit:unknown").parent_unit_id is None
    assert any(
        diagnostic.code == "unknown_node_source_unit" and diagnostic.identity == "unit:unknown"
        for diagnostic in index.diagnostics
    )
    assert index.validate_closure().valid


def test_source_index_digest_is_deterministic(tmp_path: Path) -> None:
    build = _build(tmp_path)
    ledger = ProvenanceLedger.from_artifact(build.provenance_ledger)

    first = SourceIndex.rebuild(
        build.graph,
        build.unitization,
        ledger,
        build.merge_report,
    )
    second = SourceIndex.rebuild(
        build.graph,
        build.unitization,
        ledger,
        build.merge_report,
    )

    assert first == second
    assert first.content_digest == second.content_digest


@pytest.mark.parametrize(
    "projection",
    (
        "section",
        "heading",
        "page_unit",
        "page_element",
        "lexical_range",
        "lexical_element",
        "range_reverse",
        "element_unit",
        "knowledge_unit_reverse",
        "knowledge_element_reverse",
        "unit_hierarchy",
        "unit_neighbor",
        "element_hierarchy",
        "element_neighbor",
        "ordinal",
        "range_interval",
    ),
)
def test_every_source_index_projection_rejects_corruption(
    tmp_path: Path,
    projection: str,
) -> None:
    index = _build(tmp_path).source_index
    updates = _corruption(index, projection)
    values = {
        item.name: getattr(index, item.name)
        for item in fields(index)
        if item.name != "content_digest"
    }
    values.update(updates)

    with pytest.raises(ValueError, match="source index closure failed|directions disagree"):
        SourceIndex(
            **values,
            content_digest=content_digest(values),
        )


def _corruption(index: SourceIndex, projection: str) -> dict[str, object]:
    unit_id = index.source_unit_ids[0]
    element_id = index.source_element_ids[0]
    range_id = index.source_range_ids[0]
    node_id = index.canonical_node_ids[0]
    corruptions: dict[str, dict[str, object]] = {
        "section": {
            "section_to_units": (("section:unknown", ("unit:unknown",)),),
        },
        "heading": {
            "heading_to_units": (("heading", ("unit:unknown",)),),
        },
        "page_unit": {
            "page_to_units": ((0, (unit_id,)),),
        },
        "page_element": {
            "page_to_elements": ((1, ("element:unknown",)),),
        },
        "lexical_range": {
            "lexical_to_ranges": (("token", ("range:unknown",)),),
        },
        "lexical_element": {
            "lexical_to_elements": (("token", ("element:unknown",)),),
        },
        "range_reverse": {
            "unit_to_ranges": ((unit_id, ("range:unknown",)),),
        },
        "element_unit": {
            "element_to_units": ((element_id, ("unit:unknown",)),),
        },
        "knowledge_unit_reverse": {
            "unit_to_nodes": ((unit_id, ("node:unknown",)),),
        },
        "knowledge_element_reverse": {
            "element_to_nodes": ((element_id, ("node:unknown",)),),
        },
        "unit_hierarchy": {
            "parent_to_children": ((unit_id, ("unit:unknown",)),),
        },
        "unit_neighbor": {
            "unit_to_next": ((unit_id, "unit:unknown"),),
        },
        "element_hierarchy": {
            "parent_to_child_elements": ((element_id, ("element:unknown",)),),
        },
        "element_neighbor": {
            "element_to_next": ((element_id, "element:unknown"),),
        },
        "ordinal": {
            "ordinal_to_unit": ((0, unit_id), (0, "unit:unknown")),
        },
        "range_interval": {
            "range_intervals": ((0, 1, range_id), (1, 2, "range:unknown")),
        },
    }
    assert node_id
    return corruptions[projection]

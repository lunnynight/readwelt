from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from itertools import pairwise

import pytest

from readwelt.article_graph import (
    ArticleGraphBuilder,
    Canonicalizer,
    EpistemicStatus,
)
from readwelt.domain import (
    DocumentSection,
    ReadingStage,
    SourceDocumentSnapshot,
    SpanAnchor,
    stable_id,
)
from readwelt.extraction import ExtractionEpistemicStatus
from readwelt.provenance import ProvenanceLedger
from readwelt.stage_views import StageContext, StageViewProjector


def _snapshot(text: str) -> SourceDocumentSnapshot:
    snapshot_id = stable_id("snapshot", text)
    document_id = stable_id("document", text)
    paragraphs = tuple(part for part in text.split("\n\n") if part)
    sections = []
    cursor = 0
    for ordinal, paragraph in enumerate(paragraphs):
        start = text.index(paragraph, cursor)
        end = start + len(paragraph)
        cursor = end
        section_id = stable_id("section", snapshot_id, str(ordinal))
        sections.append(
            DocumentSection(
                section_id=section_id,
                title=f"第{ordinal + 1}节",
                start_offset=start,
                end_offset=end,
                anchor=SpanAnchor.create(
                    snapshot_id=snapshot_id,
                    section_id=section_id,
                    text=text,
                    start_offset=start,
                    end_offset=end,
                ),
            )
        )
    return SourceDocumentSnapshot(
        snapshot_id=snapshot_id,
        document_id=document_id,
        schema_version="1",
        source_kind="text/plain",
        source_locator="article.txt",
        content_digest=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        captured_at=datetime(2026, 7, 26, tzinfo=UTC),
        language="zh",
        normalized_text_ref="objects/article/body",
        sections=tuple(sections),
        title="测试文章",
    )


def _build(text: str = "主张成立。\n\n主张存在限制。"):
    return ArticleGraphBuilder().build(_snapshot(text), text)


def test_deep_build_is_deterministic_for_identical_revision_and_policy() -> None:
    text = "主张成立。\n\n主张存在限制。"
    snapshot = _snapshot(text)
    builder = ArticleGraphBuilder()

    first = builder.build(snapshot, text)
    second = builder.build(snapshot, text)

    assert first == second
    assert first.schema_version == "article-graph-build.v2"
    assert first.graph.schema_version == "article-graph.v4"
    assert first.source_index.schema_version == "source-index.v3"
    assert first.content_digest == second.content_digest
    assert first.unitization.content_digest == second.unitization.content_digest
    assert tuple(item.content_digest for item in first.extractions) == tuple(
        item.content_digest for item in second.extractions
    )
    assert first.graph.content_digest == second.graph.content_digest
    assert first.merge_report.content_digest == second.merge_report.content_digest
    assert first.provenance_ledger.content_digest == second.provenance_ledger.content_digest
    assert first.source_index.content_digest == second.source_index.content_digest
    assert first.capability_report.content_digest == second.capability_report.content_digest


def test_unitization_accounts_for_every_non_whitespace_source_character() -> None:
    text = "第一段主张。\n\n第二段限制。"
    build = _build(text)
    coverage = build.unitization.coverage

    covered_offsets = {
        offset
        for unit in build.unitization.units
        for reference in unit.source_references
        if reference.start_offset is not None and reference.end_offset is not None
        for offset in range(reference.start_offset, reference.end_offset)
    }

    assert coverage.source_length == len(text)
    assert coverage.has_complete_text_coverage
    assert not coverage.uncovered
    assert {offset for offset, character in enumerate(text) if not character.isspace()}.issubset(
        covered_offsets
    )
    assert all(unit.revision_id == build.snapshot_id for unit in build.unitization.units)
    assert all(
        reference.exact_text == text[reference.start_offset : reference.end_offset]
        for unit in build.unitization.units
        for reference in unit.source_references
        if reference.start_offset is not None and reference.end_offset is not None
    )


def test_raw_extractions_are_grounded_and_preserved_before_canonicalization() -> None:
    build = _build()
    unit_ids = tuple(unit.unit_id for unit in build.unitization.units)

    assert {item.backend.backend_id for item in build.extractions} == {
        "readwelt.linguistic.regex",
        "readwelt.semantic.explicit-unit",
    }
    assert all(item.input_unit_ids == unit_ids for item in build.extractions)
    assert all(item.coverage.complete for item in build.extractions)
    assert all(item.content_digest.startswith("sha256:") for item in build.extractions)

    raw_candidates = tuple(
        candidate
        for extraction in build.extractions
        for candidate in (*extraction.candidate_nodes, *extraction.candidate_edges)
    )
    assert raw_candidates
    assert all(candidate.source_unit_ids for candidate in raw_candidates)
    assert all(
        candidate_id in {mention.candidate_id for mention in build.graph.mentions}
        for candidate_id in (
            candidate.candidate_id
            for extraction in build.extractions
            for candidate in extraction.candidate_nodes
        )
    )


def test_provenance_chain_and_source_index_close_in_both_directions() -> None:
    build = _build()
    ledger = ProvenanceLedger.from_artifact(build.provenance_ledger)
    verification = ledger.verify_chain()

    assert verification.valid
    assert verification.event_count == len(build.provenance_ledger.events)
    assert verification.head_digest == build.provenance_ledger.head_digest
    assert tuple(event.sequence for event in ledger.events) == tuple(range(len(ledger.events)))
    assert all(
        event.previous_digest == previous.digest for previous, event in pairwise(ledger.events)
    )
    known_unit_ids = {unit.unit_id for unit in build.unitization.units}

    for node in build.graph.nodes:
        units = build.source_index.units_for_node(node.node_id)
        assert set(node.source_unit_ids).issubset(units)
        assert set(units).issubset(known_unit_ids)
        assert all(
            node.node_id in build.source_index.knowledge_for_unit(unit_id).node_ids
            for unit_id in units
        )
    for edge in build.graph.edges:
        units = build.source_index.units_for_edge(edge.edge_id)
        assert set(edge.source_unit_ids).issubset(units)
        assert set(units).issubset(known_unit_ids)
        assert all(
            edge.edge_id in build.source_index.knowledge_for_unit(unit_id).edge_ids
            for unit_id in units
        )
    for claim in build.graph.claims:
        units = build.source_index.evidence_units_for_claim(claim.claim_id)
        assert set(claim.evidence_unit_ids).issubset(units)
        assert set(units).issubset(known_unit_ids)
        assert all(
            claim.claim_id in build.source_index.knowledge_for_unit(unit_id).claim_ids
            for unit_id in units
        )


def test_epistemic_status_separates_source_mentions_from_canonical_objects() -> None:
    build = _build()
    candidates = {
        candidate.candidate_id: candidate
        for extraction in build.extractions
        for candidate in extraction.candidate_nodes
    }

    assert {candidate.epistemic_status for candidate in candidates.values()} == {
        ExtractionEpistemicStatus.EXPLICIT,
        ExtractionEpistemicStatus.LINGUISTIC_INFERENCE,
    }
    assert all(
        mention.epistemic_status.value == candidates[mention.candidate_id].epistemic_status.value
        for mention in build.graph.mentions
    )
    assert all(node.epistemic_status is EpistemicStatus.CANONICALIZED for node in build.graph.nodes)
    assert all(
        claim.epistemic_status is EpistemicStatus.CANONICALIZED for claim in build.graph.claims
    )
    assert {
        EpistemicStatus.INTERNAL_DERIVED,
        EpistemicStatus.EXTERNAL,
        EpistemicStatus.SYNTHESIZED,
    }.isdisjoint({item.epistemic_status for item in build.graph.mentions})


def test_stage_view_carries_explicit_build_lineage_and_grounded_selections() -> None:
    build = _build()
    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="extract the article mainline",
            token_budget=128,
        ),
    )
    mapping = view.to_mapping()

    assert mapping["lineage"] == {
        "graph_digest": build.graph.content_digest,
        "source_index_digest": build.source_index.content_digest,
        "provenance_ledger_digest": build.provenance_ledger.content_digest,
    }
    assert view.text_units
    assert view.estimated_tokens <= view.token_budget
    assert {reason.object_id for reason in view.selection_reasons}.issuperset(
        {unit.unit_id for unit in view.text_units}
    )
    assert all(
        set(node.source_unit_ids).issubset(build.source_index.units_for_node(node.node_id))
        for node in view.nodes
    )


def test_stage_view_only_selects_units_from_admitted_evidence_anchors() -> None:
    build = _build()
    admitted = next(
        reference.anchor_id
        for unit in build.unitization.units
        for reference in unit.source_references
        if reference.anchor_id is not None
    )

    view = StageViewProjector().project(
        build,
        StageContext(
            stage=ReadingStage.MAINLINE,
            task_intent="extract only admitted evidence",
            token_budget=128,
            allowed_anchor_ids=(admitted,),
        ),
    )

    assert view.text_units
    assert set(view.anchor_ids) == {admitted}


def test_build_rejects_normalized_text_that_does_not_match_the_snapshot() -> None:
    snapshot = _snapshot("主张成立。")

    with pytest.raises(ValueError, match="normalized text digest mismatch"):
        ArticleGraphBuilder().build(snapshot, "另一段文本。")


def test_mapping_edge_requires_explicit_epistemic_status() -> None:
    extraction = {
        "extraction_id": "mapping-edge",
        "snapshot_id": "snapshot-1",
        "candidate_nodes": (
            {
                "candidate_id": "n1",
                "kind": "entity",
                "label": "A",
                "confidence": 1.0,
                "source_unit_ids": ("u1",),
                "epistemic_status": "explicit",
            },
            {
                "candidate_id": "n2",
                "kind": "entity",
                "label": "B",
                "confidence": 1.0,
                "source_unit_ids": ("u1",),
                "epistemic_status": "explicit",
            },
        ),
        "candidate_edges": (
            {
                "candidate_id": "e1",
                "relation": "supports",
                "source_candidate_id": "n1",
                "target_candidate_id": "n2",
                "confidence": 1.0,
                "source_unit_ids": ("u1",),
            },
        ),
    }

    with pytest.raises(ValueError, match="epistemic_status"):
        Canonicalizer().canonicalize((extraction,))

"""Budgeted, section-aware evidence packet assembly."""

from __future__ import annotations

from readwelt.semantic.lexical import BM25Index
from readwelt.semantic.models import OmittedEvidence, SemanticAtlas, SemanticEvidencePacket
from readwelt.semantic.tokenization import tokenize


def build_evidence_packet(
    atlas: SemanticAtlas,
    purpose: str,
    token_budget: int,
) -> SemanticEvidencePacket:
    if token_budget < 0:
        raise ValueError("token_budget cannot be negative")
    ordered = _section_balanced_ranking(atlas, purpose)
    selected, omitted, consumed = _apply_budget(atlas, ordered, token_budget)
    anchors = tuple(atlas.segments[ordinal].anchor for ordinal in selected)
    covered_sections = tuple(dict.fromkeys(anchor.section_id for anchor in anchors))
    all_sections = tuple(section_id for section_id, _ in atlas.coverage.section_anchor_ids)
    omitted_sections = tuple(
        section_id for section_id in all_sections if section_id not in covered_sections
    )
    return SemanticEvidencePacket(
        schema_version="1",
        snapshot_id=atlas.snapshot_id,
        purpose=purpose,
        anchors=anchors,
        retrieval_queries=(purpose,) if purpose else (),
        omitted=omitted,
        covered_section_ids=covered_sections,
        omitted_section_ids=omitted_sections,
        token_budget=token_budget,
        estimated_tokens=consumed,
        coverage_complete=(
            not omitted
            and atlas.coverage.full_source_covered
            and len(anchors) == len(atlas.segments)
        ),
    )


def _section_balanced_ranking(atlas: SemanticAtlas, purpose: str) -> tuple[int, ...]:
    index = BM25Index(tuple(segment.tokens for segment in atlas.segments))
    scores = dict(index.rank(tokenize(purpose)))
    # One round-robin queue per source section prevents a long section monopolising the packet.
    section_order: list[str] = []
    section_candidates: dict[str, list[int]] = {}
    for ordinal, segment in enumerate(atlas.segments):
        section_id = segment.anchor.section_id
        if section_id not in section_candidates:
            section_order.append(section_id)
            section_candidates[section_id] = []
        section_candidates[section_id].append(ordinal)
    for candidates in section_candidates.values():
        candidates.sort(key=lambda ordinal: (-scores[ordinal], ordinal))
    orientation_ids = set(atlas.coverage.orientation_anchor_ids)
    orientation_ordinals = [
        ordinal
        for ordinal, segment in enumerate(atlas.segments)
        if segment.anchor.anchor_id in orientation_ids
    ]
    orientation_ordinals.sort(key=lambda ordinal: (-scores[ordinal], ordinal))
    orientation_ordinal_set = set(orientation_ordinals)
    for candidates in section_candidates.values():
        candidates[:] = [
            ordinal for ordinal in candidates if ordinal not in orientation_ordinal_set
        ]
    ordered: list[int] = list(orientation_ordinals)
    while any(section_candidates.values()):
        active = [section_id for section_id in section_order if section_candidates[section_id]]
        active.sort(
            key=lambda section_id: (
                -scores[section_candidates[section_id][0]],
                section_order.index(section_id),
            )
        )
        for section_id in active:
            ordered.append(section_candidates[section_id].pop(0))
    return tuple(ordered)


def _apply_budget(
    atlas: SemanticAtlas,
    ordered: tuple[int, ...],
    token_budget: int,
) -> tuple[tuple[int, ...], tuple[OmittedEvidence, ...], int]:
    selected: list[int] = []
    omitted: list[OmittedEvidence] = []
    consumed = 0
    for ordinal in ordered:
        segment = atlas.segments[ordinal]
        cost = segment.statistics.token_count
        if consumed + cost <= token_budget:
            selected.append(ordinal)
            consumed += cost
        else:
            omitted.append(
                OmittedEvidence(
                    anchor_id=segment.anchor.anchor_id,
                    section_id=segment.anchor.section_id,
                    reason="token_budget",
                    estimated_tokens=cost,
                )
            )
    return tuple(selected), tuple(omitted), consumed

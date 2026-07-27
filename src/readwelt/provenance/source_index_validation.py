"""Complete closure validation for immutable SourceIndex projections."""

from __future__ import annotations

from typing import Any

from .source_index_projection import check_links, check_map, reverse


def validate_source_index(index: Any, *, current_schema: str) -> tuple[str, ...]:
    problems: list[str] = []
    units = frozenset(index.source_unit_ids)
    ranges = frozenset(index.source_range_ids)
    elements = frozenset(index.source_element_ids)
    nodes = frozenset(index.canonical_node_ids)
    edges = frozenset(index.canonical_edge_ids)
    claims = frozenset(index.canonical_claim_ids)
    sections = (
        frozenset(index.source_section_ids)
        if index.schema_version == current_schema
        else frozenset(section_id for section_id, _ in index.section_to_units)
    )
    for values, label in (
        (index.source_unit_ids, "source_unit_ids"),
        (index.source_range_ids, "source_range_ids"),
        (index.source_element_ids, "source_element_ids"),
        (index.source_section_ids, "source_section_ids"),
        (index.canonical_node_ids, "canonical_node_ids"),
        (index.canonical_edge_ids, "canonical_edge_ids"),
        (index.canonical_claim_ids, "canonical_claim_ids"),
    ):
        _check_unique_identities(values, label, problems)

    forward_maps = (
        (index.node_to_units, nodes, units, "node_to_units"),
        (index.edge_to_units, edges, units, "edge_to_units"),
        (index.claim_to_evidence_units, claims, units, "claim_to_evidence_units"),
        (index.range_to_units, ranges, units, "range_to_units"),
        (index.element_to_units, elements, units, "element_to_units"),
        (index.node_to_elements, nodes, elements, "node_to_elements"),
        (index.edge_to_elements, edges, elements, "edge_to_elements"),
        (
            index.claim_to_evidence_elements,
            claims,
            elements,
            "claim_to_evidence_elements",
        ),
    )
    for mapping, keys, values, label in forward_maps:
        check_map(mapping, keys, values, label, problems)

    complete_maps = (
        (index.node_to_units, nodes, "node_to_units"),
        (index.edge_to_units, edges, "edge_to_units"),
        (index.claim_to_evidence_units, claims, "claim_to_evidence_units"),
        (index.range_to_units, ranges, "range_to_units"),
        (index.element_to_units, elements, "element_to_units"),
    )
    for mapping, keys, label in complete_maps:
        _check_complete_keys(mapping, keys, label, problems)
    if index.schema_version == current_schema:
        for mapping, keys, label in (
            (index.node_to_elements, nodes, "node_to_elements"),
            (index.edge_to_elements, edges, "edge_to_elements"),
            (
                index.claim_to_evidence_elements,
                claims,
                "claim_to_evidence_elements",
            ),
            (index.section_to_units, sections, "section_to_units"),
        ):
            _check_complete_keys(mapping, keys, label, problems)

    check_map(index.section_to_units, sections, units, "section_to_units", problems)
    for mapping, values, label in (
        (index.heading_to_units, units, "heading_to_units"),
        (index.lexical_to_ranges, ranges, "lexical_to_ranges"),
        (index.lexical_to_elements, elements, "lexical_to_elements"),
    ):
        _check_text_projection(mapping, values, label, problems)
    for mapping, values, label in (
        (index.page_to_units, units, "page_to_units"),
        (index.page_to_elements, elements, "page_to_elements"),
    ):
        _check_numeric_projection(mapping, values, label, problems)

    reverse_pairs = (
        (index.node_to_units, index.unit_to_nodes, "node/unit"),
        (index.edge_to_units, index.unit_to_edges, "edge/unit"),
        (index.claim_to_evidence_units, index.unit_to_claims, "claim/unit"),
        (index.range_to_units, index.unit_to_ranges, "range/unit"),
    )
    for forward, backward, label in reverse_pairs:
        _check_reverse(forward, backward, label, problems)
    if index.schema_version == current_schema:
        for forward, backward, label in (
            (index.node_to_elements, index.element_to_nodes, "node/element"),
            (index.edge_to_elements, index.element_to_edges, "edge/element"),
            (
                index.claim_to_evidence_elements,
                index.element_to_claims,
                "claim/element",
            ),
        ):
            _check_reverse(forward, backward, label, problems)

    _check_navigation(
        index.unit_to_parent,
        index.parent_to_children,
        index.unit_to_previous,
        index.unit_to_next,
        units,
        "unit",
        problems,
    )
    _check_navigation(
        index.element_to_parent,
        index.parent_to_child_elements,
        index.element_to_previous,
        index.element_to_next,
        elements,
        "element",
        problems,
    )
    _check_range_intervals(index.range_intervals, ranges, problems)
    _check_ordinals(index.ordinal_to_unit, units, problems)
    return tuple(problems)


def _check_navigation(
    child_to_parent: tuple[tuple[str, str], ...],
    parent_to_children: tuple[tuple[str, tuple[str, ...]], ...],
    previous: tuple[tuple[str, str], ...],
    following: tuple[tuple[str, str], ...],
    known: frozenset[str],
    label: str,
    problems: list[str],
) -> None:
    check_links(child_to_parent, known, f"{label}_to_parent", problems)
    check_map(
        parent_to_children,
        known,
        known,
        f"parent_to_child_{label}s",
        problems,
    )
    _check_link_reverse(child_to_parent, parent_to_children, f"{label} hierarchy", problems)
    check_links(previous, known, f"{label}_to_previous", problems)
    check_links(following, known, f"{label}_to_next", problems)
    _check_inverse_links(previous, following, f"{label} previous/next", problems)


def _check_unique_identities(
    values: tuple[str, ...],
    label: str,
    problems: list[str],
) -> None:
    if len(values) != len(set(values)):
        problems.append(f"{label} contains duplicate identities")
    if any(not value for value in values):
        problems.append(f"{label} contains an empty identity")


def _check_complete_keys(
    mapping: tuple[tuple[str, tuple[str, ...]], ...],
    expected: frozenset[str],
    label: str,
    problems: list[str],
) -> None:
    if frozenset(key for key, _ in mapping) != expected:
        problems.append(f"{label} does not cover its complete key space")


def _check_text_projection(
    mapping: tuple[tuple[str, tuple[str, ...]], ...],
    known_values: frozenset[str],
    label: str,
    problems: list[str],
) -> None:
    keys = tuple(key for key, _ in mapping)
    if len(keys) != len(set(keys)):
        problems.append(f"{label} contains duplicate keys")
    for key, values in mapping:
        if not key:
            problems.append(f"{label} contains an empty key")
        if len(values) != len(set(values)):
            problems.append(f"{label} contains duplicate values for {key}")
        if any(value not in known_values for value in values):
            problems.append(f"{label} contains an unknown value")


def _check_numeric_projection(
    mapping: tuple[tuple[int, tuple[str, ...]], ...],
    known_values: frozenset[str],
    label: str,
    problems: list[str],
) -> None:
    keys = tuple(key for key, _ in mapping)
    if len(keys) != len(set(keys)):
        problems.append(f"{label} contains duplicate keys")
    for key, values in mapping:
        if key < 1:
            problems.append(f"{label} contains an invalid page")
        if len(values) != len(set(values)):
            problems.append(f"{label} contains duplicate values for {key}")
        if any(value not in known_values for value in values):
            problems.append(f"{label} contains an unknown value")


def _check_multi_map(
    mapping: tuple[tuple[str, tuple[str, ...]], ...],
    known_keys: frozenset[str],
    known_values: frozenset[str],
    label: str,
    problems: list[str],
) -> None:
    check_map(mapping, known_keys, known_values, label, problems)


def _check_reverse(
    forward: tuple[tuple[str, tuple[str, ...]], ...],
    backward: tuple[tuple[str, tuple[str, ...]], ...],
    label: str,
    problems: list[str],
) -> None:
    if reverse(dict(forward)) != backward:
        problems.append(f"{label} projections disagree")


def _check_link_reverse(
    child_to_parent: tuple[tuple[str, str], ...],
    parent_to_children: tuple[tuple[str, tuple[str, ...]], ...],
    label: str,
    problems: list[str],
) -> None:
    expected: dict[str, set[str]] = {}
    for child_id, parent_id in child_to_parent:
        expected.setdefault(parent_id, set()).add(child_id)
    frozen = tuple((key, tuple(sorted(values))) for key, values in sorted(expected.items()))
    if frozen != parent_to_children:
        problems.append(f"{label} projections disagree")


def _check_inverse_links(
    previous: tuple[tuple[str, str], ...],
    following: tuple[tuple[str, str], ...],
    label: str,
    problems: list[str],
) -> None:
    if tuple(sorted((target, source) for source, target in previous)) != following:
        problems.append(f"{label} projections disagree")


def _check_range_intervals(
    intervals: tuple[tuple[int, int, str], ...],
    known_ranges: frozenset[str],
    problems: list[str],
) -> None:
    ids = tuple(range_id for _, _, range_id in intervals)
    if frozenset(ids) != known_ranges or len(ids) != len(set(ids)):
        problems.append("range_intervals does not cover each source range exactly once")
    if any(start < 0 or end <= start for start, end, _ in intervals):
        problems.append("range_intervals contains an invalid interval")
    if intervals != tuple(sorted(intervals)):
        problems.append("range_intervals is not deterministic")


def _check_ordinals(
    ordinals: tuple[tuple[int, str], ...],
    known_units: frozenset[str],
    problems: list[str],
) -> None:
    positions = tuple(ordinal for ordinal, _ in ordinals)
    unit_ids = tuple(unit_id for _, unit_id in ordinals)
    if len(positions) != len(set(positions)) or any(item < 0 for item in positions):
        problems.append("ordinal_to_unit contains invalid or duplicate ordinals")
    if frozenset(unit_ids) != known_units or len(unit_ids) != len(set(unit_ids)):
        problems.append("ordinal_to_unit does not cover each source unit exactly once")
    if ordinals != tuple(sorted(ordinals)):
        problems.append("ordinal_to_unit is not deterministic")

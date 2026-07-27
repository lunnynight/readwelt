"""Pure deterministic helpers used to rebuild and validate SourceIndex."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from readwelt.article_graph.models import ArticleGraph
from readwelt.article_ir import AnchoredTextUnit, SourceRangeRecord, UnitizationResult
from readwelt.domain.documents import SourceElement
from readwelt.semantic.tokenization import TOKENIZER_VERSION, tokenize


@dataclass(frozen=True, slots=True)
class SourceIndexDiagnostic:
    """One raw reference excluded from the index because it did not resolve."""

    code: str
    identity: str
    referrer: str


def build_source_index_values(
    graph: ArticleGraph,
    unitization: UnitizationResult,
    *,
    schema_version: str,
    ledger_head_digest: str,
) -> dict[str, object]:
    """Build all immutable SourceIndex fields except its content digest."""

    ordered_units = tuple(sorted(unitization.units, key=lambda unit: (unit.ordinal, unit.unit_id)))
    ordered_ranges = tuple(
        sorted(
            unitization.source_ranges,
            key=lambda item: (item.start_offset, item.end_offset, item.range_id),
        )
    )
    ordered_elements = tuple(
        sorted(
            unitization.source_elements,
            key=lambda item: (item.reading_order, item.ordinal, item.element_id),
        )
    )
    source_unit_ids = tuple(unit.unit_id for unit in ordered_units)
    source_range_ids = tuple(item.range_id for item in ordered_ranges)
    source_element_ids = tuple(item.element_id for item in ordered_elements)
    source_section_ids = tuple(
        sorted(
            {
                reference.section_id
                for unit in ordered_units
                for reference in unit.source_references
                if reference.section_id is not None
            }
        )
    )
    require_unique(source_unit_ids, "source unit")
    require_unique(source_range_ids, "source range")
    require_unique(source_element_ids, "source element")
    require_unique((unit.ordinal for unit in ordered_units), "source unit ordinal")

    known_units = frozenset(source_unit_ids)
    known_elements = frozenset(source_element_ids)
    diagnostics: list[SourceIndexDiagnostic] = []
    node_units = grounded_knowledge_units(
        ((node.node_id, node.source_unit_ids) for node in graph.nodes),
        known_units,
        diagnostics,
        code="unknown_node_source_unit",
    )
    edge_units = grounded_knowledge_units(
        ((edge.edge_id, edge.source_unit_ids) for edge in graph.edges),
        known_units,
        diagnostics,
        code="unknown_edge_source_unit",
    )
    claim_units = grounded_knowledge_units(
        ((claim.claim_id, claim.evidence_unit_ids) for claim in graph.claims),
        known_units,
        diagnostics,
        code="unknown_claim_source_unit",
    )
    node_elements = grounded_knowledge_units(
        ((node.node_id, node.source_element_ids) for node in graph.nodes),
        known_elements,
        diagnostics,
        code="unknown_node_source_element",
    )
    edge_elements = grounded_knowledge_units(
        ((edge.edge_id, edge.source_element_ids) for edge in graph.edges),
        known_elements,
        diagnostics,
        code="unknown_edge_source_element",
    )
    claim_elements = grounded_knowledge_units(
        ((claim.claim_id, claim.evidence_element_ids) for claim in graph.claims),
        known_elements,
        diagnostics,
        code="unknown_claim_source_element",
    )
    range_units = _range_units(ordered_ranges, known_units, diagnostics)
    (
        section_units,
        heading_units,
        element_units,
        page_units,
    ) = _unit_locators(ordered_units, known_elements, source_element_ids, diagnostics)
    page_elements = _page_elements(ordered_elements)
    unit_ranges = reverse(range_units)
    lexical_ranges, lexical_elements = _lexical_locators(
        ordered_units,
        ordered_elements,
        unit_ranges,
    )
    unit_parent, parent_children = unit_hierarchy(
        ordered_units,
        known_units,
        diagnostics,
    )
    unit_previous = resolved_links(
        (
            (unit.unit_id, unit.previous_unit_id)
            for unit in ordered_units
            if unit.previous_unit_id is not None
        ),
        known_units,
        diagnostics,
        code="unknown_previous_unit",
    )
    unit_next = resolved_links(
        (
            (unit.unit_id, unit.next_unit_id)
            for unit in ordered_units
            if unit.next_unit_id is not None
        ),
        known_units,
        diagnostics,
        code="unknown_next_unit",
    )
    element_parent, parent_child_elements = element_hierarchy(
        ordered_elements,
        known_elements,
        diagnostics,
    )
    element_previous = resolved_links(
        (
            (element.element_id, element.previous_element_id)
            for element in ordered_elements
            if element.previous_element_id is not None
        ),
        known_elements,
        diagnostics,
        code="unknown_previous_element",
    )
    element_next = resolved_links(
        (
            (element.element_id, element.next_element_id)
            for element in ordered_elements
            if element.next_element_id is not None
        ),
        known_elements,
        diagnostics,
        code="unknown_next_element",
    )
    return {
        "schema_version": schema_version,
        "graph_digest": graph.content_digest,
        "ledger_head_digest": ledger_head_digest,
        "node_to_units": freeze_forward(node_units),
        "edge_to_units": freeze_forward(edge_units),
        "claim_to_evidence_units": freeze_forward(claim_units),
        "unit_to_nodes": reverse(node_units),
        "unit_to_edges": reverse(edge_units),
        "unit_to_claims": reverse(claim_units),
        "node_to_elements": freeze_forward(node_elements),
        "edge_to_elements": freeze_forward(edge_elements),
        "claim_to_evidence_elements": freeze_forward(claim_elements),
        "element_to_nodes": reverse(node_elements),
        "element_to_edges": reverse(edge_elements),
        "element_to_claims": reverse(claim_elements),
        "source_unit_ids": source_unit_ids,
        "source_range_ids": source_range_ids,
        "source_element_ids": source_element_ids,
        "source_section_ids": source_section_ids,
        "canonical_node_ids": tuple(sorted(node.node_id for node in graph.nodes)),
        "canonical_edge_ids": tuple(sorted(edge.edge_id for edge in graph.edges)),
        "canonical_claim_ids": tuple(sorted(claim.claim_id for claim in graph.claims)),
        "range_intervals": tuple(
            (item.start_offset, item.end_offset, item.range_id) for item in ordered_ranges
        ),
        "range_to_units": freeze_forward(range_units),
        "unit_to_ranges": unit_ranges,
        "ordinal_to_unit": tuple((unit.ordinal, unit.unit_id) for unit in ordered_units),
        "section_to_units": freeze_forward(section_units),
        "heading_to_units": freeze_forward(heading_units),
        "element_to_units": freeze_forward(element_units),
        "page_to_units": freeze_numeric(page_units),
        "page_to_elements": freeze_numeric(page_elements),
        "lexical_to_ranges": freeze_forward(lexical_ranges),
        "lexical_to_elements": freeze_forward(lexical_elements),
        "unit_to_parent": unit_parent,
        "parent_to_children": parent_children,
        "unit_to_previous": unit_previous,
        "unit_to_next": unit_next,
        "element_to_parent": element_parent,
        "parent_to_child_elements": parent_child_elements,
        "element_to_previous": element_previous,
        "element_to_next": element_next,
        "lexical_tokenizer_version": TOKENIZER_VERSION,
        "diagnostics": tuple(
            sorted(
                diagnostics,
                key=lambda item: (item.code, item.referrer, item.identity),
            )
        ),
    }


def _range_units(
    source_ranges: tuple[SourceRangeRecord, ...],
    known_units: frozenset[str],
    diagnostics: list[SourceIndexDiagnostic],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for source_range in source_ranges:
        result[source_range.range_id] = {
            unit_id for unit_id in source_range.unit_ids if unit_id in known_units
        }
        for unknown in sorted(set(source_range.unit_ids) - known_units):
            diagnostics.append(
                SourceIndexDiagnostic(
                    code="unknown_range_source_unit",
                    identity=unknown,
                    referrer=source_range.range_id,
                )
            )
    return result


def _unit_locators(
    units: tuple[AnchoredTextUnit, ...],
    known_elements: frozenset[str],
    source_element_ids: tuple[str, ...],
    diagnostics: list[SourceIndexDiagnostic],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[int, set[str]],
]:
    sections: dict[str, set[str]] = {}
    headings: dict[str, set[str]] = {}
    elements: dict[str, set[str]] = {element_id: set() for element_id in source_element_ids}
    pages: dict[int, set[str]] = {}
    for unit in units:
        unit_headings = set(unit.heading_trail)
        for reference in unit.source_references:
            if reference.section_id is not None:
                sections.setdefault(reference.section_id, set()).add(unit.unit_id)
            unit_headings.update(reference.heading_trail)
            if reference.element_id is not None:
                if reference.element_id in known_elements:
                    elements.setdefault(reference.element_id, set()).add(unit.unit_id)
                else:
                    diagnostics.append(
                        SourceIndexDiagnostic(
                            code="unknown_unit_source_element",
                            identity=reference.element_id,
                            referrer=unit.unit_id,
                        )
                    )
            if reference.page is not None:
                pages.setdefault(reference.page, set()).add(unit.unit_id)
        for heading in unit_headings:
            if heading:
                headings.setdefault(heading, set()).add(unit.unit_id)
    return sections, headings, elements, pages


def _page_elements(elements: tuple[SourceElement, ...]) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for element in elements:
        if element.page is not None:
            result.setdefault(element.page, set()).add(element.element_id)
    return result


def _lexical_locators(
    units: tuple[AnchoredTextUnit, ...],
    elements: tuple[SourceElement, ...],
    unit_ranges: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    ranges: dict[str, set[str]] = {}
    ranges_by_unit = dict(unit_ranges)
    for unit in units:
        range_ids = ranges_by_unit.get(unit.unit_id, ())
        for lexeme in set(tokenize(unit.exact_text)):
            ranges.setdefault(lexeme, set()).update(range_ids)
    element_ids: dict[str, set[str]] = {}
    for element in elements:
        if element.exact_text:
            for lexeme in set(tokenize(element.exact_text)):
                element_ids.setdefault(lexeme, set()).add(element.element_id)
    return ranges, element_ids


def grounded_knowledge_units(
    items: Iterable[tuple[str, tuple[str, ...]]],
    known_units: frozenset[str],
    diagnostics: list[SourceIndexDiagnostic],
    *,
    code: str,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for object_id, unit_ids in items:
        result[object_id] = {unit_id for unit_id in unit_ids if unit_id in known_units}
        for unknown in sorted(set(unit_ids) - known_units):
            diagnostics.append(
                SourceIndexDiagnostic(code=code, identity=unknown, referrer=object_id)
            )
    return result


def unit_hierarchy(
    units: tuple[AnchoredTextUnit, ...],
    known_units: frozenset[str],
    diagnostics: list[SourceIndexDiagnostic],
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, tuple[str, ...]], ...]]:
    links = resolved_links(
        ((unit.unit_id, unit.parent_unit_id) for unit in units if unit.parent_unit_id is not None),
        known_units,
        diagnostics,
        code="unknown_parent_unit",
    )
    children: dict[str, set[str]] = {}
    for child_id, parent_id in links:
        children.setdefault(parent_id, set()).add(child_id)
    return links, freeze_forward(children)


def element_hierarchy(
    elements: tuple[SourceElement, ...],
    known_elements: frozenset[str],
    diagnostics: list[SourceIndexDiagnostic],
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, tuple[str, ...]], ...]]:
    declared = [
        (element.element_id, element.parent_element_id)
        for element in elements
        if element.parent_element_id is not None
    ]
    declared.extend(
        (child_id, element.element_id)
        for element in elements
        for child_id in element.child_element_ids
    )
    links = resolved_links(
        declared,
        known_elements,
        diagnostics,
        code="unknown_parent_or_child_element",
    )
    parent_by_child: dict[str, str] = {}
    for child_id, parent_id in links:
        parent_by_child.setdefault(child_id, parent_id)
    normalized = tuple(sorted(parent_by_child.items()))
    children: dict[str, set[str]] = {}
    for child_id, parent_id in normalized:
        children.setdefault(parent_id, set()).add(child_id)
    return normalized, freeze_forward(children)


def resolved_links(
    links: Iterable[tuple[str, str]],
    known: frozenset[str],
    diagnostics: list[SourceIndexDiagnostic],
    *,
    code: str,
) -> tuple[tuple[str, str], ...]:
    resolved: dict[str, str] = {}
    for source_id, target_id in links:
        if source_id not in known or target_id not in known:
            diagnostics.append(
                SourceIndexDiagnostic(
                    code=code,
                    identity=target_id,
                    referrer=source_id,
                )
            )
            continue
        resolved.setdefault(source_id, target_id)
    return tuple(sorted(resolved.items()))


def freeze_forward(
    mapping: Mapping[str, set[str]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (object_id, tuple(sorted(unit_ids))) for object_id, unit_ids in sorted(mapping.items())
    )


def freeze_numeric(
    mapping: Mapping[int, set[str]],
) -> tuple[tuple[int, tuple[str, ...]], ...]:
    return tuple(
        (value, tuple(sorted(identities))) for value, identities in sorted(mapping.items())
    )


def reverse(
    mapping: Mapping[str, set[str] | tuple[str, ...]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    reversed_values: dict[str, set[str]] = {}
    for object_id, unit_ids in mapping.items():
        for unit_id in unit_ids:
            reversed_values.setdefault(unit_id, set()).add(object_id)
    return tuple(
        (unit_id, tuple(sorted(object_ids)))
        for unit_id, object_ids in sorted(reversed_values.items())
    )


def ranges_for_units(
    unit_ids: Iterable[str],
    unit_to_ranges: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            range_id for unit_id in unit_ids for range_id in unit_to_ranges.get(unit_id, ())
        )
    )


def ordered_subset(values: Iterable[str], order: tuple[str, ...]) -> tuple[str, ...]:
    admitted = frozenset(values)
    return tuple(value for value in order if value in admitted)


def require_unique(values: Iterable[object], label: str) -> None:
    materialized = tuple(values)
    if len(set(materialized)) != len(materialized):
        raise ValueError(f"{label} identities must be unique")


def check_map(
    mapping: tuple[tuple[str, tuple[str, ...]], ...],
    known_keys: frozenset[str],
    known_values: frozenset[str],
    label: str,
    problems: list[str],
) -> None:
    keys = tuple(key for key, _ in mapping)
    if len(keys) != len(set(keys)):
        problems.append(f"{label} contains duplicate keys")
    for key, values in mapping:
        if key not in known_keys:
            problems.append(f"{label} contains unknown key {key}")
        if len(values) != len(set(values)):
            problems.append(f"{label} contains duplicate values for {key}")
        for value in values:
            if value not in known_values:
                problems.append(f"{label} contains unknown value {value}")


def check_links(
    links: tuple[tuple[str, str], ...],
    known: frozenset[str],
    label: str,
    problems: list[str],
) -> None:
    sources = tuple(source_id for source_id, _ in links)
    if len(sources) != len(set(sources)):
        problems.append(f"{label} contains duplicate sources")
    for source_id, target_id in links:
        if source_id not in known or target_id not in known:
            problems.append(f"{label} contains unresolved link {source_id}->{target_id}")

"""Typed closure from provider-visible locating material to the Source Plane."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from readwelt.article_graph.digest import content_digest
from readwelt.article_ir import UnitizationResult

from . import closure_models as _closure_models
from . import models as _provenance_models
from .ledger import ProvenanceLedger
from .source_index import SourceIndex

PROVENANCE_CLOSURE_SCHEMA_VERSION = _closure_models.PROVENANCE_CLOSURE_SCHEMA_VERSION
ProvenanceClosureIssue = _closure_models.ProvenanceClosureIssue
ProvenanceClosureReport = _closure_models.ProvenanceClosureReport
ProviderMaterialDisposition = _closure_models.ProviderMaterialDisposition
ProviderMaterialKind = _closure_models.ProviderMaterialKind
ProviderMaterialResolution = _closure_models.ProviderMaterialResolution
ProviderVisibleMaterial = _closure_models.ProviderVisibleMaterial
SourceRecordKind = _closure_models.SourceRecordKind
TypedSourceReference = _closure_models.TypedSourceReference
ProvenanceEvent = _provenance_models.ProvenanceEvent
ProvenanceEventType = _provenance_models.ProvenanceEventType
ProvenanceLedgerArtifact = _provenance_models.ProvenanceLedgerArtifact


def provider_visible_material(
    *,
    nodes: Iterable[tuple[str, tuple[str, ...]] | tuple[str, tuple[str, ...], tuple[str, ...]]],
    edges: Iterable[tuple[str, tuple[str, ...]] | tuple[str, tuple[str, ...], tuple[str, ...]]],
    text_items: Iterable[tuple[str, str, bool]],
    claims: Iterable[
        tuple[str, tuple[str, ...]] | tuple[str, tuple[str, ...], tuple[str, ...]]
    ] = (),
    source_ranges: Iterable[tuple[str, tuple[str, ...]]] = (),
    source_elements: Iterable[tuple[str, str, tuple[str, ...]]] = (),
) -> tuple[ProviderVisibleMaterial, ...]:
    """Build the typed list from the exact fields serialized by StageView."""

    return (
        *(
            ProviderVisibleMaterial(
                material_id=item[0],
                material_kind=ProviderMaterialKind.GRAPH_NODE,
                source_unit_ids=item[1],
                source_element_ids=item[2] if len(item) == 3 else (),
            )
            for item in nodes
        ),
        *(
            ProviderVisibleMaterial(
                material_id=item[0],
                material_kind=ProviderMaterialKind.GRAPH_EDGE,
                source_unit_ids=item[1],
                source_element_ids=item[2] if len(item) == 3 else (),
            )
            for item in edges
        ),
        *(
            ProviderVisibleMaterial(
                material_id=item[0],
                material_kind=ProviderMaterialKind.GRAPH_CLAIM,
                source_unit_ids=item[1],
                source_element_ids=item[2] if len(item) == 3 else (),
            )
            for item in claims
        ),
        *(
            ProviderVisibleMaterial(
                material_id=material_id,
                material_kind=(
                    ProviderMaterialKind.TEXT_SLICE if is_slice else ProviderMaterialKind.TEXT_UNIT
                ),
                source_unit_ids=(unit_id,),
            )
            for material_id, unit_id, is_slice in text_items
        ),
        *(
            ProviderVisibleMaterial(
                material_id=range_id,
                material_kind=ProviderMaterialKind.SOURCE_RANGE,
                source_unit_ids=unit_ids,
                source_record_id=range_id,
            )
            for range_id, unit_ids in source_ranges
        ),
        *(
            ProviderVisibleMaterial(
                material_id=material_id,
                material_kind=ProviderMaterialKind.SOURCE_ELEMENT,
                source_unit_ids=unit_ids,
                source_record_id=element_id,
            )
            for material_id, element_id, unit_ids in source_elements
        ),
    )


def final_provider_visible_material(
    *,
    stage_view_materials: Iterable[ProviderVisibleMaterial],
    unitization: UnitizationResult,
    anchor_ids: Iterable[str],
    retrieval_hits: Iterable[tuple[str, str]],
    upstream_claim_ids: Iterable[str],
    external_evidence_ids: Iterable[str],
    metadata_ids: Iterable[str],
    provenance_ids: Iterable[str],
) -> tuple[ProviderVisibleMaterial, ...]:
    """Type every material category in the final StageRequest.

    ``retrieval_hits`` contains ``(hit_id, anchor_id)`` pairs. Source-backed
    categories resolve anchor identities now; all other categories are
    explicitly non-source and cannot be mistaken for article facts.
    """

    anchors = tuple(
        ProviderVisibleMaterial(
            material_id=anchor_id,
            material_kind=ProviderMaterialKind.ANCHOR,
            source_unit_ids=_unit_ids_for_anchor(unitization, anchor_id),
        )
        for anchor_id in dict.fromkeys(anchor_ids)
    )
    hits = tuple(
        ProviderVisibleMaterial(
            material_id=hit_id,
            material_kind=ProviderMaterialKind.RETRIEVAL_HIT,
            source_unit_ids=_unit_ids_for_anchor(unitization, anchor_id),
        )
        for hit_id, anchor_id in dict.fromkeys(retrieval_hits)
    )
    return (
        *stage_view_materials,
        *anchors,
        *hits,
        *(
            _non_source_material(
                claim_id,
                ProviderMaterialKind.UPSTREAM_CLAIM,
                "settled_stage_conclusion",
            )
            for claim_id in dict.fromkeys(upstream_claim_ids)
        ),
        *(
            _non_source_material(
                evidence_id,
                ProviderMaterialKind.EXTERNAL_EVIDENCE,
                "outside_article_source_plane",
            )
            for evidence_id in dict.fromkeys(external_evidence_ids)
        ),
        *(
            _non_source_material(
                metadata_id,
                ProviderMaterialKind.REQUEST_METADATA,
                "provider_request_control_metadata",
            )
            for metadata_id in dict.fromkeys(metadata_ids)
        ),
        *(
            _non_source_material(
                provenance_id,
                ProviderMaterialKind.REQUEST_PROVENANCE,
                "request_lineage_metadata",
            )
            for provenance_id in dict.fromkeys(provenance_ids)
        ),
    )


def validate_provider_material_closure(
    materials: tuple[ProviderVisibleMaterial, ...],
    *,
    snapshot_id: str,
    unitization: UnitizationResult,
    source_index: SourceIndex,
    ledger_artifact: ProvenanceLedgerArtifact,
    expected_graph_digest: str,
    expected_source_index_digest: str,
    expected_ledger_digest: str,
) -> ProvenanceClosureReport:
    """Resolve provider material through trusted events to concrete source records.

    Unknown or mismatched identities produce diagnostics and no invented source
    association. Projection events are deliberately not accepted as grounding.
    """

    issues: list[ProvenanceClosureIssue] = []
    resolutions: list[ProviderMaterialResolution] = []
    _validate_lineage(
        snapshot_id=snapshot_id,
        unitization=unitization,
        source_index=source_index,
        ledger_artifact=ledger_artifact,
        expected_graph_digest=expected_graph_digest,
        expected_source_index_digest=expected_source_index_digest,
        expected_ledger_digest=expected_ledger_digest,
        issues=issues,
    )
    lineage_valid = not issues
    ledger = ProvenanceLedger.from_artifact(ledger_artifact)
    units = {unit.unit_id: unit for unit in unitization.units}
    ranges = {record.range_id: record for record in unitization.source_ranges}
    elements = {element.element_id: element for element in unitization.source_elements}
    unit_to_ranges = dict(source_index.unit_to_ranges)
    element_to_units = dict(source_index.element_to_units)

    for material in materials:
        material_issues: list[ProvenanceClosureIssue] = []
        if material.disposition is ProviderMaterialDisposition.NON_SOURCE_METADATA:
            resolutions.append(
                ProviderMaterialResolution(
                    material=material,
                    source_references=(),
                    ledger_event_digests=(),
                )
            )
            continue
        resolved_unit_ids = _resolve_material_units(
            material,
            source_index,
            material_issues,
        )
        ledger_events = _material_events(
            material,
            resolved_unit_ids,
            ledger.events,
            expected_graph_digest,
            unitization.content_digest,
            material_issues,
        )
        source_references: list[TypedSourceReference] = []
        direct_reference = _direct_source_record(
            material,
            snapshot_id=snapshot_id,
            ranges=ranges,
            elements=elements,
        )
        if direct_reference is not None:
            source_references.append(direct_reference)
        if material.material_kind in {
            ProviderMaterialKind.GRAPH_NODE,
            ProviderMaterialKind.GRAPH_EDGE,
            ProviderMaterialKind.GRAPH_CLAIM,
        }:
            source_references.extend(
                TypedSourceReference(
                    record_id=element_id,
                    record_kind=SourceRecordKind.SOURCE_ELEMENT,
                    snapshot_id=snapshot_id,
                )
                for element_id in material.source_element_ids
                if element_id in elements
            )
        for unit_id in resolved_unit_ids:
            unit = units.get(unit_id)
            if unit is None:
                material_issues.append(
                    _issue(
                        "unknown_source_unit",
                        material,
                        f"source unit {unit_id!r} is absent from the Source Plane",
                    )
                )
                continue
            unit_event = _unitization_event(
                unit_id,
                unitization.content_digest,
                ledger.events,
            )
            if unit_event is None:
                material_issues.append(
                    _issue(
                        "missing_unitization_event",
                        material,
                        f"source unit {unit_id!r} has no unitization ledger event",
                    )
                )
                continue
            reference_ids = frozenset(
                reference.reference_id for reference in unit.source_references
            )
            if not reference_ids.issubset(unit_event.source_refs):
                material_issues.append(
                    _issue(
                        "unitization_source_reference_mismatch",
                        material,
                        f"unitization event does not name every locator for {unit_id!r}",
                    )
                )
                continue
            ledger_events.append(unit_event)
            source_references.extend(
                _source_records_for_unit(
                    unit_id,
                    snapshot_id=snapshot_id,
                    reference_ids=reference_ids,
                    range_ids=unit_to_ranges.get(unit_id, ()),
                    ranges=ranges,
                    element_to_units=element_to_units,
                    elements=elements,
                    material=material,
                    issues=material_issues,
                )
            )
        issues.extend(material_issues)
        resolutions.append(
            ProviderMaterialResolution(
                material=material,
                source_references=(
                    tuple(dict.fromkeys(source_references))
                    if lineage_valid and not material_issues
                    else ()
                ),
                ledger_event_digests=tuple(dict.fromkeys(event.digest for event in ledger_events)),
            )
        )

    resolved = tuple(resolutions)
    recorded_issues = tuple(issues)
    payload = {
        "schema_version": PROVENANCE_CLOSURE_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "resolutions": resolved,
        "issues": recorded_issues,
    }
    return ProvenanceClosureReport(
        schema_version=PROVENANCE_CLOSURE_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        resolutions=resolved,
        issues=recorded_issues,
        content_digest=content_digest(payload),
    )


def _validate_lineage(
    *,
    snapshot_id: str,
    unitization: UnitizationResult,
    source_index: SourceIndex,
    ledger_artifact: ProvenanceLedgerArtifact,
    expected_graph_digest: str,
    expected_source_index_digest: str,
    expected_ledger_digest: str,
    issues: list[ProvenanceClosureIssue],
) -> None:
    lineage_id = "__lineage__"
    if unitization.snapshot_id != snapshot_id:
        issues.append(
            ProvenanceClosureIssue(
                "snapshot_mismatch",
                lineage_id,
                "unitization belongs to another source revision",
            )
        )
    if source_index.content_digest != expected_source_index_digest:
        issues.append(
            ProvenanceClosureIssue(
                "source_index_digest_mismatch",
                lineage_id,
                "provider material names another SourceIndex projection",
            )
        )
    if source_index.graph_digest != expected_graph_digest:
        issues.append(
            ProvenanceClosureIssue(
                "graph_digest_mismatch",
                lineage_id,
                "provider material names another canonical graph projection",
            )
        )
    if ledger_artifact.content_digest != expected_ledger_digest:
        issues.append(
            ProvenanceClosureIssue(
                "ledger_digest_mismatch",
                lineage_id,
                "provider material names another provenance ledger",
            )
        )
    if source_index.ledger_head_digest != ledger_artifact.head_digest:
        issues.append(
            ProvenanceClosureIssue(
                "ledger_head_mismatch",
                lineage_id,
                "SourceIndex and provenance ledger heads disagree",
            )
        )


def _resolve_material_units(
    material: ProviderVisibleMaterial,
    source_index: SourceIndex,
    issues: list[ProvenanceClosureIssue],
) -> tuple[str, ...]:
    if material.material_kind is ProviderMaterialKind.SOURCE_RANGE:
        range_id = material.source_record_id or material.material_id
        if range_id not in source_index.source_range_ids:
            issues.append(
                _issue(
                    "unknown_source_range",
                    material,
                    "provider-visible range is absent from the SourceIndex",
                )
            )
            return ()
        record_units = source_index.units_for_range(range_id)
        if material.source_unit_ids != record_units:
            issues.append(
                _issue(
                    "source_index_grounding_mismatch",
                    material,
                    "provider-visible range grounding disagrees with SourceIndex",
                )
            )
            return ()
        return record_units
    if material.material_kind is ProviderMaterialKind.SOURCE_ELEMENT:
        element_id = material.source_record_id or material.material_id
        if element_id not in source_index.source_element_ids:
            issues.append(
                _issue(
                    "unknown_source_element",
                    material,
                    "provider-visible element is absent from the SourceIndex",
                )
            )
            return ()
        record_units = source_index.units_for_element(element_id)
        if material.source_unit_ids != record_units:
            issues.append(
                _issue(
                    "source_index_grounding_mismatch",
                    material,
                    "provider-visible element grounding disagrees with SourceIndex",
                )
            )
            return ()
        return record_units
    if material.material_kind in {
        ProviderMaterialKind.TEXT_UNIT,
        ProviderMaterialKind.TEXT_SLICE,
        ProviderMaterialKind.ANCHOR,
        ProviderMaterialKind.RETRIEVAL_HIT,
    }:
        if len(material.source_unit_ids) != 1:
            issues.append(
                _issue(
                    "missing_source_binding",
                    material,
                    "source-backed provider material must resolve to exactly one unit",
                )
            )
            return ()
        if (
            material.material_kind is ProviderMaterialKind.TEXT_UNIT
            and material.material_id != material.source_unit_ids[0]
        ):
            issues.append(
                _issue(
                    "text_unit_identity_mismatch",
                    material,
                    "whole text material identity must equal its source unit",
                )
            )
            return ()
        return material.source_unit_ids

    canonical_ids: frozenset[str]
    indexed_units: tuple[str, ...]
    if material.material_kind is ProviderMaterialKind.GRAPH_NODE:
        canonical_ids = frozenset(source_index.canonical_node_ids)
        indexed_units = source_index.units_for_node(material.material_id)
        indexed_elements = source_index.elements_for_node(material.material_id)
    elif material.material_kind is ProviderMaterialKind.GRAPH_EDGE:
        canonical_ids = frozenset(source_index.canonical_edge_ids)
        indexed_units = source_index.units_for_edge(material.material_id)
        indexed_elements = source_index.elements_for_edge(material.material_id)
    else:
        canonical_ids = frozenset(source_index.canonical_claim_ids)
        indexed_units = source_index.evidence_units_for_claim(material.material_id)
        indexed_elements = source_index.evidence_elements_for_claim(material.material_id)
    if material.material_id not in canonical_ids:
        issues.append(
            _issue(
                "unknown_graph_object",
                material,
                "provider-visible graph identity is absent from the canonical index",
            )
        )
        return ()
    if material.source_unit_ids != indexed_units:
        issues.append(
            _issue(
                "source_index_grounding_mismatch",
                material,
                "provider-visible grounding disagrees with SourceIndex",
            )
        )
        return ()
    if material.source_element_ids != indexed_elements:
        issues.append(
            _issue(
                "source_index_element_grounding_mismatch",
                material,
                "provider-visible element grounding disagrees with SourceIndex",
            )
        )
        return ()
    if not indexed_units and not indexed_elements:
        issues.append(
            _issue(
                "missing_source_grounding",
                material,
                "canonical graph material has no grounded source unit or element",
            )
        )
        return ()
    return indexed_units


def _material_events(
    material: ProviderVisibleMaterial,
    unit_ids: tuple[str, ...],
    events: tuple[ProvenanceEvent, ...],
    expected_graph_digest: str,
    unitization_digest: str,
    issues: list[ProvenanceClosureIssue],
) -> list[ProvenanceEvent]:
    if material.material_kind in {
        ProviderMaterialKind.SOURCE_RANGE,
        ProviderMaterialKind.SOURCE_ELEMENT,
    }:
        event = next(
            (
                candidate
                for candidate in events
                if candidate.event_type is ProvenanceEventType.UNITIZATION
                and unitization_digest in candidate.outputs
            ),
            None,
        )
        if event is None:
            issues.append(
                _issue(
                    "missing_unitization_event",
                    material,
                    "Source Plane material has no unitization ledger event",
                )
            )
            return []
        return [event]
    if material.material_kind in {
        ProviderMaterialKind.TEXT_UNIT,
        ProviderMaterialKind.TEXT_SLICE,
        ProviderMaterialKind.ANCHOR,
        ProviderMaterialKind.RETRIEVAL_HIT,
    }:
        return []
    candidates = tuple(
        event
        for event in events
        if event.event_type is ProvenanceEventType.CANONICALIZATION
        and material.material_id in event.outputs
        and expected_graph_digest in event.outputs
    )
    event = next(
        (
            candidate
            for candidate in candidates
            if set((*unit_ids, *material.source_element_ids)).issubset(candidate.source_refs)
        ),
        None,
    )
    if event is None:
        issues.append(
            _issue(
                "missing_canonicalization_event",
                material,
                "no canonicalization event closes this object to its source units",
            )
        )
        return []
    return [event]


def _direct_source_record(
    material: ProviderVisibleMaterial,
    *,
    snapshot_id: str,
    ranges: Mapping[str, object],
    elements: Mapping[str, object],
) -> TypedSourceReference | None:
    if material.material_kind is ProviderMaterialKind.SOURCE_RANGE:
        range_id = material.source_record_id or material.material_id
        if range_id in ranges:
            return TypedSourceReference(
                record_id=range_id,
                record_kind=SourceRecordKind.SOURCE_RANGE,
                snapshot_id=snapshot_id,
            )
    if material.material_kind is ProviderMaterialKind.SOURCE_ELEMENT:
        element_id = material.source_record_id or material.material_id
        if element_id in elements:
            return TypedSourceReference(
                record_id=element_id,
                record_kind=SourceRecordKind.SOURCE_ELEMENT,
                snapshot_id=snapshot_id,
            )
    return None


def _unitization_event(
    unit_id: str,
    unitization_digest: str,
    events: tuple[ProvenanceEvent, ...],
) -> ProvenanceEvent | None:
    return next(
        (
            event
            for event in events
            if event.event_type is ProvenanceEventType.UNITIZATION
            and unit_id in event.outputs
            and unitization_digest in event.outputs
        ),
        None,
    )


def _source_records_for_unit(
    unit_id: str,
    *,
    snapshot_id: str,
    reference_ids: frozenset[str],
    range_ids: tuple[str, ...],
    ranges: Mapping[str, object],
    element_to_units: dict[str, tuple[str, ...]],
    elements: Mapping[str, object],
    material: ProviderVisibleMaterial,
    issues: list[ProvenanceClosureIssue],
) -> tuple[TypedSourceReference, ...]:
    references = [
        TypedSourceReference(
            record_id=unit_id,
            record_kind=SourceRecordKind.TEXT_UNIT,
            snapshot_id=snapshot_id,
            via_unit_id=unit_id,
        ),
        *(
            TypedSourceReference(
                record_id=reference_id,
                record_kind=SourceRecordKind.SOURCE_REFERENCE,
                snapshot_id=snapshot_id,
                via_unit_id=unit_id,
            )
            for reference_id in sorted(reference_ids)
        ),
    ]
    for range_id in range_ids:
        if range_id not in ranges:
            issues.append(
                _issue(
                    "unknown_source_range",
                    material,
                    f"SourceIndex range {range_id!r} is absent from the Source Plane",
                )
            )
            continue
        references.append(
            TypedSourceReference(
                record_id=range_id,
                record_kind=SourceRecordKind.SOURCE_RANGE,
                snapshot_id=snapshot_id,
                via_unit_id=unit_id,
            )
        )
    for element_id, linked_units in element_to_units.items():
        if unit_id not in linked_units:
            continue
        if element_id not in elements:
            issues.append(
                _issue(
                    "unknown_source_element",
                    material,
                    f"SourceIndex element {element_id!r} is absent from the Source Plane",
                )
            )
            continue
        references.append(
            TypedSourceReference(
                record_id=element_id,
                record_kind=SourceRecordKind.SOURCE_ELEMENT,
                snapshot_id=snapshot_id,
                via_unit_id=unit_id,
            )
        )
    return tuple(references)


def _issue(
    code: str,
    material: ProviderVisibleMaterial,
    detail: str,
) -> ProvenanceClosureIssue:
    return ProvenanceClosureIssue(
        code=code,
        material_id=material.material_id,
        detail=detail,
    )


def _unit_ids_for_anchor(
    unitization: UnitizationResult,
    anchor_id: str,
) -> tuple[str, ...]:
    return tuple(
        unit.unit_id
        for unit in unitization.units
        if any(reference.anchor_id == anchor_id for reference in unit.source_references)
    )


def _non_source_material(
    material_id: str,
    material_kind: ProviderMaterialKind,
    reason: str,
) -> ProviderVisibleMaterial:
    return ProviderVisibleMaterial(
        material_id=material_id,
        material_kind=material_kind,
        source_unit_ids=(),
        disposition=ProviderMaterialDisposition.NON_SOURCE_METADATA,
        non_source_reason=reason,
    )

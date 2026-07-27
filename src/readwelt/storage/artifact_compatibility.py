"""Typed decoders for immutable current and historical ArticleGraph artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter

from readwelt.article_graph import (
    ArticleGraph,
    ArticleGraphBuildArtifact,
    ArticleGraphCapabilityReport,
    GroundingFailure,
    MergeReport,
)
from readwelt.article_graph.digest import content_digest, stable_identifier
from readwelt.article_ir import (
    ARTICLE_SOURCE_PLANE_SCHEMA_VERSION,
    HISTORICAL_UNITIZATION_SCHEMA_VERSION,
    UnitizationResult,
)
from readwelt.extraction import GraphExtraction
from readwelt.provenance import ProvenanceLedgerArtifact, SourceIndex
from readwelt.stage_views import StageView


@dataclass(frozen=True, slots=True)
class HistoricalSourceIndexV1:
    """The immutable projection contract emitted before source-first indexing."""

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
        if self.schema_version != "source-index.v1":
            raise ValueError(f"unsupported historical source index: {self.schema_version}")
        if _reverse(self.node_to_units) != self.unit_to_nodes:
            raise ValueError("historical node source index directions disagree")
        if _reverse(self.edge_to_units) != self.unit_to_edges:
            raise ValueError("historical edge source index directions disagree")
        if _reverse(self.claim_to_evidence_units) != self.unit_to_claims:
            raise ValueError("historical claim source index directions disagree")
        if self.content_digest != content_digest(
            {
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
        ):
            raise ValueError("historical source index content digest mismatch")


@dataclass(frozen=True, slots=True)
class HistoricalArticleGraphBuildV1:
    """Typed historical aggregate whose v1 SourceIndex is no longer current."""

    schema_version: str
    snapshot_id: str
    policy_id: str
    unitization: UnitizationResult
    extractions: tuple[GraphExtraction, ...]
    graph: ArticleGraph
    merge_report: MergeReport
    provenance_ledger: ProvenanceLedgerArtifact
    source_index: HistoricalSourceIndexV1
    capability_report: ArticleGraphCapabilityReport
    grounding_failures: tuple[GroundingFailure, ...]
    content_digest: str


def decode_artifact(
    artifact_type: str,
    schema_version: str,
    payload: Mapping[str, Any],
) -> object:
    """Decode one supported payload and validate its internal identities."""

    if artifact_type == "anchored_text_unitization":
        unitization = TypeAdapter(UnitizationResult).validate_python(payload)
        _validate_unitization(unitization, payload)
        return unitization
    if artifact_type == "article_graph":
        graph = TypeAdapter(ArticleGraph).validate_python(payload)
        _validate_graph(graph, payload)
        return graph
    if artifact_type == "graph_extraction":
        return TypeAdapter(GraphExtraction).validate_python(payload)
    if artifact_type == "article_graph_source_index":
        model: type[HistoricalSourceIndexV1] | type[SourceIndex]
        model = HistoricalSourceIndexV1 if schema_version == "source-index.v1" else SourceIndex
        return TypeAdapter(model).validate_python(payload)
    if artifact_type == "stage_view":
        stage_view = TypeAdapter(StageView).validate_python(payload)
        _validate_stage_view(stage_view, payload)
        return stage_view
    if artifact_type == "article_graph_build":
        if schema_version in {
            "article-graph-build-artifact.v1",
            "article-graph-build-artifact.v2",
        }:
            return TypeAdapter(ArticleGraphBuildArtifact).validate_python(payload)
        return _decode_historical_build(payload)
    raise ValueError(f"unsupported structured artifact type: {artifact_type}")


def _decode_historical_build(payload: Mapping[str, Any]) -> HistoricalArticleGraphBuildV1:
    unitization = TypeAdapter(UnitizationResult).validate_python(payload["unitization"])
    _validate_unitization(unitization, _mapping(payload["unitization"]))
    extractions = tuple(
        TypeAdapter(GraphExtraction).validate_python(item)
        for item in _sequence(payload["extractions"])
    )
    graph_payload = _mapping(payload["graph"])
    graph = TypeAdapter(ArticleGraph).validate_python(graph_payload)
    _validate_graph(graph, graph_payload)
    merge_payload = _mapping(payload["merge_report"])
    merge_report = TypeAdapter(MergeReport).validate_python(merge_payload)
    _validate_merge_report(merge_report, merge_payload)
    ledger = TypeAdapter(ProvenanceLedgerArtifact).validate_python(payload["provenance_ledger"])
    source_index = TypeAdapter(HistoricalSourceIndexV1).validate_python(payload["source_index"])
    capability_payload = _mapping(payload["capability_report"])
    capability_report = TypeAdapter(ArticleGraphCapabilityReport).validate_python(
        capability_payload
    )
    _validate_capability_report(capability_report, capability_payload)
    grounding_payloads = tuple(_mapping(item) for item in _sequence(payload["grounding_failures"]))
    grounding_failures = tuple(
        TypeAdapter(GroundingFailure).validate_python(item) for item in grounding_payloads
    )
    for failure, failure_payload in zip(
        grounding_failures,
        grounding_payloads,
        strict=True,
    ):
        _validate_grounding_failure(failure, failure_payload)
    if source_index.graph_digest != graph.content_digest:
        raise ValueError("historical source index belongs to another graph")
    if source_index.ledger_head_digest != ledger.head_digest:
        raise ValueError("historical source index belongs to another provenance ledger")
    snapshot_id = str(payload["snapshot_id"])
    if unitization.snapshot_id != snapshot_id or graph.snapshot_id != snapshot_id:
        raise ValueError("historical build components belong to another snapshot")
    if any(extraction.snapshot_id != snapshot_id for extraction in extractions):
        raise ValueError("historical extraction belongs to another snapshot")
    expected = content_digest(
        {
            "schema_version": payload["schema_version"],
            "snapshot_id": snapshot_id,
            "policy_id": payload["policy_id"],
            "unitization_digest": unitization.content_digest,
            "extraction_digests": tuple(item.content_digest for item in extractions),
            "graph_digest": graph.content_digest,
            "merge_report_digest": merge_report.content_digest,
            "provenance_ledger_digest": ledger.content_digest,
            "source_index_digest": source_index.content_digest,
            "capability_report_digest": capability_report.content_digest,
            "grounding_failure_digests": tuple(item.content_digest for item in grounding_failures),
        }
    )
    if payload["content_digest"] != expected:
        raise ValueError("historical article graph build content digest mismatch")
    return HistoricalArticleGraphBuildV1(
        schema_version=str(payload["schema_version"]),
        snapshot_id=snapshot_id,
        policy_id=str(payload["policy_id"]),
        unitization=unitization,
        extractions=extractions,
        graph=graph,
        merge_report=merge_report,
        provenance_ledger=ledger,
        source_index=source_index,
        capability_report=capability_report,
        grounding_failures=grounding_failures,
        content_digest=str(payload["content_digest"]),
    )


def _validate_graph(graph: ArticleGraph, payload: Mapping[str, Any]) -> None:
    keys = [
        "schema_version",
        "snapshot_id",
        "mentions",
        "nodes",
        "edges",
        "claims",
        "available_capabilities",
        "missing_capabilities",
    ]
    if graph.schema_version == "article-graph.v4":
        keys.append("taxonomy_schema_version")
    expected = content_digest({key: payload[key] for key in keys})
    if graph.content_digest != expected:
        raise ValueError("article graph content digest mismatch")


def _validate_merge_report(
    report: MergeReport,
    payload: Mapping[str, Any],
) -> None:
    expected = content_digest(
        {
            key: payload[key]
            for key in (
                "schema_version",
                "policy_id",
                "decisions",
                "conflicts",
                "rejected_candidate_ids",
                "deferred_candidate_ids",
            )
        }
    )
    if report.content_digest != expected:
        raise ValueError("merge report content digest mismatch")


def _validate_capability_report(
    report: ArticleGraphCapabilityReport,
    payload: Mapping[str, Any],
) -> None:
    expected = content_digest(
        (
            payload["schema_version"],
            payload["outcomes"],
            payload["available_capabilities"],
            payload["missing_capabilities"],
            payload["degraded"],
        )
    )
    if report.content_digest != expected:
        raise ValueError("capability report content digest mismatch")


def _validate_grounding_failure(
    failure: GroundingFailure,
    payload: Mapping[str, Any],
) -> None:
    parts = (
        payload["extraction_id"],
        payload["candidate_id"],
        payload["candidate_kind"],
        payload["reference_kind"],
        payload["claimed_unit_ids"],
        payload.get("claimed_element_ids", ()),
        payload["reason"],
    )
    if failure.content_digest != content_digest(parts):
        raise ValueError("grounding failure content digest mismatch")
    if failure.failure_id != stable_identifier("grounding_failure", *parts):
        raise ValueError("grounding failure identity mismatch")


def _validate_unitization(
    unitization: UnitizationResult,
    payload: Mapping[str, Any],
) -> None:
    coverage = _mapping(payload["coverage"])
    expected_coverage = content_digest(
        {
            "snapshot_id": coverage["snapshot_id"],
            "document_id": coverage["document_id"],
            "source_length": coverage["source_length"],
            "records": tuple(_coverage_record_value(item) for item in coverage["records"]),
            "normalization_transformations": coverage["normalization_transformations"],
        }
    )
    if coverage["content_digest"] != expected_coverage:
        raise ValueError("unitization coverage content digest mismatch")
    for unit in _sequence(payload["units"]):
        unit_mapping = _mapping(unit)
        exact_text = str(unit_mapping["exact_text"])
        expected_hash = f"sha256:{hashlib.sha256(exact_text.encode()).hexdigest()}"
        if unit_mapping["content_hash"] != expected_hash:
            raise ValueError("anchored text unit content hash mismatch")
    digest_payload: dict[str, Any] = {
        "schema_version": unitization.schema_version,
        "snapshot_id": unitization.snapshot_id,
        "units": tuple(_unit_value(item) for item in _sequence(payload["units"])),
        "coverage_digest": coverage["content_digest"],
    }
    if unitization.schema_version == ARTICLE_SOURCE_PLANE_SCHEMA_VERSION:
        manifest = _mapping(payload["coverage_manifest"])
        expected_manifest = content_digest(
            {
                "schema_version": manifest["schema_version"],
                "snapshot_id": manifest["snapshot_id"],
                "source_length": manifest["source_length"],
                "range_coverage": tuple(
                    _coverage_record_value(item) for item in manifest["range_coverage"]
                ),
                "element_coverage": tuple(
                    _coverage_record_value(item) for item in manifest["element_coverage"]
                ),
                "structure_coverage": tuple(
                    _coverage_record_value(item) for item in manifest["structure_coverage"]
                ),
                "capability_coverage": tuple(
                    _coverage_record_value(item) for item in manifest["capability_coverage"]
                ),
            }
        )
        if manifest["content_digest"] != expected_manifest:
            raise ValueError("Source Plane coverage manifest digest mismatch")
        digest_payload.update(
            source_ranges=tuple(
                _source_range_value(item) for item in _sequence(payload["source_ranges"])
            ),
            source_elements=tuple(
                _source_element_value(item) for item in _sequence(payload["source_elements"])
            ),
            coverage_manifest_digest=manifest["content_digest"],
        )
    elif unitization.schema_version != HISTORICAL_UNITIZATION_SCHEMA_VERSION:
        raise ValueError(f"unsupported unitization schema: {unitization.schema_version}")
    if unitization.content_digest != content_digest(digest_payload):
        raise ValueError("unitization content digest mismatch")


def _validate_stage_view(view: StageView, raw: Mapping[str, Any] | None = None) -> None:
    source = raw or {}
    keys = [
        "schema_version",
        "snapshot_id",
        "stage",
        "task_intent",
        "nodes",
        "edges",
        "text_units",
        "upstream_claims",
        "unresolved_conflict_ids",
        "missing_capabilities",
        "capability_outcomes",
        "coverage_complete",
    ]
    if view.schema_version in {"stage-view.v2", "stage-view.v3", "stage-view.v4"}:
        keys.extend(("coverage", "continuation", "blocking_records"))
        keys.extend(
            key
            for key in (
                "source_ranges",
                "source_elements",
                "external_evidence",
                "external_evidence_omissions",
            )
            if key in source
        )
    keys.extend(
        (
            "token_budget",
            "estimated_tokens",
            "selection_reasons",
            "locator_backend",
            "fallback_backend",
            "graph_digest",
            "source_index_digest",
            "provenance_ledger_digest",
        )
    )
    if view.schema_version == "stage-view.v4":
        keys.append("claim_candidates")
    if view.schema_version in {"stage-view.v2", "stage-view.v3", "stage-view.v4"}:
        keys.append("hard_serialized_token_budget")
    payload = {key: source[key] for key in keys}
    if view.content_digest != content_digest(payload):
        raise ValueError("StageView content digest mismatch")


def _unit_value(value: object) -> dict[str, Any]:
    unit = _mapping(value)
    return {
        key: unit[key]
        for key in (
            "unit_id",
            "schema_version",
            "snapshot_id",
            "document_id",
            "revision_id",
            "ordinal",
            "kind",
            "exact_text",
            "content_hash",
            "structural_path",
            "heading_trail",
        )
    } | {
        "source_references": tuple(
            tuple(
                reference[key]
                for key in (
                    "reference_id",
                    "section_id",
                    "anchor_id",
                    "start_offset",
                    "end_offset",
                    "exact_text",
                    "prefix",
                    "suffix",
                    "page",
                    "bounding_box",
                    "element_id",
                    "textual_anchor",
                    "kind",
                    "parent_element_id",
                    "heading_trail",
                )
            )
            for reference in map(_mapping, unit["source_references"])
        ),
        "parent_unit_id": unit["parent_unit_id"],
        "previous_unit_id": unit["previous_unit_id"],
        "next_unit_id": unit["next_unit_id"],
    }


def _coverage_record_value(value: object) -> tuple[object, ...]:
    record = _mapping(value)
    return tuple(
        record[key]
        for key in (
            "record_id",
            "status",
            "scope",
            "reason",
            "start_offset",
            "end_offset",
            "section_id",
            "unit_ids",
            "detail",
        )
    )


def _source_range_value(value: object) -> dict[str, Any]:
    source_range = _mapping(value)
    return {
        key: source_range[key]
        for key in (
            "range_id",
            "snapshot_id",
            "schema_version",
            "start_offset",
            "end_offset",
            "kind",
            "content_hash",
            "unit_ids",
            "reason",
        )
    }


def _source_element_value(value: object) -> tuple[object, ...]:
    element = _mapping(value)
    keys = (
        "element_id",
        "schema_version",
        "ordinal",
        "reading_order",
        "projection_status",
        "kind",
        "content_layer",
        "start_offset",
        "end_offset",
        "parent_element_id",
        "child_element_ids",
        "previous_element_id",
        "next_element_id",
        "structural_relations",
        "page",
        "bounding_box",
        "native_reference",
        "raw_payload_ref",
    )
    return tuple(element.get(key) if key == "content_layer" else element[key] for key in keys)


def _reverse(
    forward: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    result: dict[str, set[str]] = {}
    for object_id, unit_ids in forward:
        for unit_id in unit_ids:
            result.setdefault(unit_id, set()).add(object_id)
    return tuple(
        (unit_id, tuple(sorted(object_ids))) for unit_id, object_ids in sorted(result.items())
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("artifact component must be an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError("artifact component must be an array")
    return tuple(value)

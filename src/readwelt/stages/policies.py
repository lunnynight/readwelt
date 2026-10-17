"""Fixed six-stage order, policies, and provider response contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from readwelt.domain.reading import LedgerDecision, ReadingStage

STAGES = (
    ReadingStage.MAINLINE,
    ReadingStage.STRUCTURE,
    ReadingStage.DECOMPRESSION,
    ReadingStage.AUTHOR_MODEL,
    ReadingStage.BOUNDARIES,
    ReadingStage.TRANSFER,
)
ARTICLE_ONLY = frozenset((ReadingStage.MAINLINE, ReadingStage.STRUCTURE))
ACCEPTED = frozenset((LedgerDecision.ACCEPTED, LedgerDecision.QUALIFIED))
STAGE_POLICIES: Mapping[ReadingStage, Mapping[str, Any]] = {
    ReadingStage.MAINLINE: {
        "goal": "Recover the article's main line using only the supplied source anchors.",
        "produce": (
            "core idea, core question, major claims, internal evidence, "
            "reasoning chain, and source-underdetermined gaps"
        ),
        "constraints": (
            "Every strong claim must cite admitted source_citations or anchor_ids; "
            "do not use biography, "
            "historical background, external research, or imported theory."
        ),
    },
    ReadingStage.STRUCTURE: {
        "goal": "Map how the article's argument is constructed.",
        "produce": (
            "paragraph functions and claim/premise/evidence/example/objection/"
            "qualification/conclusion relationships"
        ),
        "constraints": (
            "Separate explicit structure from inference and the author's claims "
            "from quoted claims; use only source anchors and accepted stage-1 claims."
        ),
    },
    ReadingStage.DECOMPRESSION: {
        "goal": "Decompress knowledge assumed or compressed by the article.",
        "produce": (
            "source-grounded decompression units with prerequisites, concepts, "
            "mechanisms, assumptions, boundaries, transfer examples, and uncertainties; "
            "link each unit to stage claims and typed source citations"
        ),
        "constraints": (
            "External evidence may support, qualify, or challenge frozen article "
            "understanding, but must not rewrite stages 1-2."
        ),
    },
    ReadingStage.AUTHOR_MODEL: {
        "goal": "Recover a bounded model of how the author sees and selects the problem.",
        "produce": (
            "core assumptions, salient objects, problem genesis, chosen and rejected "
            "methods, plus at least two competing interpretations"
        ),
        "constraints": (
            "Mark interpretation distance and evidence; do not present speculation "
            "as author fact. Every competing claim must include a distinct "
            "provenance.interpretation_id."
        ),
    },
    ReadingStage.BOUNDARIES: {
        "goal": "Pressure-test the settled reading.",
        "produce": (
            "implicit assumptions, validity conditions, counterexamples, temporal/"
            "regional/institutional boundaries, alternatives, and missing evidence"
        ),
        "constraints": "Qualify or reject claims that do not survive the boundary test.",
    },
    ReadingStage.TRANSFER: {
        "goal": "Transfer only claims that survived the stage-5 boundary test.",
        "produce": (
            "original method, abstract principle, invariant mechanism, prerequisites, "
            "non-transferable contingencies, new-domain example, and failure test"
        ),
        "constraints": (
            "Do not derive a transfer principle directly from an attractive sentence; "
            "every transfer must cite accepted or qualified stage-5 source_claim_ids."
        ),
    },
}
_SOURCE_CITATION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "required": ["kind", "identity"],
    "properties": {
        "schema_version": {"type": "string", "enum": ["source-citation.v1"]},
        "kind": {"enum": ["anchor", "unit", "range", "element", "graph_object"]},
        "identity": {"type": "string"},
    },
}
_STRING_ARRAY_SCHEMA: Mapping[str, Any] = {
    "type": "array",
    "items": {"type": "string"},
}

RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "anchor_ids"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "text": {"type": "string"},
                    "anchor_ids": {"type": "array", "items": {"type": "string"}},
                    "graph_object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_citations": {
                        "type": "array",
                        "items": _SOURCE_CITATION_SCHEMA,
                    },
                    "decision": {
                        "enum": [decision.value for decision in LedgerDecision],
                    },
                    "source_claim_ids": {"type": "array", "items": {"type": "string"}},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                    "provenance": {"type": "object"},
                },
            },
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind", "description"],
                "properties": {
                    "gap_id": {"type": "string"},
                    "kind": {"type": "string"},
                    "description": {"type": "string"},
                    "affected_claim_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "critical": {"type": "boolean"},
                    "repairable": {"type": "boolean"},
                    "resolved": {"type": "boolean"},
                },
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}
DECOMPRESSION_RESPONSE_SCHEMA: Mapping[str, Any] = {
    **RESPONSE_SCHEMA,
    "required": [*RESPONSE_SCHEMA["required"], "decompression_units"],
    "properties": {
        **RESPONSE_SCHEMA["properties"],
        "decompression_units": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "unit_id",
                    "explanation",
                    "claim_ids",
                    "source_citations",
                ],
                "properties": {
                    "unit_id": {"type": "string"},
                    "explanation": {"type": "string"},
                    "claim_ids": _STRING_ARRAY_SCHEMA,
                    "source_citations": {
                        "type": "array",
                        "items": _SOURCE_CITATION_SCHEMA,
                    },
                    "concepts_introduced": _STRING_ARRAY_SCHEMA,
                    "concepts_assumed": _STRING_ARRAY_SCHEMA,
                    "mechanism_steps": _STRING_ARRAY_SCHEMA,
                    "dependencies": _STRING_ARRAY_SCHEMA,
                    "missing_prerequisites": _STRING_ARRAY_SCHEMA,
                    "tacit_practices": _STRING_ARRAY_SCHEMA,
                    "assumptions": _STRING_ARRAY_SCHEMA,
                    "inferred_relations": _STRING_ARRAY_SCHEMA,
                    "boundary_conditions": _STRING_ARRAY_SCHEMA,
                    "alternatives": _STRING_ARRAY_SCHEMA,
                    "changed_condition_examples": _STRING_ARRAY_SCHEMA,
                    "uncertainties": _STRING_ARRAY_SCHEMA,
                },
                "additionalProperties": False,
            },
        },
    },
}


def response_schema_for_stage(stage: ReadingStage) -> Mapping[str, Any]:
    return DECOMPRESSION_RESPONSE_SCHEMA if stage is ReadingStage.DECOMPRESSION else RESPONSE_SCHEMA

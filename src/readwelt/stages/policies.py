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
            "prerequisites, concepts, context, verification targets, and conflicts "
            "linked to specific source or upstream claim ids"
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
                        "items": {
                            "type": "object",
                            "required": ["kind", "identity"],
                            "properties": {
                                "schema_version": {
                                    "type": "string",
                                    "enum": ["source-citation.v1"],
                                },
                                "kind": {
                                    "enum": [
                                        "anchor",
                                        "unit",
                                        "range",
                                        "element",
                                        "graph_object",
                                    ]
                                },
                                "identity": {"type": "string"},
                            },
                        },
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

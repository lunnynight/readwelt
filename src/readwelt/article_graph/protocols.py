"""Structural input contracts for extraction artifacts.

Concrete extraction dataclasses intentionally live outside this package.  The
canonicalizer accepts these protocols as well as mappings with equivalent keys.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CandidateNodeLike(Protocol):
    candidate_id: str
    kind: str
    label: str | None
    text: str | None
    confidence: float
    source_unit_ids: Sequence[str]


@runtime_checkable
class CandidateEdgeLike(Protocol):
    candidate_id: str
    relation: str
    source_candidate_id: str
    target_candidate_id: str
    confidence: float
    source_unit_ids: Sequence[str]


@runtime_checkable
class GraphExtractionLike(Protocol):
    extraction_id: str
    snapshot_id: str
    candidate_nodes: Sequence[CandidateNodeLike]
    candidate_edges: Sequence[CandidateEdgeLike]


ExtractionInput = GraphExtractionLike | Mapping[str, Any]

"""Versioned closed core taxonomy for ArticleGraph locating candidates."""

from __future__ import annotations

import re
from enum import StrEnum

ARGUMENT_TAXONOMY_SCHEMA_VERSION = "argument-locating-taxonomy.v1"


class CoreCandidateKind(StrEnum):
    ENTITY = "entity"
    CONCEPT = "concept"
    EVENT = "event"
    CLAIM = "claim"
    PREMISE = "premise"
    CONCLUSION = "conclusion"
    EVIDENCE = "evidence"
    EXAMPLE = "example"
    OBJECTION = "objection"
    QUALIFICATION = "qualification"


class CoreRelationKind(StrEnum):
    SUPPORT = "support"
    REFUTATION = "refutation"
    CAUSATION = "causation"
    CONTRAST = "contrast"
    QUALIFICATION = "qualification"
    EXEMPLIFICATION = "exemplification"
    PREMISE_TO_CLAIM = "premise-to-claim"
    CONCLUSION_FLOW = "conclusion-flow"


CORE_CANDIDATE_KINDS = tuple(item.value for item in CoreCandidateKind)
CORE_RELATION_KINDS = tuple(item.value for item in CoreRelationKind)
_NAMESPACED_EXTENSION = re.compile(r"^[a-z][a-z0-9_.-]*:[a-z][a-z0-9_.-]*$")


def valid_candidate_kind(value: str) -> bool:
    return value in CORE_CANDIDATE_KINDS or valid_namespaced_extension(value)


def valid_relation_kind(value: str) -> bool:
    return value in CORE_RELATION_KINDS or valid_namespaced_extension(value)


def valid_namespaced_extension(value: str) -> bool:
    return _NAMESPACED_EXTENSION.fullmatch(value) is not None

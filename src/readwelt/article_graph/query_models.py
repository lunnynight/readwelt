"""Versioned public contracts for the ArticleGraph Agent Query Plane."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ARTICLE_GRAPH_QUERY_REQUEST_SCHEMA_VERSION = "readwelt.articlegraph-query-request.v1"
ARTICLE_GRAPH_QUERY_FILTER_SCHEMA_VERSION = "readwelt.articlegraph-query-filter.v1"
ARTICLE_GRAPH_QUERY_BUDGET_SCHEMA_VERSION = "readwelt.articlegraph-query-budget.v1"
ARTICLE_GRAPH_QUERY_HIT_SCHEMA_VERSION = "readwelt.articlegraph-query-hit.v1"
ARTICLE_GRAPH_EVIDENCE_SCHEMA_VERSION = "readwelt.articlegraph-evidence.v1"
ARTICLE_GRAPH_QUERY_PAGE_SCHEMA_VERSION = "readwelt.articlegraph-query-page.v1"
ARTICLE_GRAPH_QUERY_RECEIPT_SCHEMA_VERSION = "readwelt.articlegraph-query-receipt.v1"
ARTICLE_GRAPH_QUERY_CONTINUATION_SCHEMA_VERSION = "readwelt.articlegraph-query-continuation.v1"
ARTICLE_GRAPH_QUERY_ERROR_SCHEMA_VERSION = "readwelt.articlegraph-query-error.v1"


class QueryOperation(StrEnum):
    SEARCH = "search"
    LOCATE = "locate"
    EVIDENCE = "evidence"
    NEIGHBORS = "neighbors"
    TRACE_CLAIM = "trace_claim"
    EXPAND_CONTEXT = "expand_context"


class QueryObjectKind(StrEnum):
    SOURCE_UNIT = "source_unit"
    SOURCE_ELEMENT = "source_element"
    MENTION = "mention"
    NODE = "node"
    EDGE = "edge"
    CLAIM = "claim"


class LocatorPrecision(StrEnum):
    EXACT_RANGE = "exact_range"
    SOURCE_ELEMENT = "source_element"
    PAGE = "page"
    SOURCE_UNIT = "source_unit"
    DOCUMENT = "document"


class QueryTruncationReason(StrEnum):
    MAX_HITS = "max_hits"
    MAX_DEPTH = "max_depth"
    MAX_VISITED_OBJECTS = "max_visited_objects"
    MAX_RELATION_PATHS = "max_relation_paths"
    MAX_EVIDENCE_CHARACTERS = "max_evidence_characters"
    MAX_SOURCE_BYTES = "max_source_bytes"
    MAX_ESTIMATED_TOKENS = "max_estimated_tokens"


class QueryErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    DOCUMENT_NOT_FOUND = "document_not_found"
    GRAPH_NOT_PREPARED = "graph_not_prepared"
    OBJECT_NOT_FOUND = "object_not_found"
    DANGLING_SOURCE_REFERENCE = "dangling_source_reference"
    INVALID_CONTINUATION = "invalid_continuation"
    RESTART_REQUIRED = "restart_required"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INTERNAL_ERROR = "internal_error"


class _QueryWireModel(BaseModel):
    """Strict immutable base with one stable public serialization path."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version_value: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        return cls.model_validate(dict(value))


class QueryFilter(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_FILTER_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-filter.v1"] = (
        "readwelt.articlegraph-query-filter.v1"
    )
    object_kinds: tuple[QueryObjectKind, ...] = ()
    source_unit_ids: tuple[str, ...] = ()
    source_element_ids: tuple[str, ...] = ()
    relation_kinds: tuple[str, ...] = ()
    epistemic_statuses: tuple[str, ...] = ()
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_page_range(self) -> Self:
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_end requires page_start")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class QueryBudget(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_BUDGET_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-budget.v1"] = (
        "readwelt.articlegraph-query-budget.v1"
    )
    max_hits: int = Field(default=50, ge=1, le=500)
    max_depth: int = Field(default=2, ge=0, le=8)
    max_visited_objects: int = Field(default=2_000, ge=1, le=100_000)
    max_relation_paths: int = Field(default=100, ge=1, le=2_000)
    max_evidence_characters: int = Field(default=32_768, ge=1, le=2_097_152)
    max_source_bytes: int = Field(default=65_536, ge=1, le=4_194_304)
    max_estimated_tokens: int = Field(default=8_192, ge=1, le=131_072)


class QueryUsage(_QueryWireModel):
    schema_version_value = "readwelt.articlegraph-query-usage.v1"
    schema_version: Literal["readwelt.articlegraph-query-usage.v1"] = (
        "readwelt.articlegraph-query-usage.v1"
    )
    returned_hits: int = Field(ge=0)
    visited_objects: int = Field(default=0, ge=0)
    traversed_edges: int = Field(default=0, ge=0)
    relation_paths: int = Field(default=0, ge=0)
    evidence_characters: int = Field(default=0, ge=0)
    source_bytes: int = Field(default=0, ge=0)
    estimated_tokens: int = Field(default=0, ge=0)


class SourceLocator(_QueryWireModel):
    schema_version_value = "readwelt.articlegraph-source-locator.v1"
    schema_version: Literal["readwelt.articlegraph-source-locator.v1"] = (
        "readwelt.articlegraph-source-locator.v1"
    )
    precision: LocatorPrecision
    source_unit_id: str | None = None
    source_range_id: str | None = None
    source_element_id: str | None = None
    section_id: str | None = None
    page: int | None = Field(default=None, ge=1)
    bounding_box: tuple[float, float, float, float] | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_locator(self) -> Self:
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be provided together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset <= self.start_offset
        ):
            raise ValueError("end_offset must be greater than start_offset")
        identities = (
            self.source_unit_id,
            self.source_range_id,
            self.source_element_id,
            self.section_id,
            self.page,
        )
        if all(value is None for value in identities):
            raise ValueError("source locator must retain at least one source identity")
        if self.bounding_box is not None and self.page is None:
            raise ValueError("bounding_box requires page")
        if self.precision is LocatorPrecision.EXACT_RANGE and self.source_range_id is None:
            raise ValueError("exact_range precision requires source_range_id")
        return self


class RelationHop(_QueryWireModel):
    schema_version_value = "readwelt.articlegraph-relation-hop.v1"
    schema_version: Literal["readwelt.articlegraph-relation-hop.v1"] = (
        "readwelt.articlegraph-relation-hop.v1"
    )
    edge_id: str
    relation_kind: str
    source_object_id: str
    target_object_id: str

    @field_validator("edge_id", "relation_kind", "source_object_id", "target_object_id")
    @classmethod
    def _require_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("relation hop identities must be non-empty")
        return value


class EvidenceEnvelope(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_EVIDENCE_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-evidence.v1"] = (
        "readwelt.articlegraph-evidence.v1"
    )
    evidence_id: str
    graph_object_ids: tuple[str, ...]
    locators: tuple[SourceLocator, ...]
    exact_text: str | None = None
    provenance_digest: str

    @field_validator("evidence_id", "provenance_digest")
    @classmethod
    def _require_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence identity and provenance digest must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_grounding(self) -> Self:
        if not self.graph_object_ids:
            raise ValueError("evidence must identify at least one graph object")
        if not self.locators:
            raise ValueError("evidence must retain at least one source locator")
        return self


class QueryHit(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_HIT_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-hit.v1"] = (
        "readwelt.articlegraph-query-hit.v1"
    )
    object_id: str
    object_kind: QueryObjectKind
    rank: int = Field(ge=1)
    score: float | None = None
    match_reason: str
    label: str | None = None
    text: str | None = None
    epistemic_status: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_method: str | None = None
    ambiguity: tuple[str, ...] = ()
    source_unit_ids: tuple[str, ...] = ()
    source_element_ids: tuple[str, ...] = ()
    evidence: tuple[EvidenceEnvelope, ...] = ()
    relation_path: tuple[RelationHop, ...] = ()

    @field_validator("object_id", "match_reason")
    @classmethod
    def _require_object_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("object_id must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_evidence_ownership(self) -> Self:
        for envelope in self.evidence:
            if self.object_id not in envelope.graph_object_ids:
                raise ValueError("hit evidence must reference the returned object")
        return self


class ArticleGraphQueryRequest(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_REQUEST_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-request.v1"] = (
        "readwelt.articlegraph-query-request.v1"
    )
    document_id: str
    operation: QueryOperation
    query: str | None = None
    object_ids: tuple[str, ...] = ()
    consumer_stage: str | None = None
    task_intent: str | None = None
    filters: QueryFilter = Field(default_factory=QueryFilter)
    budget: QueryBudget = Field(default_factory=QueryBudget)
    continuation: str | None = None

    @field_validator("document_id")
    @classmethod
    def _require_document_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_id must be non-empty")
        return value


class QueryContinuation(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_CONTINUATION_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-continuation.v1"] = (
        "readwelt.articlegraph-query-continuation.v1"
    )
    snapshot_id: str
    graph_digest: str
    operation: QueryOperation
    normalized_query_digest: str
    filter_digest: str
    budget_digest: str
    next_offset: int = Field(ge=0)
    ordering_key: tuple[str, ...] = ()
    remaining_frontier: tuple[str, ...] = ()
    visited_object_ids: tuple[str, ...] = ()


class QueryReceipt(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_RECEIPT_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-receipt.v1"] = (
        "readwelt.articlegraph-query-receipt.v1"
    )
    receipt_id: str
    snapshot_id: str
    graph_digest: str
    operation: QueryOperation
    consumer_stage: str | None = None
    normalized_query_digest: str
    returned_object_ids: tuple[str, ...]
    budget: QueryBudget
    usage: QueryUsage
    input_continuation_digest: str | None = None
    output_continuation_digest: str | None = None
    retrieval_backend: str = "deterministic"
    fallback_backend: str | None = None
    result_digest: str


class QueryPage(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_PAGE_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-page.v1"] = (
        "readwelt.articlegraph-query-page.v1"
    )
    snapshot_id: str
    graph_digest: str
    operation: QueryOperation
    normalized_query_digest: str
    hits: tuple[QueryHit, ...]
    budget: QueryBudget
    usage: QueryUsage
    truncation_reason: QueryTruncationReason | None = None
    continuation: str | None = None
    receipt: QueryReceipt

    @model_validator(mode="after")
    def _validate_receipt_and_order(self) -> Self:
        ranks = tuple(hit.rank for hit in self.hits)
        if ranks != tuple(range(1, len(self.hits) + 1)):
            raise ValueError("query hit ranks must be contiguous and ordered from one")
        returned_ids = tuple(hit.object_id for hit in self.hits)
        expected = (
            self.snapshot_id,
            self.graph_digest,
            self.operation,
            self.normalized_query_digest,
            returned_ids,
            self.budget,
            self.usage,
        )
        observed = (
            self.receipt.snapshot_id,
            self.receipt.graph_digest,
            self.receipt.operation,
            self.receipt.normalized_query_digest,
            self.receipt.returned_object_ids,
            self.receipt.budget,
            self.receipt.usage,
        )
        if observed != expected:
            raise ValueError("query page and receipt disagree")
        if self.usage.returned_hits != len(self.hits):
            raise ValueError("query usage returned_hits disagrees with page hits")
        if (self.continuation is None) != (self.truncation_reason is None):
            raise ValueError("continuation and truncation_reason must appear together")
        return self


class QueryErrorDetail(_QueryWireModel):
    schema_version_value = "readwelt.articlegraph-query-error-detail.v1"
    schema_version: Literal["readwelt.articlegraph-query-error-detail.v1"] = (
        "readwelt.articlegraph-query-error-detail.v1"
    )
    field: str | None = None
    code: str
    message: str


class QueryError(_QueryWireModel):
    schema_version_value = ARTICLE_GRAPH_QUERY_ERROR_SCHEMA_VERSION
    schema_version: Literal["readwelt.articlegraph-query-error.v1"] = (
        "readwelt.articlegraph-query-error.v1"
    )
    code: QueryErrorCode
    message: str
    restart_required: bool = False
    retryable: bool = False
    details: tuple[QueryErrorDetail, ...] = ()

    @model_validator(mode="after")
    def _validate_restart_contract(self) -> Self:
        if self.code is QueryErrorCode.RESTART_REQUIRED and not self.restart_required:
            raise ValueError("restart_required error code must set restart_required")
        if self.restart_required and self.code is not QueryErrorCode.RESTART_REQUIRED:
            raise ValueError("restart_required flag requires restart_required error code")
        return self

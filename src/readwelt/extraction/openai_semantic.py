"""Production OpenAI-compatible backend for argument-locating candidates."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from readwelt.provider_input import (
    DEFAULT_TOKEN_COUNTER,
    InputTokenCounter,
    ProviderContractError,
    openai_structured_payload,
)

from .models import (
    BackendCapability,
    BackendDescriptor,
    CandidateEdge,
    CandidateNode,
    CapabilityOutcome,
    CapabilityStatus,
    ConfidenceAssessment,
    DegradationReport,
    ExtractionCoverage,
    ExtractionEpistemicStatus,
    ExtractionInput,
    GraphExtraction,
    NetworkBehavior,
    SourceGrounding,
    SourceReference,
    stable_id,
)
from .taxonomy import (
    ARGUMENT_TAXONOMY_SCHEMA_VERSION,
    CORE_CANDIDATE_KINDS,
    CORE_RELATION_KINDS,
)

_KIND_CAPABILITIES = {
    "entity": BackendCapability.ENTITY,
    "concept": BackendCapability.CONCEPT,
    "event": BackendCapability.EVENT,
    "claim": BackendCapability.CLAIM,
    "premise": BackendCapability.PREMISE,
    "conclusion": BackendCapability.CONCLUSION,
    "evidence": BackendCapability.EVIDENCE,
    "example": BackendCapability.EXAMPLE,
    "objection": BackendCapability.OBJECTION,
    "qualification": BackendCapability.QUALIFICATION,
}
_RELATION_CAPABILITIES = {
    "support": BackendCapability.SUPPORT_RELATION,
    "refutation": BackendCapability.REFUTATION_RELATION,
    "causation": BackendCapability.CAUSATION_RELATION,
    "contrast": BackendCapability.CONTRAST_RELATION,
    "qualification": BackendCapability.QUALIFICATION_RELATION,
    "exemplification": BackendCapability.EXEMPLIFICATION_RELATION,
    "premise-to-claim": BackendCapability.PREMISE_TO_CLAIM_RELATION,
    "conclusion-flow": BackendCapability.CONCLUSION_FLOW_RELATION,
}
_CAPABILITIES = tuple((*_KIND_CAPABILITIES.values(), *_RELATION_CAPABILITIES.values()))
_SYSTEM_INSTRUCTIONS = """
You locate argument structure; you do not write a reading-stage conclusion.
Return only source-grounded candidates from the supplied unit window.
Every start/end offset is zero-based, end-exclusive, and relative to window_text.
Candidate text must equal window_text[start:end]. Edge endpoints must name node
local_ids from the same response. Use only the closed taxonomy in the schema.
If the text does not express a candidate, return an empty array; never guess.
""".strip()
_ATTRIBUTE_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["key", "value"],
        "additionalProperties": False,
    },
}
ARGUMENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "local_id": {"type": "string"},
                    "kind": {"type": "string", "enum": list(CORE_CANDIDATE_KINDS)},
                    "label": {"type": ["string", "null"]},
                    "text": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "confidence": {"type": "number"},
                    "confidence_method": {"type": "string"},
                    "attributes": _ATTRIBUTE_SCHEMA,
                },
                "required": [
                    "local_id",
                    "kind",
                    "label",
                    "text",
                    "start",
                    "end",
                    "confidence",
                    "confidence_method",
                    "attributes",
                ],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "local_id": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "enum": list(CORE_RELATION_KINDS),
                    },
                    "source_local_id": {"type": "string"},
                    "target_local_id": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "confidence": {"type": "number"},
                    "confidence_method": {"type": "string"},
                    "attributes": _ATTRIBUTE_SCHEMA,
                },
                "required": [
                    "local_id",
                    "relation",
                    "source_local_id",
                    "target_local_id",
                    "start",
                    "end",
                    "confidence",
                    "confidence_method",
                    "attributes",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nodes", "edges"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class OpenAIArgumentSemanticBackend:
    """Strict, per-unit bounded semantic extraction over chat completions."""

    model: str
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str | None = None
    timeout_seconds: float = 60.0
    max_request_tokens: int = 32_000
    max_window_chars: int = 12_000
    client: httpx.Client | None = field(default=None, repr=False)
    token_counter: InputTokenCounter = field(
        default=DEFAULT_TOKEN_COUNTER,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("argument semantic model is required")
        if self.max_request_tokens < 1 or self.max_window_chars < 1:
            raise ValueError("argument semantic request bounds must be positive")
        self.base_url = self.base_url.rstrip("/")

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend_id="readwelt.semantic.openai-argument",
            name="OpenAI-compatible argument-locating semantic backend",
            version="1",
            model_revision=self.model,
            supported_capabilities=_CAPABILITIES,
            required_resources=(f"openai-compatible-model:{self.model}",),
            license_name="provider-configured",
            network_behavior=NetworkBehavior.REQUIRED,
            deterministic=False,
            metadata={
                "endpoint_protocol": "openai-chat-completions",
                "model_license": "provider-declared",
                "request_policy": "per-unit-bounded-v1",
            },
            taxonomy_schema_version=ARGUMENT_TAXONOMY_SCHEMA_VERSION,
            emitted_candidate_kinds=CORE_CANDIDATE_KINDS,
            emitted_relations=CORE_RELATION_KINDS,
        )

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction:
        if not inputs:
            raise ValueError("an extraction invocation requires at least one input unit")
        identities = {(item.document_id, item.snapshot_id) for item in inputs}
        if len(identities) != 1:
            raise ValueError("all extraction inputs must share document and snapshot identity")

        nodes: list[CandidateNode] = []
        edges: list[CandidateEdge] = []
        covered: list[str] = []
        failures: list[str] = []
        counts = {capability: 0 for capability in _CAPABILITIES}
        for item in inputs:
            if not item.text.strip():
                continue
            try:
                unit_nodes, unit_edges = self._extract_unit(item)
            except Exception as exc:
                failures.append(f"{item.unit_id}:{type(exc).__name__}:{exc}")
                continue
            nodes.extend(unit_nodes)
            edges.extend(unit_edges)
            covered.append(item.unit_id)
            for node in unit_nodes:
                counts[_KIND_CAPABILITIES[node.kind]] += 1
            for edge in unit_edges:
                counts[_RELATION_CAPABILITIES[edge.relation]] += 1

        input_ids = tuple(item.unit_id for item in inputs)
        covered_ids = tuple(covered)
        uncovered_ids = tuple(
            item.unit_id for item in inputs if item.unit_id not in set(covered_ids)
        )
        outcomes = tuple(
            _capability_outcome(
                capability,
                input_ids,
                covered_ids,
                counts[capability],
                failures,
            )
            for capability in _CAPABILITIES
        )
        document_id, snapshot_id = next(iter(identities))
        extraction_id = stable_id(
            "extraction",
            self.descriptor.backend_id,
            self.descriptor.version,
            self.model,
            document_id,
            snapshot_id,
            *(f"{item.unit_id}:{item.text}" for item in inputs),
        )
        return GraphExtraction(
            schema_version="graph-extraction.v3",
            extraction_id=extraction_id,
            document_id=document_id,
            snapshot_id=snapshot_id,
            backend=self.descriptor,
            input_unit_ids=input_ids,
            candidate_nodes=tuple(nodes),
            candidate_edges=tuple(edges),
            outcomes=outcomes,
            coverage=ExtractionCoverage(input_ids, covered_ids, uncovered_ids),
            degradation=DegradationReport.from_outcomes(outcomes),
            warnings=tuple(failures),
        )

    def _extract_unit(
        self,
        item: ExtractionInput,
    ) -> tuple[list[CandidateNode], list[CandidateEdge]]:
        nodes: list[CandidateNode] = []
        edges: list[CandidateEdge] = []
        offset = 0
        while offset < len(item.text):
            end, payload = self._bounded_payload(item, offset)
            response = self._post(payload)
            parsed = _parse_structured_response(
                response,
                provider_name=self.descriptor.backend_id,
            )
            window_nodes, window_edges = _parse_window(
                item,
                offset,
                item.text[offset:end],
                parsed,
                self.descriptor.backend_id,
            )
            nodes.extend(window_nodes)
            edges.extend(window_edges)
            offset = end
        return nodes, edges

    def _bounded_payload(
        self,
        item: ExtractionInput,
        start: int,
    ) -> tuple[int, dict[str, Any]]:
        high = min(len(item.text), start + self.max_window_chars)
        low = start + 1
        best: tuple[int, dict[str, Any]] | None = None
        while low <= high:
            end = (low + high) // 2
            payload = self._payload(item, start, end)
            tokens = self.token_counter.count_json(payload).tokens
            if tokens <= self.max_request_tokens:
                best = (end, payload)
                low = end + 1
            else:
                high = end - 1
        if best is None:
            raise ProviderContractError(
                "argument semantic request envelope cannot fit one source character"
            )
        return best

    def _payload(
        self,
        item: ExtractionInput,
        start: int,
        end: int,
    ) -> dict[str, Any]:
        return openai_structured_payload(
            model=self.model,
            system_instructions=_SYSTEM_INSTRUCTIONS,
            input_value={
                "schema_version": "argument-semantic-request.v1",
                "taxonomy_schema_version": ARGUMENT_TAXONOMY_SCHEMA_VERSION,
                "document_id": item.document_id,
                "snapshot_id": item.snapshot_id,
                "unit_id": item.unit_id,
                "window_start": start,
                "window_end": end,
                "window_text": item.text[start:end],
            },
            response_schema=ARGUMENT_RESPONSE_SCHEMA,
            schema_name="readwelt_argument_candidates",
        )

    def _post(self, payload: Mapping[str, Any]) -> httpx.Response:
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderContractError(
                f"{self.descriptor.backend_id} is unavailable: no API key was configured"
            )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self.client is not None:
                response = self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=dict(payload),
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client() as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=dict(payload),
                        timeout=self.timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise ProviderContractError(
                f"{self.descriptor.backend_id} is unavailable: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 400:
            raise ProviderContractError(
                f"{self.descriptor.backend_id} is unavailable: HTTP {response.status_code}"
            )
        return response


def configured_argument_semantic_backend(
    environment: Mapping[str, str] | None = None,
) -> OpenAIArgumentSemanticBackend | None:
    """Build the optional production backend without implicit model selection."""

    env = os.environ if environment is None else environment
    model = env.get("READWELT_ARGUMENT_MODEL", "").strip()
    if not model:
        return None
    base_url = env.get(
        "READWELT_ARGUMENT_BASE_URL",
        "http://127.0.0.1:11434/v1",
    )
    api_key = (
        env.get("READWELT_ARGUMENT_API_KEY")
        or env.get("READWELT_API_KEY")
        or env.get("OPENAI_API_KEY")
        or ("local" if _is_local_endpoint(base_url) else None)
    )
    return OpenAIArgumentSemanticBackend(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=float(env.get("READWELT_ARGUMENT_TIMEOUT_SECONDS", "60")),
        max_request_tokens=int(env.get("READWELT_ARGUMENT_MAX_REQUEST_TOKENS", "32000")),
        max_window_chars=int(env.get("READWELT_ARGUMENT_MAX_WINDOW_CHARS", "12000")),
    )


def _parse_window(
    item: ExtractionInput,
    window_start: int,
    window_text: str,
    payload: Mapping[str, Any],
    backend_id: str,
) -> tuple[list[CandidateNode], list[CandidateEdge]]:
    raw_nodes = payload["nodes"]
    raw_edges = payload["edges"]
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ProviderContractError("argument candidate arrays are required")
    node_ids: dict[str, str] = {}
    nodes: list[CandidateNode] = []
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise ProviderContractError("argument node must be an object")
        local_id = _required_text(raw, "local_id")
        if local_id in node_ids:
            raise ProviderContractError(f"duplicate argument node local_id: {local_id}")
        start, end, exact_text = _validated_span(raw, window_text)
        candidate_id = stable_id(
            "candidate",
            backend_id,
            item.unit_id,
            str(window_start),
            local_id,
        )
        node_ids[local_id] = candidate_id
        nodes.append(
            CandidateNode(
                candidate_id=candidate_id,
                kind=_required_text(raw, "kind"),
                label=(str(raw["label"]) if raw.get("label") is not None else None),
                text=exact_text,
                grounding=_grounding(item, window_start + start, window_start + end),
                confidence=_confidence(raw),
                epistemic_status=ExtractionEpistemicStatus.SEMANTIC_INFERENCE,
                attributes=_attributes(raw),
            )
        )
    edges: list[CandidateEdge] = []
    edge_local_ids: set[str] = set()
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            raise ProviderContractError("argument edge must be an object")
        local_id = _required_text(raw, "local_id")
        if local_id in edge_local_ids:
            raise ProviderContractError(f"duplicate argument edge local_id: {local_id}")
        edge_local_ids.add(local_id)
        source_local = _required_text(raw, "source_local_id")
        target_local = _required_text(raw, "target_local_id")
        if source_local not in node_ids or target_local not in node_ids:
            raise ProviderContractError(
                "argument edge endpoints must resolve in the same response window"
            )
        start, end, _exact_text = _validated_span(raw, window_text)
        edges.append(
            CandidateEdge(
                candidate_id=stable_id(
                    "candidate-edge",
                    backend_id,
                    item.unit_id,
                    str(window_start),
                    local_id,
                ),
                relation=_required_text(raw, "relation"),
                source_candidate_id=node_ids[source_local],
                target_candidate_id=node_ids[target_local],
                grounding=_grounding(item, window_start + start, window_start + end),
                confidence=_confidence(raw),
                epistemic_status=ExtractionEpistemicStatus.SEMANTIC_INFERENCE,
                attributes=_attributes(raw),
            )
        )
    return nodes, edges


def _parse_structured_response(
    response: httpx.Response,
    *,
    provider_name: str,
) -> dict[str, Any]:
    """Defer the provider validator import until package initialization is complete."""

    from readwelt.providers.contracts import validate_json_schema

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        candidate = json.loads(content) if isinstance(content, str) else content
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ProviderContractError(f"{provider_name} returned an invalid chat completion") from exc
    if not isinstance(candidate, Mapping):
        raise ProviderContractError(f"{provider_name} returned a non-object candidate")
    validate_json_schema(candidate, ARGUMENT_RESPONSE_SCHEMA)
    return dict(candidate)


def _validated_span(
    value: Mapping[str, Any],
    window_text: str,
) -> tuple[int, int, str]:
    start = value.get("start")
    end = value.get("end")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
        or end > len(window_text)
    ):
        raise ProviderContractError("argument candidate offsets are outside the window")
    exact_text = window_text[start:end]
    supplied = value.get("text")
    if supplied is not None and supplied != exact_text:
        raise ProviderContractError("argument candidate text does not match its offsets")
    return start, end, exact_text


def _grounding(
    item: ExtractionInput,
    start: int,
    end: int,
) -> SourceGrounding:
    element_id = next(
        (
            reference.element_id
            for reference in item.source_references
            if reference.element_id is not None
        ),
        None,
    )
    return SourceGrounding(
        source_references=(
            SourceReference(
                unit_id=item.unit_id,
                element_id=element_id,
                start_offset=start,
                end_offset=end,
                exact_text=item.text[start:end],
            ),
        ),
        exact=True,
    )


def _confidence(value: Mapping[str, Any]) -> ConfidenceAssessment:
    score = value.get("confidence")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ProviderContractError("argument candidate confidence must be numeric")
    return ConfidenceAssessment(
        float(score),
        _required_text(value, "confidence_method"),
    )


def _attributes(value: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    raw = value.get("attributes")
    if not isinstance(raw, list):
        raise ProviderContractError("argument candidate attributes must be an array")
    result: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ProviderContractError("argument candidate attribute must be an object")
        result.append((_required_text(item, "key"), str(item.get("value", ""))))
    return tuple(sorted(result))


def _required_text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ProviderContractError(f"argument candidate {key} is required")
    return result


def _capability_outcome(
    capability: BackendCapability,
    input_ids: tuple[str, ...],
    covered_ids: tuple[str, ...],
    count: int,
    failures: list[str],
) -> CapabilityOutcome:
    if failures:
        status = CapabilityStatus.PARTIAL if covered_ids else CapabilityStatus.FAILED
    else:
        status = CapabilityStatus.COMPLETE if count else CapabilityStatus.EMPTY
    return CapabilityOutcome(
        capability=capability,
        status=status,
        input_unit_ids=input_ids,
        covered_unit_ids=covered_ids,
        candidate_count=count,
        message="; ".join(failures) if failures else None,
    )


def _is_local_endpoint(base_url: str) -> bool:
    normalized = base_url.lower()
    return any(marker in normalized for marker in ("127.0.0.1", "localhost", "[::1]"))

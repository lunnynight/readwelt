"""Internal normalization for structural extraction inputs."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .digest import canonical_value
from .models import EpistemicStatus
from .protocols import ExtractionInput


def normalize_extraction(extraction: ExtractionInput) -> dict[str, Any]:
    extraction_id = str(_read(extraction, "extraction_id", "artifact_id", "id"))
    snapshot_id = str(_read(extraction, "snapshot_id"))
    nodes = _read(extraction, "candidate_nodes", "node_candidates", "nodes", default=())
    edges = _read(extraction, "candidate_edges", "edge_candidates", "edges", default=())
    outcomes = tuple(_read(extraction, "outcomes", default=()))
    available = tuple(
        str(getattr(_read(item, "capability"), "value", _read(item, "capability")))
        for item in outcomes
        if str(getattr(_read(item, "status"), "value", _read(item, "status")))
        in {"complete", "partial", "empty"}
    )
    missing = tuple(
        str(getattr(_read(item, "capability"), "value", _read(item, "capability")))
        for item in outcomes
        if str(getattr(_read(item, "status"), "value", _read(item, "status")))
        in {"unsupported", "not_run", "failed"}
    )
    return {
        "extraction_id": extraction_id,
        "snapshot_id": snapshot_id,
        "nodes": tuple(_normalize_node(item) for item in nodes),
        "edges": tuple(_normalize_edge(item) for item in edges),
        "available_capabilities": tuple(
            _read(extraction, "available_capabilities", default=available)
        ),
        "missing_capabilities": tuple(_read(extraction, "missing_capabilities", default=missing)),
    }


def merge_attributes(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, Any], ...]:
    values: dict[str, list[Any]] = defaultdict(list)
    for candidate in candidates:
        for key, value in candidate["attributes"]:
            if value not in values[key]:
                values[key].append(value)
    return tuple(
        (key, items[0] if len(items) == 1 else tuple(sorted(items, key=repr)))
        for key, items in sorted(values.items())
    )


def unique_candidates(
    candidates: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        previous = by_id.get(candidate_id)
        if previous is not None and previous != candidate:
            raise ValueError(f"candidate id has conflicting definitions: {candidate_id}")
        by_id[candidate_id] = candidate
    return tuple(by_id[key] for key in sorted(by_id))


def identity_key(value: str, case_sensitive: bool) -> str:
    normalized = unicodedata.normalize("NFKC", " ".join(value.split()))
    return normalized if case_sensitive else normalized.casefold()


def sorted_union(groups: Iterable[Iterable[str]]) -> tuple[str, ...]:
    return tuple(sorted({item for group in groups for item in group}))


def _normalize_node(candidate: Any) -> dict[str, Any]:
    candidate_id = str(_read(candidate, "candidate_id", "node_id", "id"))
    return {
        "candidate_id": candidate_id,
        "kind": str(_read(candidate, "kind", "node_kind", "type")).strip().lower(),
        "label": _optional_text(_read(candidate, "label", "name", default=None)),
        "text": _optional_text(_read(candidate, "text", "exact_text", default=None)),
        "confidence": _confidence(candidate),
        "source_unit_ids": _source_unit_ids(candidate),
        "ambiguity": _ambiguities(_read(candidate, "ambiguity", "ambiguities", default=())),
        "epistemic_status": _status(
            _read(candidate, "epistemic_status", "status", "origin")
        ),
        "attributes": _attributes(_read(candidate, "attributes", default={})),
    }


def _normalize_edge(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": str(_read(candidate, "candidate_id", "edge_id", "id")),
        "relation": str(_read(candidate, "relation", "predicate", "kind")).strip(),
        "source_candidate_id": str(
            _read(candidate, "source_candidate_id", "source_node_id", "source_id")
        ),
        "target_candidate_id": str(
            _read(candidate, "target_candidate_id", "target_node_id", "target_id")
        ),
        "confidence": _confidence(candidate),
        "source_unit_ids": _source_unit_ids(candidate),
        "ambiguity": _ambiguities(_read(candidate, "ambiguity", "ambiguities", default=())),
        "epistemic_status": _status(
            _read(candidate, "epistemic_status", "status", "origin")
        ),
        "attributes": _attributes(_read(candidate, "attributes", default={})),
    }


def _read(value: Any, *names: str, default: Any = ...) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    if default is not ...:
        return default
    raise ValueError(f"required extraction field missing: {'/'.join(names)}")


def _source_unit_ids(value: Any) -> tuple[str, ...]:
    direct = _read(value, "source_unit_ids", "unit_ids", default=None)
    if direct is not None:
        return _string_tuple(direct)
    grounding = _read(value, "grounding", default=None)
    refs = (
        _read(grounding, "source_references", "source_refs", default=())
        if grounding is not None
        else _read(value, "source_refs", "source_references", default=())
    )
    unit_ids: list[str] = []
    for ref in refs:
        ref_value = _read(ref, "unit_id", "text_unit_id", "anchor_id", default=None)
        if ref_value:
            unit_ids.append(str(ref_value))
    return tuple(sorted(set(unit_ids)))


def _confidence(value: Any) -> float:
    confidence = _read(value, "confidence", default=1.0)
    return float(_read(confidence, "score", default=confidence))


def _ambiguities(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,)
    normalized: set[str] = set()
    for value in values:
        code = _read(value, "code", default=None)
        message = _read(value, "message", default=None)
        if code is not None:
            normalized.add(f"{code}:{message}" if message is not None else str(code))
        else:
            normalized.add(str(value))
    return tuple(sorted(normalized))


def _status(value: Any) -> EpistemicStatus:
    raw = getattr(value, "value", value)
    aliases = {"expressed": "explicit", "inferred": "semantic_inference"}
    return EpistemicStatus(aliases.get(str(raw), str(raw)))


def _attributes(value: Any) -> tuple[tuple[str, Any], ...]:
    if isinstance(value, Mapping):
        items: Iterable[tuple[Any, Any]] = value.items()
    else:
        items = value or ()
    return tuple(
        sorted(
            ((str(key), canonical_value(item)) for key, item in items),
            key=lambda pair: pair[0],
        )
    )


def _string_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,)
    return tuple(sorted({str(value) for value in values}))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

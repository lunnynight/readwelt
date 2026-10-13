"""Deterministic real-corpus manifest construction and preregistration gates."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "readwelt.articlegraph-agent-reading-manifest.v1"
PREREGISTRATION_SCHEMA = "readwelt.articlegraph-agent-reading-preregistration.v1"
DEFAULT_CATEGORIES = ("FOF与基金研究", "宏观量化与资产配置", "量化多因子选股")
_CJK = re.compile(r"[\u3400-\u9fff]")
_TERM = re.compile(r"[\u3400-\u9fff]{2,8}")
_CONCLUSION_TERMS = ("结论", "我们认为", "结果表明", "研究发现", "显示", "建议")
_EXCLUDED_TEXT = (
    "免责声明",
    "风险提示",
    "目录",
    "法律声明",
    "分析师声明",
    "市场有风险",
    "投资需谨慎",
    "不构成投资建议",
    "本报告所载",
    "本报告仅供",
    "本公司不对",
    "客户应考虑",
    "接收人收到本报告",
    "职业理解",
    "特此声明",
    "证券投资咨询业务资格",
    "请务必阅读正文之后的信息披露",
    "版权所有",
    "评级说明",
)


def build_preregistered_manifest(
    corpus_root: Path,
    *,
    categories: tuple[str, ...] = DEFAULT_CATEGORIES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    inventory_categories = tuple(
        path.name for path in sorted(corpus_root.iterdir()) if path.is_dir()
    )
    inventory, exclusions = _inventory(corpus_root, inventory_categories)
    size_threshold = _median([item["byte_size"] for item in inventory])
    density_threshold = _median([item["characters_per_page"] for item in inventory])
    for item in inventory:
        item["length_band"] = "long" if item["byte_size"] >= size_threshold else "short"
        item["extraction_quality_band"] = (
            "dense_native_text"
            if item["characters_per_page"] >= density_threshold
            else "sparse_native_text"
        )
    selected = _select_balanced(inventory, categories)
    documents = [_document_entry(index + 1, item) for index, item in enumerate(selected)]
    generated_at = datetime.now(UTC).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA,
        "experiment_id": "articlegraph-agent-reading-d1-v1",
        "scored": True,
        "frozen": True,
        "generated_at": generated_at,
        "corpus": {
            "name": "“海量”专题",
            "root": str(corpus_root.resolve()),
            "inventory_pdf_count": len(list(corpus_root.rglob("*.pdf"))),
            "selection_categories": list(categories),
            "length_threshold_bytes": size_threshold,
            "quality_threshold_characters_per_page": density_threshold,
            "selection_rule": "sha256 order; first two documents per category-length-quality cell",
        },
        "exclusion_criteria": [
            "unreadable_or_encrypted_pdf",
            "zero_pages",
            "zero_extractable_native_text",
            "duplicate_source_sha256",
            "fewer_than_three_exact_source_anchors",
        ],
        "exclusions": exclusions,
        "documents": documents,
    }
    manifest["manifest_digest"] = _digest(manifest)
    preregistration = {
        "schema_version": PREREGISTRATION_SCHEMA,
        "experiment_id": manifest["experiment_id"],
        "manifest_digest": manifest["manifest_digest"],
        "frozen_at": generated_at,
        "protocol_version": 1,
        "pilot_excluded_from_scoring": True,
        "protocol_correction_log_sha256": _file_digest(
            Path(__file__).with_name("d1") / "protocol-corrections.md"
        ),
        "analysis_code_digests": {
            name: _file_digest(Path(__file__).with_name(name))
            for name in (
                "manifest.py",
                "protocol.py",
                "validity.py",
                "scoring.py",
                "report.py",
                "runner.py",
            )
        },
        "product_code_digests": {
            "query_continuation.py": _file_digest(
                Path(__file__).parents[2]
                / "src"
                / "readwelt"
                / "article_graph"
                / "query_continuation.py"
            )
        },
        "hypotheses": {
            "location": "treatment location accuracy exceeds matched raw baseline",
            "comprehension": "treatment comprehension is non-inferior and preferably higher",
            "repeat_cost": "warm repeated treatment reading uses fewer input tokens",
            "trust": "every accepted treatment answer has replayable query receipts",
        },
        "primary_metrics": [
            "location_accuracy",
            "citation_precision",
            "comprehension_score",
            "warm_input_tokens",
        ],
        "release_thresholds": {
            "location_accuracy_absolute_gain": 0.10,
            "citation_precision_minimum": 0.95,
            "comprehension_absolute_gain": 0.05,
            "warm_input_token_reduction": 0.30,
            "valid_pair_rate": 0.95,
            "treatment_receipt_coverage": 1.0,
        },
        "matching_fields": [
            "document_id",
            "task_ids",
            "model",
            "model_settings",
            "answer_schema",
            "wall_clock_policy",
            "execution_policy",
        ],
        "analysis_policy": "paired descriptive metrics; invalid pairs excluded with reasons",
        "protocol_corrections_allowed": "pilot_only_before_scored_freeze",
    }
    preregistration["preregistration_digest"] = _digest(preregistration)
    validate_manifest(manifest)
    return manifest, preregistration


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("unsupported evaluation manifest schema")
    documents = manifest.get("documents")
    if not isinstance(documents, list) or len(documents) < 24:
        raise ValueError("scored manifest requires at least 24 documents")
    if manifest.get("manifest_digest") != _digest_without(manifest, "manifest_digest"):
        raise ValueError("evaluation manifest digest mismatch")
    ids: set[str] = set()
    digests: set[str] = set()
    cells: Counter[tuple[str, str, str]] = Counter()
    task_count = 0
    for document in documents:
        document_id = str(document.get("document_id", ""))
        source_digest = str(document.get("source_sha256", ""))
        if not document_id or document_id in ids:
            raise ValueError("document ids must be unique and non-empty")
        if not re.fullmatch(r"[0-9a-f]{64}", source_digest) or source_digest in digests:
            raise ValueError("source SHA-256 digests must be unique and valid")
        ids.add(document_id)
        digests.add(source_digest)
        cell = (
            str(document["category"]),
            str(document["length_band"]),
            str(document["extraction_quality_band"]),
        )
        cells[cell] += 1
        anchors = {item["anchor_id"]: item for item in document.get("gold_anchors", [])}
        tasks = document.get("tasks", [])
        if {item.get("kind") for item in tasks} != {"location", "citation", "comprehension"}:
            raise ValueError("each document requires location, citation, and comprehension tasks")
        for task in tasks:
            if task.get("gold_anchor_id") not in anchors:
                raise ValueError("task gold anchor does not resolve")
            rubric = task.get("rubric")
            if not isinstance(rubric, dict) or not rubric.get("scoring_rules"):
                raise ValueError("every task requires explicit scoring rules")
        task_count += len(tasks)
    if len({cell[0] for cell in cells}) < 3:
        raise ValueError("manifest requires at least three document categories")
    if any(count < 2 for count in cells.values()) or len(cells) < 12:
        raise ValueError("every represented category-length-quality cell requires two documents")
    if task_count < 72:
        raise ValueError("scored manifest requires at least 72 tasks")


def verify_manifest_sources(manifest: dict[str, Any]) -> None:
    """Replay immutable digests and exact page anchors against the source PDFs."""
    import fitz

    validate_manifest(manifest)
    for document_entry in manifest["documents"]:
        path = Path(document_entry["source_path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != document_entry["source_sha256"]:
            raise ValueError(f"source digest mismatch: {document_entry['document_id']}")
        document = fitz.open(path)
        try:
            for anchor in document_entry["gold_anchors"]:
                page_index = int(anchor["page"]) - 1
                if page_index < 0 or page_index >= len(document):
                    raise ValueError(f"gold page is out of bounds: {anchor['anchor_id']}")
                page_text = " ".join(document[page_index].get_text("text").split())
                if anchor["exact_text"] not in page_text:
                    raise ValueError(f"gold anchor does not replay: {anchor['anchor_id']}")
        finally:
            document.close()


def write_preregistration(corpus_root: Path, output: Path) -> tuple[Path, Path]:
    manifest, preregistration = build_preregistered_manifest(corpus_root)
    verify_manifest_sources(manifest)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    preregistration_path = output / "preregistration.json"
    manifest_path.write_text(_pretty(manifest), encoding="utf-8")
    preregistration_path.write_text(_pretty(preregistration), encoding="utf-8")
    return manifest_path, preregistration_path


def _inventory(
    corpus_root: Path, categories: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    import fitz

    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    seen: set[str] = set()
    for category in categories:
        for path in sorted((corpus_root / category).rglob("*.pdf")):
            source_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if source_digest in seen:
                exclusions.append(
                    {"source_path": str(path.resolve()), "reason": "duplicate_source_sha256"}
                )
                continue
            try:
                document = fitz.open(path)
                pages = [page.get_text("text") for page in document]
                document.close()
            except Exception as error:
                exclusions.append(
                    {
                        "source_path": str(path.resolve()),
                        "reason": f"unreadable_or_encrypted_pdf:{type(error).__name__}",
                    }
                )
                continue
            characters = sum(len(text) for text in pages)
            if not pages:
                exclusions.append(
                    {"source_path": str(path.resolve()), "reason": "zero_pages"}
                )
                continue
            if characters == 0:
                exclusions.append(
                    {
                        "source_path": str(path.resolve()),
                        "reason": "zero_extractable_native_text",
                    }
                )
                continue
            candidates = _anchor_candidates(pages)
            if len(candidates) < 3:
                exclusions.append(
                    {
                        "source_path": str(path.resolve()),
                        "reason": "fewer_than_three_exact_source_anchors",
                    }
                )
                continue
            seen.add(source_digest)
            rows.append(
                {
                    "category": category,
                    "source_path": str(path.resolve()),
                    "source_sha256": source_digest,
                    "byte_size": path.stat().st_size,
                    "page_count": len(pages),
                    "extracted_characters": characters,
                    "characters_per_page": round(characters / len(pages), 3),
                    "anchor_candidates": candidates,
                }
            )
    return rows, exclusions


def _select_balanced(
    inventory: list[dict[str, Any]], categories: tuple[str, ...]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for category in categories:
        for length in ("short", "long"):
            for quality in ("sparse_native_text", "dense_native_text"):
                cell = sorted(
                    (
                        item
                        for item in inventory
                        if item["category"] == category
                        and item["length_band"] == length
                        and item["extraction_quality_band"] == quality
                    ),
                    key=lambda item: item["source_sha256"],
                )
                if len(cell) < 2:
                    raise ValueError(
                        f"insufficient corpus documents for {category}/{length}/{quality}"
                    )
                selected.extend(cell[:2])
    return selected


def _document_entry(index: int, item: dict[str, Any]) -> dict[str, Any]:
    document_id = f"d{index:03d}-{item['source_sha256'][:12]}"
    candidates = item["anchor_candidates"][:3]
    anchors = [
        {
            "anchor_id": f"{document_id}-a{position}",
            "page": candidate["page"],
            "start_offset": candidate["start_offset"],
            "end_offset": candidate["end_offset"],
            "exact_text": candidate["exact_text"],
            "text_sha256": hashlib.sha256(candidate["exact_text"].encode()).hexdigest(),
        }
        for position, candidate in enumerate(candidates, start=1)
    ]
    tasks = _tasks(document_id, anchors)
    return {
        **{key: value for key, value in item.items() if key != "anchor_candidates"},
        "document_id": document_id,
        "gold_annotation_method": "deterministic_exact_source_match.v1",
        "gold_anchors": anchors,
        "tasks": tasks,
    }


def _tasks(document_id: str, anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Candidate order is evidence-strength order. Reserve the strongest passage
    # for comprehension, the next for citation, and use the third as the locator.
    comprehension, citation, location = anchors
    quote = location["exact_text"][:80]
    required_terms = _required_terms(comprehension["exact_text"])
    return [
        {
            "task_id": f"{document_id}-location",
            "kind": "location",
            "question": f"原文片段“{quote}”位于报告第几页？",
            "gold_anchor_id": location["anchor_id"],
            "expected_answer": str(location["page"]),
            "rubric": {"max_score": 1, "scoring_rules": ["page_exact_match"]},
        },
        {
            "task_id": f"{document_id}-citation",
            "kind": "citation",
            "question": "请给出报告中一条可直接支持其研究判断的原文证据并标注页码。",
            "gold_anchor_id": citation["anchor_id"],
            "expected_answer": citation["exact_text"],
            "rubric": {
                "max_score": 1,
                "scoring_rules": ["exact_or_containing_quote", "page_matches_gold_anchor"],
            },
        },
        {
            "task_id": f"{document_id}-comprehension",
            "kind": "comprehension",
            "question": "这份报告明确表达的一项核心研究判断是什么？请概括并引用原文证据。",
            "gold_anchor_id": comprehension["anchor_id"],
            "expected_answer": comprehension["exact_text"],
            "rubric": {
                "max_score": 2,
                "required_terms": required_terms,
                "scoring_rules": [
                    "one_point_for_supported_core_judgment",
                    "one_point_for_gold_or_equivalent_source_anchor",
                ],
            },
        },
    ]


def _anchor_candidates(pages: list[str]) -> list[dict[str, Any]]:
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for page_number, raw_page_text in enumerate(pages, start=1):
        if len(pages) > 4 and page_number > len(pages) - 2:
            continue
        page_text = " ".join(raw_page_text.split())
        for match in re.finditer(r"[^。！？；]{45,320}[。！？；]", page_text):
            text = match.group(0).strip()
            if not 45 <= len(text) <= 320 or len(_CJK.findall(text)) < 25:
                continue
            if any(marker in text for marker in _EXCLUDED_TEXT):
                continue
            if "...." in text or "……" in text:
                continue
            score = sum(8 for marker in _CONCLUSION_TERMS if marker in text)
            score += min(len(text), 180) // 30
            score += 3 if re.search(r"\d", text) else 0
            # Title/cover and boilerplate tail pages are useful for navigation but
            # poor gold evidence for research comprehension.
            if page_number == 1:
                score -= 8
            if page_number > max(2, int(len(pages) * 0.9)):
                score -= 8
            candidates.append(
                (
                    score,
                    -page_number,
                    {
                        "page": page_number,
                        "start_offset": match.start(),
                        "end_offset": match.end(),
                        "exact_text": text,
                    },
                )
            )
    ordered = sorted(candidates, key=lambda item: (-item[0], item[1], item[2]["exact_text"]))
    selected: list[dict[str, Any]] = []
    # Prefer page diversity, then backfill from strong paragraphs on an already
    # selected page when a short report has fewer than eight substantive pages.
    for _, _, candidate in ordered:
        if candidate["exact_text"] in {item["exact_text"] for item in selected}:
            continue
        if candidate["page"] in {item["page"] for item in selected}:
            continue
        selected.append(candidate)
        if len(selected) == 8:
            return selected
    for _, _, candidate in ordered:
        if candidate["exact_text"] in {item["exact_text"] for item in selected}:
            continue
        selected.append(candidate)
        if len(selected) == 8:
            return selected
    return selected


def _required_terms(text: str) -> list[str]:
    terms = [item for item in _TERM.findall(text) if item not in _EXCLUDED_TEXT]
    return list(dict.fromkeys(terms))[:4]


def _median(values: list[float | int]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def _pretty(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _digest(value: dict[str, Any]) -> str:
    return _digest_without(value, "")


def _digest_without(value: dict[str, Any], key: str) -> str:
    payload = {name: item for name, item in value.items() if name != key}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


__all__ = [
    "SCHEMA",
    "build_preregistered_manifest",
    "validate_manifest",
    "verify_manifest_sources",
    "write_preregistration",
]

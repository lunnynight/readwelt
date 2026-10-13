"""Deterministic task scoring against frozen page-and-quote gold anchors."""

from __future__ import annotations

from typing import Any


def score_answers(document: dict[str, Any], final_answer: dict[str, Any]) -> dict[str, float]:
    answers = {
        str(item.get("task_id")): item
        for item in final_answer.get("answers", [])
        if isinstance(item, dict)
    }
    anchors = {item["anchor_id"]: item for item in document["gold_anchors"]}
    scores = {"location": 0.0, "citation": 0.0, "comprehension": 0.0}
    for task in document["tasks"]:
        answer = answers.get(task["task_id"], {})
        anchor = anchors[task["gold_anchor_id"]]
        kind = task["kind"]
        if kind == "location":
            scores[kind] = float(_page(answer) == int(anchor["page"]))
        elif kind == "citation":
            quote = _normalized(str(answer.get("quote", "")))
            gold = _normalized(str(anchor["exact_text"]))
            scores[kind] = float(
                _page(answer) == int(anchor["page"])
                and bool(quote)
                and (quote in gold or gold in quote)
            )
        elif kind == "comprehension":
            answer_text = _normalized(str(answer.get("answer", "")))
            quote = _normalized(str(answer.get("quote", "")))
            gold = _normalized(str(anchor["exact_text"]))
            terms = [str(item) for item in task["rubric"].get("required_terms", [])]
            supported_judgment = bool(answer_text) and sum(
                term in answer_text or term in quote for term in terms
            ) >= min(2, len(terms))
            supported_quote = bool(quote) and (quote in gold or gold in quote)
            scores[kind] = float(supported_judgment) + float(supported_quote)
    return scores


def _page(answer: dict[str, Any]) -> int | None:
    value = answer.get("page")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _normalized(text: str) -> str:
    return "".join(text.split())


__all__ = ["score_answers"]

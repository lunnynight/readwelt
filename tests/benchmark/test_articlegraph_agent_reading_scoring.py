from __future__ import annotations

from benchmarks.articlegraph_agent_reading.scoring import score_answers


def _case(answer: str, quote: str) -> tuple[dict[str, object], dict[str, object]]:
    document = {
        "gold_anchors": [{"anchor_id": "a", "page": 4, "exact_text": "共同生产形成社会力量。"}],
        "tasks": [
            {
                "task_id": "c",
                "kind": "comprehension",
                "gold_anchor_id": "a",
                "rubric": {"required_terms": ["共同生产", "社会力量"]},
            }
        ],
    }
    response = {"answers": [{"task_id": "c", "answer": answer, "quote": quote, "page": 4}]}
    return document, response


def test_quote_terms_do_not_substitute_for_an_answer() -> None:
    document, response = _case("这段谈的是自由贸易政策。", "共同生产形成社会力量。")
    scores = score_answers(document, response)
    assert scores["comprehension_lexical_screen"] == 0.0
    assert "comprehension" not in scores


def test_keyword_only_response_gets_only_partial_lexical_credit() -> None:
    document, response = _case("共同生产与社会力量是两个关键词。", "共同生产形成社会力量。")
    assert score_answers(document, response)["comprehension_lexical_screen"] == 1.0


def test_short_quote_substring_does_not_count_as_supported_citation() -> None:
    document = {
        "gold_anchors": [{"anchor_id": "a", "page": 4, "exact_text": "共同生产形成社会力量。"}],
        "tasks": [{"task_id": "c", "kind": "citation", "gold_anchor_id": "a", "rubric": {}}],
    }
    response = {"answers": [{"task_id": "c", "quote": "共同生产", "page": 4}]}
    assert score_answers(document, response)["citation"] == 0.0


def test_valid_answer_gets_lexical_screen_credit_not_semantic_certification() -> None:
    document, response = _case("文本说共同生产形成社会力量。", "共同生产形成社会力量。")
    assert score_answers(document, response)["comprehension_lexical_screen"] == 1.0

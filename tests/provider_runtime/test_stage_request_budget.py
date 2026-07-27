from __future__ import annotations

from readwelt.providers import StageRequest
from readwelt.providers.request_budget import (
    serialized_request_tokens,
    settle_stage_request,
    stage_request_material_page,
)


def test_complete_stage_request_is_authoritatively_settled_and_recoverable() -> None:
    anchors = tuple(
        {
            "anchor_id": f"anchor-{index:03d}",
            "section_id": f"section-{index:03d}",
            "start_offset": index * 200,
            "end_offset": (index + 1) * 200,
            "exact_text": f"Evidence {index:03d} " + "x" * 180,
        }
        for index in range(80)
    )
    hits = tuple(
        {
            "anchor_id": item["anchor_id"],
            "section_id": item["section_id"],
            "lexical_rank": index,
            "lexical_score": 1.0 / (index + 1),
        }
        for index, item in enumerate(anchors)
    )
    request = StageRequest(
        schema_version="1",
        run_id="run-budget",
        stage="stage_1_mainline",
        evidence_packet={
            "anchors": anchors,
            "retrieval_hits": hits,
            "upstream_claims": tuple(
                {
                    "claim_id": f"claim-{index:03d}",
                    "text": "upstream " + "y" * 100,
                    "anchor_ids": [anchors[index]["anchor_id"]],
                }
                for index in range(40)
            ),
            "external_evidence": tuple(f"external-{index}" for index in range(40)),
            "omitted_anchor_ids": tuple(f"omitted-{index}" for index in range(80)),
            "omitted_sections": tuple(f"section-{index}" for index in range(80)),
            "stage_view": {
                "schema_version": "stage-view.v2",
                "content_digest": f"sha256:{'a' * 64}",
            },
        },
        response_schema={"type": "object", "properties": {}},
        provenance={"provider": "fixture"},
    )
    critical_anchor = anchors[-1]["anchor_id"]

    settled = settle_stage_request(
        request,
        hard_serialized_token_budget=8_000,
        critical_anchor_ids=(critical_anchor,),
    )
    mapping = settled.to_dict()

    assert settled.estimated_serialized_tokens == serialized_request_tokens(mapping)
    assert settled.estimated_serialized_tokens <= 8_000
    provider_input = mapping["budget_manifest"]["provider_input"]
    assert provider_input["max_tokens"] <= 8_000
    assert provider_input["receipts"][0]["mode"] == "conservative_upper_bound"
    assert (
        provider_input["receipts"][0]["counter_id"] == "readwelt.utf8_bytes.max_1_token_per_byte.v1"
    )
    assert mapping["response_schema"] == request.response_schema
    assert mapping["provenance"]["request_digest"].startswith("sha256:")
    anchor_page = mapping["evidence_packet"]["anchors"]
    assert anchor_page["critical_count"] == 1
    assert anchor_page["critical_presented_count"] == 1
    assert anchor_page["items"][0]["anchor_id"] == critical_anchor

    recovered = list(anchor_page["items"])
    cursor = anchor_page["next_cursor"]
    while cursor is not None:
        page = stage_request_material_page(
            "anchors",
            anchors,
            cursor=cursor,
            limit=11,
            critical_anchor_ids=(critical_anchor,),
        )
        recovered.extend(page["items"])
        cursor = page["next_cursor"]
    assert len(recovered) == len(anchors)
    assert {item["anchor_id"] for item in recovered} == {item["anchor_id"] for item in anchors}

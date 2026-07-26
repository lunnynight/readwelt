from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

mcp = pytest.importorskip("mcp")


def _payload(result: Any) -> dict[str, Any]:
    assert not result.isError
    value = json.loads(result.content[0].text)
    assert isinstance(value, dict)
    return value


def test_real_stdio_agent_session_completes_without_internal_provider(
    tmp_path: Path,
) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    source = tmp_path / "article.txt"
    source.write_text("第一段提出主张。\n\n第二段说明限制。", encoding="utf-8")
    project = tmp_path / ".readwelt"

    async def run_session() -> dict[str, Any]:
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-c",
                "from readwelt.mcp.server import main; main()",
                "--project",
                str(project),
            ],
            cwd=Path.cwd(),
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            assert {
                "start_agent_reading",
                "get_agent_turn",
                "submit_agent_turn",
            }.issubset(names)
            turn = _payload(
                await session.call_tool(
                    "start_agent_reading",
                    {
                        "source": str(source),
                        "idempotency_key": "stdio-agent-session",
                    },
                )
            )
            for expected_stage in (
                "stage_1_mainline",
                "stage_2_structure",
                "stage_3_decompression",
                "stage_4_author_model",
                "stage_5_boundaries",
                "stage_6_transfer",
            ):
                assert turn["stage"] == expected_stage
                request = turn["request"]
                anchors = request["evidence_packet"]["anchors"]
                upstream = request["evidence_packet"]["upstream_claims"]
                claims = []
                for index in range(2 if expected_stage == "stage_4_author_model" else 1):
                    claim: dict[str, Any] = {
                        "claim_id": f"{expected_stage}:stdio:{index}",
                        "text": f"{expected_stage} claim {index}",
                        "anchor_ids": [anchors[0]["anchor_id"]],
                        "decision": "accepted",
                    }
                    if expected_stage not in (
                        "stage_1_mainline",
                        "stage_2_structure",
                    ):
                        claim["source_claim_ids"] = [upstream[0]["claim_id"]]
                    if expected_stage == "stage_4_author_model":
                        claim["provenance"] = {"interpretation_id": f"stdio-lens-{index}"}
                    claims.append(claim)
                turn = _payload(
                    await session.call_tool(
                        "submit_agent_turn",
                        {
                            "run_id": turn["run_id"],
                            "candidate": {
                                "claims": claims,
                                "gaps": [],
                                "warnings": [],
                            },
                            "agent_name": "generic-mcp-test-agent",
                            "model": "external-test-model",
                        },
                    )
                )
            return turn

    completed = asyncio.run(run_session())

    assert completed["action"] == "completed"
    assert completed["execution_status"] == "completed"
    assert {item["artifact_type"] for item in completed["outputs"]} == {
        "reading_bundle",
        "reader_report_markdown",
    }

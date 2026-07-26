"""Pure Markdown compiler for settled reverse-reading output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ._normalize import as_items, first_field, read_field, stable_identifier

_PUBLISHABLE_DECISIONS = frozenset({"accepted", "qualified"})
_UNRESOLVED_DECISIONS = frozenset({"contested", "underdetermined"})
_STAGE_ORDER = {
    "stage1": 1,
    "stage_1": 1,
    "1": 1,
    "mainline": 1,
    "stage2": 2,
    "stage_2": 2,
    "2": 2,
    "structure": 2,
    "stage3": 3,
    "stage_3": 3,
    "3": 3,
    "knowledge": 3,
    "stage4": 4,
    "stage_4": 4,
    "4": 4,
    "author_model": 4,
    "stage5": 5,
    "stage_5": 5,
    "5": 5,
    "boundaries": 5,
    "stage6": 6,
    "stage_6": 6,
    "6": 6,
    "transfer": 6,
}


@dataclass(frozen=True, slots=True)
class _PublishedClaim:
    claim_id: str
    statement: str
    stage: int
    claim_type: str
    decision: str
    limitations: tuple[str, ...]
    anchor_ids: tuple[str, ...]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _stage_number(value: Any) -> int:
    raw = _text(value).lower().replace("-", "_").replace(" ", "_")
    if raw in _STAGE_ORDER:
        return _STAGE_ORDER[raw]
    for digit in range(1, 7):
        if str(digit) in raw:
            return digit
    return 99


def _artifact_ref(value: Any) -> str | None:
    artifact_id = _text(first_field(value, ("artifact_id", "resource_uri", "path")))
    if not artifact_id:
        return None
    digest = _text(read_field(value, "content_digest"))
    return f"{artifact_id} ({digest})" if digest else artifact_id


def _claim_sources(bundle: Any) -> tuple[Any, ...]:
    claims = list(as_items(first_field(bundle, ("claims", "settled_claims"), ())))
    artifacts = as_items(first_field(bundle, ("stage_artifacts", "stages", "artifacts"), ()))
    for artifact in artifacts:
        claims.extend(as_items(first_field(artifact, ("claims", "accepted_claims"), ())))
    unique: dict[str, Any] = {}
    for claim in claims:
        claim_id = stable_identifier(claim, "claim_id", "id")
        if claim_id:
            unique.setdefault(claim_id, claim)
    return tuple(unique[key] for key in sorted(unique))


def _ledger_lines(bundle: Any) -> tuple[Any, ...]:
    ledger = first_field(bundle, ("ledger", "claim_ledger", "reading_claim_ledger"))
    return as_items(read_field(ledger, "lines", ()))


def _eligible_for_report(line: Any) -> bool:
    eligible = tuple(
        _text(item).lower() for item in as_items(read_field(line, "eligible_projections"))
    )
    if not eligible:
        return True
    return any(item in {"report", "markdown", "reader", "public"} for item in eligible)


def _published_claims(bundle: Any) -> tuple[_PublishedClaim, ...]:
    decisions: dict[str, Any] = {}
    for line in _ledger_lines(bundle):
        claim_id = stable_identifier(line, "claim_id", "id")
        decision = _text(read_field(line, "decision")).lower()
        if claim_id and decision in _PUBLISHABLE_DECISIONS and _eligible_for_report(line):
            decisions[claim_id] = line

    published: list[_PublishedClaim] = []
    for claim in _claim_sources(bundle):
        claim_id = stable_identifier(claim, "claim_id", "id")
        line = decisions.get(claim_id)
        if line is None:
            continue
        statement = _text(first_field(claim, ("statement", "text", "content", "summary")))
        if not statement:
            continue
        stage = _stage_number(first_field(claim, ("stage_created", "stage", "origin_stage")))
        limitations = tuple(
            _text(item)
            for item in (
                *as_items(read_field(claim, "limitations", ())),
                *as_items(read_field(line, "limitations", ())),
            )
            if _text(item)
        )
        anchor_ids = tuple(
            sorted(
                {
                    _text(item)
                    for item in as_items(
                        first_field(claim, ("span_anchor_ids", "anchor_ids", "anchors"), ())
                    )
                    if _text(item)
                }
            )
        )
        published.append(
            _PublishedClaim(
                claim_id=claim_id,
                statement=statement,
                stage=stage,
                claim_type=_text(read_field(claim, "claim_type")),
                decision=_text(read_field(line, "decision")).lower(),
                limitations=limitations,
                anchor_ids=anchor_ids,
            )
        )
    return tuple(sorted(published, key=lambda item: (item.stage, item.claim_id)))


def _bullet(claim: _PublishedClaim) -> str:
    qualifier = "（有限定）" if claim.decision == "qualified" else ""
    anchors = f" [原文锚点：{', '.join(claim.anchor_ids)}]" if claim.anchor_ids else ""
    limitations = (
        f" 限制：{'；'.join(dict.fromkeys(claim.limitations))}" if claim.limitations else ""
    )
    statement = claim.statement
    if len(statement) > 1_200:
        statement = f"大文本 claim `{claim.claim_id}`（完整内容见 canonical bundle artifact）"
    return f"- {statement}{qualifier}{anchors}{limitations}"


def _claim_block(claims: Iterable[_PublishedClaim], *, empty: str) -> list[str]:
    rendered = [_bullet(claim) for claim in claims]
    return rendered or [f"- {empty}"]


def _claims_for_stage(
    claims: tuple[_PublishedClaim, ...],
    *stages: int,
) -> tuple[_PublishedClaim, ...]:
    return tuple(item for item in claims if item.stage in stages)


def _title(bundle: Any) -> str:
    direct = _text(first_field(bundle, ("title", "document_title")))
    if direct:
        return direct
    snapshot = first_field(bundle, ("snapshot", "source_snapshot", "document"))
    snapshot_title = _text(first_field(snapshot, ("title", "name", "source_name")))
    if snapshot_title:
        return snapshot_title
    snapshot_id = _text(first_field(bundle, ("snapshot_id", "document_id")))
    return f"逆向阅读：{snapshot_id}" if snapshot_id else "未命名文章"


def _render_gaps(bundle: Any) -> list[str]:
    gaps = list(as_items(first_field(bundle, ("gaps", "unresolved_gaps"), ())))
    for artifact in as_items(first_field(bundle, ("stage_artifacts", "stages", "artifacts"), ())):
        gaps.extend(as_items(read_field(artifact, "gaps", ())))
    unique: dict[str, Any] = {}
    for gap in gaps:
        gap_id = stable_identifier(gap, "gap_id", "id") or repr(gap)
        unique.setdefault(gap_id, gap)
    result: list[str] = []
    for gap_id in sorted(unique):
        gap = unique[gap_id]
        description = _text(first_field(gap, ("description", "message", "summary")))
        status = _text(read_field(gap, "status"))
        if not status and read_field(gap, "resolved") is not None:
            status = "resolved" if bool(read_field(gap, "resolved")) else "open"
        kind = _text(read_field(gap, "kind"))
        label = " / ".join(part for part in (kind, status) if part)
        label_suffix = f"（{label}）" if label else ""
        result.append(f"- `{gap_id}`{label_suffix}：{description or '未提供说明'}")
    return result or ["- 未记录缺口。"]


def _render_unresolved(bundle: Any) -> list[str]:
    rows: list[str] = []
    for line in sorted(
        _ledger_lines(bundle),
        key=lambda value: stable_identifier(value, "claim_id", "id"),
    ):
        decision = _text(read_field(line, "decision")).lower()
        if decision not in _UNRESOLVED_DECISIONS:
            continue
        claim_id = stable_identifier(line, "claim_id", "id")
        limitations = "；".join(
            _text(item) for item in as_items(read_field(line, "limitations")) if _text(item)
        )
        label = "存在竞争、尚未结算" if decision == "contested" else "证据不足、无法确定"
        rows.append(f"- `{claim_id}`：{label}{f'；{limitations}' if limitations else ''}")
    return rows or ["- 没有 contested / underdetermined ledger line。"]


def _anchor_index(bundle: Any) -> dict[str, Any]:
    anchors = list(as_items(first_field(bundle, ("anchors", "span_anchors"), ())))
    snapshot = first_field(bundle, ("snapshot", "source_snapshot", "document"))
    anchors.extend(as_items(first_field(snapshot, ("anchors", "span_anchors"), ())))
    return {
        stable_identifier(anchor, "anchor_id", "id"): anchor
        for anchor in anchors
        if stable_identifier(anchor, "anchor_id", "id")
    }


def _render_anchors(bundle: Any, claims: tuple[_PublishedClaim, ...]) -> list[str]:
    index = _anchor_index(bundle)
    used = sorted({anchor_id for claim in claims for anchor_id in claim.anchor_ids})
    rows: list[str] = []
    for anchor_id in used:
        anchor = index.get(anchor_id)
        if anchor is None:
            rows.append(f"- `{anchor_id}`：通过 bundle 的 anchor resource 读取。")
            continue
        exact = _text(read_field(anchor, "exact_text"))
        page = read_field(anchor, "page")
        section = _text(read_field(anchor, "section_id"))
        location = "，".join(
            part
            for part in (
                f"页 {page}" if page else "",
                f"段 {section}" if section else "",
            )
            if part
        )
        if len(exact) > 280:
            exact = f"{exact[:277]}…（完整原文通过 `{anchor_id}` artifact 读取）"
        location_suffix = f"（{location}）" if location else ""
        rows.append(f"- `{anchor_id}`{location_suffix}：{exact or '原文见 anchor artifact'}")
    return rows or ["- 已发布 claim 未携带原文锚点。"]


def _render_provenance(bundle: Any) -> list[str]:
    records = list(as_items(first_field(bundle, ("provider_provenance", "provenance"), ())))
    for artifact in as_items(first_field(bundle, ("stage_artifacts", "stages", "artifacts"), ())):
        if first_field(artifact, ("provider", "model", "agent")) is not None:
            records.append(artifact)
        records.extend(as_items(first_field(artifact, ("model_invocations", "provenance"), ())))
    flattened: list[Any] = []
    for record in records:
        if isinstance(record, Mapping) and not any(
            key in record for key in ("provider", "model", "agent", "invocation_id")
        ):
            flattened.extend(record.values())
        else:
            flattened.append(record)
    rows: set[str] = set()
    for record in flattened:
        if isinstance(record, (tuple, list)) and len(record) == 2:
            record = {str(record[0]): record[1]}
        provider = _text(first_field(record, ("provider", "provider_kind", "agent"), "unknown"))
        model = _text(first_field(record, ("model", "model_id", "model_name")))
        invocation = _text(first_field(record, ("invocation_id", "request_id", "candidate_id")))
        parts = [f"provider={provider}"]
        if model:
            parts.append(f"model={model}")
        if invocation:
            parts.append(f"id={invocation}")
        rows.add("- " + "；".join(parts))
    return sorted(rows) or ["- 本次 bundle 未记录模型或外部 Agent 调用。"]


def render_reader_markdown(bundle: Any) -> str:
    """Compile a Chinese reader report without inference or model calls."""

    claims = _published_claims(bundle)
    stage1 = _claims_for_stage(claims, 1)
    stage2 = _claims_for_stage(claims, 2)
    stage3 = _claims_for_stage(claims, 3)
    stage4 = _claims_for_stage(claims, 4)
    stage5 = _claims_for_stage(claims, 5)
    stage6 = _claims_for_stage(claims, 6)
    sections: list[tuple[str, list[str]]] = [
        ("文章是什么", _claim_block(stage1, empty="尚无通过 ledger 的文章定位。")),
        ("核心思想", _claim_block(stage1, empty="尚无通过 ledger 的主线结论。")),
        ("核心问题", _claim_block(stage1, empty="尚无通过 ledger 的核心问题。")),
        ("论点与论据", _claim_block(stage2, empty="尚无通过 ledger 的论证结构。")),
        ("文章逻辑链", _claim_block(stage2, empty="尚无通过 ledger 的结构结论。")),
        ("文章背后的世界", _claim_block(stage3, empty="尚无通过 ledger 的知识解压结果。")),
        (
            "作者的思想模型",
            [
                "- 作者模型 / 竞争解释（仅展示已结算项）：",
                *_claim_block(stage4, empty="尚无通过 ledger 的作者模型或竞争解释。"),
            ],
        ),
        ("隐含假设与限制", _claim_block(stage5, empty="尚无通过 ledger 的边界结论。")),
        ("可迁移原则", _claim_block(stage6, empty="尚无通过 ledger 的迁移原则。")),
    ]
    lines = [f"# {_title(bundle)}", "", "> Readwelt 六阶段逆向阅读报告（由已结算产物确定性编译）"]
    for heading, body in sections:
        lines.extend(("", f"## {heading}", "", *body))
    lines.extend(("", "## 附录：审计信息"))
    for heading, body in (
        ("缺口与未决项", [*_render_gaps(bundle), *_render_unresolved(bundle)]),
        ("原文锚点", _render_anchors(bundle, claims)),
        ("Provider provenance", _render_provenance(bundle)),
    ):
        lines.extend(("", f"### {heading}", "", *body))
    lines.append("")
    return "\n".join(lines)

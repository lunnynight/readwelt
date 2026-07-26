from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from readwelt.projections import render_reader_markdown


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    stage: str
    anchor_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Line:
    claim_id: str
    decision: str
    limitations: tuple[str, ...] = ()
    eligible_projections: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ledger:
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class Gap:
    gap_id: str
    kind: str
    description: str
    status: str = "open"


@dataclass(frozen=True)
class Anchor:
    anchor_id: str
    exact_text: str
    section_id: str
    page: int | None = None


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    stage: str
    claims: tuple[Claim, ...]
    gaps: tuple[Gap, ...] = ()
    provider: str | None = None
    model: str | None = None
    provenance: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Bundle:
    run_id: str
    snapshot_id: str
    artifacts: tuple[Artifact, ...]
    ledger: Ledger
    anchors: tuple[Anchor, ...]
    title: str = "测试文章"
    transitions: tuple[object, ...] = field(default_factory=tuple)


def _bundle() -> Bundle:
    claims = (
        Claim("c1", "文章以实践检验认识。", "stage_1_mainline", ("a1",)),
        Claim("c2", "论证由问题、反例和结论组成。", "stage_2_structure", ("a2",)),
        Claim("c3", "这里的实践包含社会行动。", "stage_3_decompression"),
        Claim("c4", "作者采用动态认识模型。", "stage_4_author_model"),
        Claim("c5", "结论依赖可反馈的实践条件。", "stage_5_boundaries"),
        Claim("c6", "可迁移为迭代验证原则。", "stage_6_transfer"),
        Claim("c7", "这个被拒绝的句子绝不能出现。", "stage_4_author_model"),
        Claim("c8", "这个未决句子也不能出现。", "stage_4_author_model"),
    )
    lines = (
        Line("c1", "accepted"),
        Line("c2", "qualified", ("仅适用于正文论证",)),
        Line("c3", "accepted"),
        Line("c4", "accepted"),
        Line("c5", "accepted"),
        Line("c6", "accepted"),
        Line("c7", "rejected"),
        Line("c8", "underdetermined", ("缺少作者书信",)),
    )
    return Bundle(
        run_id="run-1",
        snapshot_id="snapshot-1",
        artifacts=(
            Artifact(
                artifact_id="artifact-stage-1-6",
                stage="stage_1_mainline",
                claims=claims,
                gaps=(
                    Gap(
                        gap_id="gap-1",
                        kind="attribution_ambiguity",
                        description="一个引文的归属尚不明确。",
                    ),
                ),
                provider="local",
                model="gte-test",
            ),
        ),
        ledger=Ledger(lines),
        anchors=(
            Anchor("a1", "实践是检验真理的标准。", "s1", 1),
            Anchor("a2", "认识必须回到实践。", "s2", 2),
        ),
    )


def test_report_contains_all_reader_surfaces_and_provenance() -> None:
    report = render_reader_markdown(_bundle())

    for heading in (
        "文章是什么",
        "核心思想",
        "核心问题",
        "论点与论据",
        "文章逻辑链",
        "文章背后的世界",
        "作者的思想模型",
        "隐含假设与限制",
        "可迁移原则",
    ):
        assert f"## {heading}" in report
    assert "## 附录：审计信息" in report
    for heading in ("缺口与未决项", "原文锚点", "Provider provenance"):
        assert f"### {heading}" in report

    assert "文章以实践检验认识。" in report
    assert "论证由问题、反例和结论组成。" in report
    assert "这里的实践包含社会行动。" in report
    assert "作者采用动态认识模型。" in report
    assert "结论依赖可反馈的实践条件。" in report
    assert "可迁移为迭代验证原则。" in report
    assert "实践是检验真理的标准。" in report
    assert "attribution_ambiguity" in report
    assert "provider=local；model=gte-test" in report


def test_report_never_publishes_non_settled_claim_text() -> None:
    report = render_reader_markdown(_bundle())

    assert "这个被拒绝的句子绝不能出现。" not in report
    assert "这个未决句子也不能出现。" not in report
    assert "`c8`：证据不足、无法确定；缺少作者书信" in report
    assert "`c7`" not in report


def test_report_is_byte_for_byte_deterministic() -> None:
    bundle = _bundle()
    encoded = render_reader_markdown(bundle).encode()
    assert encoded == render_reader_markdown(bundle).encode()
    assert hashlib.sha256(encoded).hexdigest() == (
        "9bd5facb6b7169cc48793ffaf700bd569"  # pragma: allowlist secret
        "c9aa03db6938264dd1831454c59c13c"  # pragma: allowlist secret
    )


def test_claim_without_ledger_line_is_withheld() -> None:
    bundle = _bundle()
    extra = Claim("unsettled", "不能绕过 ledger。", "stage_1_mainline")
    artifact = bundle.artifacts[0]
    changed = Bundle(
        run_id=bundle.run_id,
        snapshot_id=bundle.snapshot_id,
        artifacts=(
            Artifact(
                artifact_id=artifact.artifact_id,
                stage=artifact.stage,
                claims=(*artifact.claims, extra),
                gaps=artifact.gaps,
                provider=artifact.provider,
                model=artifact.model,
            ),
        ),
        ledger=bundle.ledger,
        anchors=bundle.anchors,
    )

    assert "不能绕过 ledger。" not in render_reader_markdown(changed)

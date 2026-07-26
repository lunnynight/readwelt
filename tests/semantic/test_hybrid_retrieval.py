from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from readwelt.domain import (
    DocumentSection,
    LedgerDecision,
    ReadingClaim,
    ReadingStage,
    SourceDocumentSnapshot,
    SpanAnchor,
    stable_id,
)
from readwelt.semantic import (
    HybridRetriever,
    RetrievalPlan,
    SemanticPreprocessor,
    SentenceTransformerDenseEncoder,
    build_stage_retrieval_plan,
    configured_dense_encoder,
)


def _snapshot(parts: tuple[str, ...]) -> tuple[SourceDocumentSnapshot, str]:
    text = "\n".join(parts)
    snapshot_id = stable_id("snapshot", text)
    sections: list[DocumentSection] = []
    offset = 0
    for ordinal, part in enumerate(parts):
        section_id = stable_id("section", snapshot_id, str(ordinal))
        anchor = SpanAnchor.create(
            snapshot_id=snapshot_id,
            section_id=section_id,
            text=text,
            start_offset=offset,
            end_offset=offset + len(part),
        )
        sections.append(
            DocumentSection(
                section_id=section_id,
                title=None,
                start_offset=offset,
                end_offset=offset + len(part),
                anchor=anchor,
            )
        )
        offset += len(part) + 1
    return (
        SourceDocumentSnapshot(
            snapshot_id=snapshot_id,
            document_id=stable_id("document", text),
            schema_version="1",
            source_kind="text/plain",
            source_locator="article.txt",
            content_digest=f"sha256:{'1' * 64}",
            captured_at=datetime.now(UTC),
            language="zh",
            normalized_text_ref="objects/11/body",
            sections=tuple(sections),
        ),
        text,
    )


@dataclass
class _MeaningEncoder:
    provider: str = "test"
    model: str = "meaning-v1"
    revision: str = "1"
    dimensions: int = 2

    def encode_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._encode(text) for text in texts)

    def encode_queries(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._encode(text) for text in texts)

    @staticmethod
    def _encode(text: str) -> tuple[float, float]:
        if "价格" in text or "市场无效" in text:
            return (1.0, 0.0)
        return (0.0, 1.0)


def test_dense_channel_recovers_chinese_paraphrase_that_lexical_misses() -> None:
    snapshot, text = _snapshot(
        (
            "价格没有充分反映公开信息。",
            "市场举办古典音乐节并组织演出。",
        )
    )
    atlas = SemanticPreprocessor().prepare(snapshot, text)
    plan = RetrievalPlan(
        stage=ReadingStage.BOUNDARIES,
        queries=("市场无效",),
        token_budget=20,
    )

    lexical = HybridRetriever().retrieve(atlas, plan)
    hybrid = HybridRetriever(dense_encoder=_MeaningEncoder()).retrieve(atlas, plan)

    assert lexical.hits[0].anchor_id != atlas.segments[0].anchor.anchor_id
    assert hybrid.hits[0].anchor_id == atlas.segments[0].anchor.anchor_id
    assert hybrid.hits[0].dense_rank == 1
    assert hybrid.retrieval_backend == "rust-hybrid-rrf-v2"


def test_document_embeddings_are_reused_across_stage_queries() -> None:
    snapshot, text = _snapshot(("价格反映信息。", "音乐组织旋律。"))
    atlas = SemanticPreprocessor().prepare(snapshot, text)

    class CountingEncoder(_MeaningEncoder):
        document_calls = 0

        def encode_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            self.document_calls += 1
            return super().encode_documents(texts)

    encoder = CountingEncoder()
    retriever = HybridRetriever(dense_encoder=encoder)
    retriever.retrieve(
        atlas,
        RetrievalPlan(ReadingStage.MAINLINE, ("文章主线",), token_budget=8),
    )
    retriever.retrieve(
        atlas,
        RetrievalPlan(ReadingStage.BOUNDARIES, ("市场无效",), token_budget=8),
    )

    assert encoder.document_calls == 1


def test_full_coverage_skips_dense_work_and_preserves_source_order() -> None:
    snapshot, text = _snapshot(("价格反映信息。", "音乐组织旋律。"))
    atlas = SemanticPreprocessor().prepare(snapshot, text)

    class FailIfCalled(_MeaningEncoder):
        def encode_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            raise AssertionError("dense encoder should not run for a full-source packet")

    packet = HybridRetriever(dense_encoder=FailIfCalled()).retrieve(
        atlas,
        RetrievalPlan(ReadingStage.MAINLINE, ("文章主线",), token_budget=10_000),
    )

    assert packet.retrieval_backend == "full-coverage-v1"
    assert packet.coverage_complete
    assert tuple(anchor.anchor_id for anchor in packet.anchors) == tuple(
        segment.anchor.anchor_id for segment in atlas.segments
    )
    assert all(hit.dense_rank is None for hit in packet.hits)


def test_document_embeddings_are_reused_across_retriever_processes(tmp_path: Path) -> None:
    snapshot, text = _snapshot(("价格反映信息。", "音乐组织旋律。"))
    atlas = SemanticPreprocessor().prepare(snapshot, text)

    class CountingEncoder(_MeaningEncoder):
        document_calls = 0

        def encode_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            self.document_calls += 1
            return super().encode_documents(texts)

    encoder = CountingEncoder()
    plan = RetrievalPlan(ReadingStage.BOUNDARIES, ("市场无效",), token_budget=8)
    first = HybridRetriever(dense_encoder=encoder, cache_dir=tmp_path).retrieve(atlas, plan)
    second = HybridRetriever(dense_encoder=encoder, cache_dir=tmp_path).retrieve(atlas, plan)

    assert encoder.document_calls == 1
    assert first.hits == second.hits
    assert len(tuple(tmp_path.glob("*.f32"))) == 1
    assert len(tuple(tmp_path.glob("*.json"))) == 1


def test_corrupt_persistent_embedding_cache_is_rebuilt(tmp_path: Path) -> None:
    snapshot, text = _snapshot(("价格反映信息。", "音乐组织旋律。"))
    atlas = SemanticPreprocessor().prepare(snapshot, text)

    class CountingEncoder(_MeaningEncoder):
        document_calls = 0

        def encode_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            self.document_calls += 1
            return super().encode_documents(texts)

    encoder = CountingEncoder()
    plan = RetrievalPlan(ReadingStage.BOUNDARIES, ("市场无效",), token_budget=8)
    HybridRetriever(dense_encoder=encoder, cache_dir=tmp_path).retrieve(atlas, plan)
    next(tmp_path.glob("*.f32")).write_bytes(b"corrupt")

    packet = HybridRetriever(dense_encoder=encoder, cache_dir=tmp_path).retrieve(atlas, plan)

    assert encoder.document_calls == 2
    assert packet.hits[0].anchor_id == atlas.segments[0].anchor.anchor_id


def test_stage_plan_uses_settled_claims_without_losing_user_purpose() -> None:
    claim = ReadingClaim(
        claim_id="claim-1",
        text="公开信息未被价格充分吸收",
        stage=ReadingStage.MAINLINE,
        anchor_ids=("anchor-1",),
        decision=LedgerDecision.ACCEPTED,
    )

    plan = build_stage_retrieval_plan(
        ReadingStage.STRUCTURE,
        purpose="理解这篇文章的核心机制",
        token_budget=120,
        upstream_claims=(claim,),
    )

    assert plan.stage is ReadingStage.STRUCTURE
    assert plan.queries[0] == "理解这篇文章的核心机制"
    assert claim.text in plan.queries
    assert plan.source_claim_ids == (claim.claim_id,)
    assert any("论证结构" in query for query in plan.queries)


def test_retrieval_rejects_required_anchor_outside_atlas() -> None:
    snapshot, text = _snapshot(("价格反映信息。",))
    atlas = SemanticPreprocessor().prepare(snapshot, text)
    plan = RetrievalPlan(
        ReadingStage.STRUCTURE,
        ("论证结构",),
        token_budget=20,
        required_anchor_ids=("anchor:other-snapshot",),
    )

    with pytest.raises(ValueError, match="unknown anchor"):
        HybridRetriever().retrieve(atlas, plan)


def test_hybrid_packet_keeps_section_coverage_and_explicit_omissions() -> None:
    snapshot, text = _snapshot(
        (
            "市场价格可能遗漏公开信息。",
            "作者随后提出制度解释。",
            "最后给出适用边界。",
        )
    )
    atlas = SemanticPreprocessor().prepare(snapshot, text)

    packet = HybridRetriever(dense_encoder=_MeaningEncoder()).retrieve(
        atlas,
        RetrievalPlan(ReadingStage.BOUNDARIES, ("市场无效",), token_budget=9),
    )

    assert packet.estimated_tokens <= packet.token_budget
    assert packet.omitted
    assert len(packet.hits) == len(packet.anchors)
    assert {hit.anchor_id for hit in packet.hits} == {anchor.anchor_id for anchor in packet.anchors}
    assert not packet.coverage_complete


def test_local_encoder_is_opt_in_and_keeps_cache_inside_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("READWELT_DENSE_MODEL", raising=False)
    assert configured_dense_encoder(tmp_path) is None

    monkeypatch.setenv("READWELT_DENSE_MODEL", "auto")
    encoder = configured_dense_encoder(tmp_path)

    assert encoder is not None
    assert encoder.model == "Alibaba-NLP/gte-multilingual-base"
    assert str(tmp_path) in str(encoder._cache_dir)  # noqa: SLF001


def test_local_encoder_auto_selects_cuda_and_uses_asymmetric_methods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    class FakeRuntime:
        def __init__(self, model: str, **kwargs: object) -> None:
            calls.append(("load", (model, kwargs)))

        def encode_document(self, texts: list[str], **kwargs: object) -> list[list[float]]:
            calls.append(("document", (texts, kwargs)))
            return [[1.0, 0.0] for _ in texts]

        def encode_query(self, texts: list[str], **kwargs: object) -> list[list[float]]:
            calls.append(("query", (texts, kwargs)))
            return [[0.0, 1.0] for _ in texts]

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setitem(
        __import__("sys").modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeRuntime),
    )
    encoder = SentenceTransformerDenseEncoder(cache_dir=tmp_path, dimensions=2)

    assert encoder.encode_documents(("文档",)) == ((1.0, 0.0),)
    assert encoder.encode_queries(("查询",)) == ((0.0, 1.0),)
    load_kwargs = calls[0][1][1]  # type: ignore[index]
    assert load_kwargs["device"] == "cuda"
    assert calls[1][0] == "document"
    assert calls[2][0] == "query"

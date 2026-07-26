# ArticleGraph Foundation

`ArticleGraph` 是 Xberg 文档快照与 Completion Engine 之间、供 AI 消费的文章中间表示。它保存文章已经表达的内容、系统做出的可追溯推断和尚未解决的歧义，不承担最终理解或补全。

当前数据链：

```text
SourceDocumentSnapshot + normalized text
  -> AnchoredTextUnitSet + CoverageReport
  -> LinguisticBackend / SemanticExtractionBackend
  -> immutable GraphExtraction artifacts
  -> Canonicalizer
  -> ArticleGraph + MergeReport
  -> ProvenanceLedger + SourceIndex
  -> StageView
  -> six-stage reading engine
```

应用只调用：

```python
ArticleGraphBuilder.build(snapshot, normalized_text, policy=None)
```

返回的 `ArticleGraphBuildResult` 同时包含：

- revision-aware `AnchoredTextUnit` 和原文覆盖报告；
- 每个 backend 的原始 `GraphExtraction` 候选制品；
- 保留 Mention 的 canonical nodes、edges 和 claims；
- `MergeDecision`、`ConflictRecord` 与 `MergeReport`；
- 可持久化、可验链的独立 `ProvenanceLedgerArtifact`；
- Knowledge ↔ TextUnit 双向 `SourceIndex`；
- 区分 empty、unsupported、failed、partial、complete 的能力报告。

事实底账是 source snapshot、AnchoredTextUnit、raw extraction、merge/conflict records 和 provenance events。`ArticleGraph`、`SourceIndex`、`StageView` 都是带版本和 digest 的可重建投影。

核心不变量：

1. 所有非空白原文要么被 TextUnit 覆盖，要么显式记录为 unsupported/uncovered。
2. source-required 候选缺少有效 grounding 时 fail empty，不能猜造锚点。
3. 同名 mention 不是身份相同的充分证据；跨 source unit 默认 defer。
4. projection 和普通 ledger event 不能反向扩写事实 grounding。
5. explicit、linguistic inference、semantic inference、canonicalized、internal derived、external、synthesized 永久分离。
6. StageView 携带 graph、source-index、provenance-ledger digest 和每项选择理由。
7. BM25/dense 只能作为 StageView 的显式 locator，不能取代 ArticleGraph 或 Completion Engine。

当前内置 linguistic/semantic backend 是无外部模型依赖的确定性降级实现。HanLP、LTP、DeepKE 等后端将在后续变更中通过现有 seam 接入；缺少它们不会破坏文档导入和 ArticleGraph 构建。

完整规范位于 `openspec/changes/build-article-graph-foundation/`。

# ArticleGraph Architecture

`ArticleGraph` 是 Readwelt 的文章预处理 IR。它的任务不是替 AI 输出六阶段结论，而是以更少 token、更低定位不确定性和可追溯来源，帮助 AI 快速找到文章已经表达的结构、论证对象与原文证据。

## 当前边界

```text
Xberg primary ingestion
  + Docling PDF/OCR structural fallback when required
  ↓
Complete Source Plane
  - original source root
  - normalized ranges and gaps
  - AnchoredTextUnit
  - native source elements and structure
  ↓
GraphExtraction locating candidates
  - linguistic candidates
  - argument-locating semantic candidates
  ↓
Canonical ArticleGraph
  + MergeDecision / ConflictRecord
  + ProvenanceLedger / SourceIndex
  ↓
bounded StageView traversal
  ↓
six-stage AI candidate generation and settlement
  ↓
future CompletionPlan / Completion Engine
```

这条链路有三条不能混淆的边界：

1. Source Plane 保存来源本身；缺失、冲突和不支持能力必须显式记录。
2. ArticleGraph 保存 source-grounded locating candidates，不把机器抽取当成文章最终解释。
3. StageView 选择当前阶段需要的有限输入；六阶段 Agent 才负责理解、判断、反事实和迁移。

## Complete Source Plane

Source Plane 已不再只是 `AnchoredTextUnit`。当前制品同时保存：

- 原始文件字节对应的 source-document root；
- 可精确重建规范化文本的 range、gap 和 text unit；
- Xberg `nodes` 与 `elements` 的累计投影，而非二选一；
- backend-native identity、offset、reading order、parent/children、previous/next；
- table、figure、caption、page、geometry 和 raw-payload handle；
- range、element、structure、capability 四类覆盖记录；
- 不能可靠投影的元素、关系和能力缺口。

Xberg 仍是主入口。PDF 没有可用结构或文本时，固定版本的可选 Docling 后端可使用显式本地模型执行 layout/OCR；它遍历 groups、picture descendants 和全部 content layers，并保留 `content_layer` provenance。原始 PDF 始终仍是 source root。

## ArticleGraph 是定位层

`ArticleGraphBuilder` 接收完整 snapshot 并生成：

- immutable `GraphExtraction` 原始候选；
- mention、node、edge、claim 及其 source unit/range/element grounding；
- premise、conclusion、evidence、example、objection、qualification 等论证定位类型；
- support、refutation、causation、contrast、qualification 等关系候选；
- canonicalization 的 merge/defer/reject 决策、冲突和置信度；
- 可重建的 `SourceIndex` 与独立 provenance ledger。

这些对象都是“AI 应该去哪里看”的机器候选，不是 Stage 1–6 的最终理解。semantic backend 失败不得缩小 Source Plane；未知 native element 或无有效 grounding 的候选必须 fail empty，不能伪造锚点。

当前默认仍提供确定性 linguistic/semantic 降级路径。Stanza `1.14.0` 加固定 `zh-hans` 模型已作为可选生产 linguistic adapter 接入，模型不可用时显式降级；HanLP/PaddleNLP 未通过当前执行门禁，LTP 受模型许可边界限制，DeepKE 只作为 schema/output 参考。生产 OpenAI-compatible semantic adapter 实现了完整版本化论证定位 taxonomy 的严格输入、输出和 grounding 契约；只有满足该契约的宿主模型才能贡献候选。当前本机 `gemma3:1b` 配置 control 没有通过完整 taxonomy/grounding 能力门禁，因此它不是已采用的默认 semantic model；claim-only 路径继续被明确标记为 partial fallback。

## StageView 与六阶段

StageView 不是 ArticleGraph 的完整转储。它根据阶段、任务、SourceIndex、覆盖状态和预算选择：

- 原文切片及 source unit/range/element；
- 论证定位 candidates；
- 上游阶段已结算结论；
- 冲突、遗漏、blocking records 与 external evidence；
- continuation cursor 和 rescue 状态。

预算在最终 provider-bound StageRequest envelope 上结算，包括 StageView、anchors、retrieval hits、上游 claims、外部证据、instructions、response schema 和 request provenance。超大文本或非文本元素必须确定性切片或显式阻塞；长文不能退化为“全量塞给模型”。

六阶段当前拥有持久化状态、候选提交、引用结算、continuation 和真实 Claude Code provider seam。Codex、Gemini、OpenCode 仍是 host-neutral 协议目标，并非都已完成真实进程 E2E。Stage 输出通过 typed citations 回指 Source Plane/ArticleGraph，但绝不能反写成 source fact。

## 已完成的长文验收

真实 7-case corpus 覆盖中文和英文 TXT、HTML、native PDF、image-only scanned PDF、EPUB，以及超过 100,000 字符的文档。当前报告：

- 7/7 acceptance passed；
- unit、range、element、source-root coverage 均为 1.0；
- bounded continuation traversal 全部完成并遵守 hard budget；
- native/scanned PDF structural-reference closure 为真；
- lexical locating control 在最终 envelope 内满足 must-hit gate；
- dense、hybrid、reranking 只在相应后端启用时比较，不宣称未测量的固定节省比例。

权威报告是 `reports/articlegraph-long-document-acceptance-2026-07-27.json`；当前 digest 为 `sha256:25b905202e73d70f5d8ef52fa2a53f60b052ab9a0d1d3472591ca30e930a7622`。

## 仍未完成

ArticleGraph 基建和长文定位验收完成，不等于 Readwelt 产品已经完成。当前仍缺：

- `CompletionPlan` 契约；
- 理解缺口发现、研究调度和完成标准；
- 外部研究闭环；
- Codex、Gemini、OpenCode 等宿主的同合同真实 E2E；
- 用户修正驱动的补全策略优化。

因此当前准确描述是：Readwelt 已具备完整、可追溯、可分页的 ArticleGraph 定位底座，并正在从 ArticleGraph 基建期进入 Completion Engine 建设期。

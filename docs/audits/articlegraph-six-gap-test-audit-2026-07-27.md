# ArticleGraph 六项工程盘点与测试记录

日期：2026-07-27
范围：全输入预算、制品体积、真实 Agent 宿主、中文抽取后端、真实长文、CompletionPlan

这份记录已按 `harden-article-graph-source-plane` 的最终实现重新核对。早期审计中“只有 AnchoredTextUnit”“没有中文 backend”“没有真实 PDF/EPUB 长文验证”“预算只计算 selected text”等结论属于变更前基线，不再代表当前代码。

## 当前结论

| 项目 | 当前状态 | 已有证据 | 剩余边界 |
|---|---|---|---|
| 最终 provider 输入硬预算 | 已完成 | 对最终 StageRequest envelope 计数；continuation、blocking 和 oversized slicing 有回归门禁 | 不宣称与每个商业 provider tokenizer 完全等价；当前记录 exact tokenizer 或保守上界 |
| ArticleGraph 制品体积与去重 | 已完成当前门禁 | CAS unique bytes、aggregate bytes、rebuild reuse、peak memory、streaming read 已在 100k+ 文档测量 | 后续新增制品仍需维持相同门禁 |
| 真实 Agent 宿主 | 部分完成 | host-neutral Skill/CLI/HTTP/mailbox；真实 Claude Code provider 使用宿主认证并保存 receipt | Codex、Gemini、OpenCode 尚未完成同合同真实进程 E2E |
| 中文 linguistic backend | 已完成可选生产接入 | Stanza 1.14.0 + 固定 zh-hans 模型 adapter、grounding、lineage、显式降级 | 非默认；HanLP/PaddleNLP 未通过当前门禁，LTP 有许可边界，DeepKE 仅作参考 |
| PDF/EPUB/100k+ 长文验收 | 已完成 | 真实 7-case corpus，7/7 acceptance passed，完整 bounded traversal 和 hard-budget gate | 这是定位与来源可达性验收，不是六阶段理解质量 benchmark |
| CompletionPlan | 未实现 | 无可持久化 gap plan、research scheduling 或 completion criteria 契约 | 下一阶段核心产品工作 |

## 当前真实数据流

```text
Xberg + optional Docling fallback
  ↓
Complete Source Plane
  - source root bytes
  - normalized range/gap
  - AnchoredTextUnit
  - native source element/structure
  ↓
GraphExtraction locating candidates
  ↓
Canonical ArticleGraph + Merge/Conflict
  ↓
SourceIndex + ProvenanceLedger
  ↓
bounded StageView / final StageRequest envelope
  ↓
six-stage Agent candidate + settlement
```

ArticleGraph 的验收目标是帮助 AI 快速定位和拆解文章结构，不是替 AI 产出最终理解。机器抽取出的 premise、evidence、claim、support 等对象必须保留 candidate 身份、grounding、置信度和 provenance。六阶段结果属于后续 AI 结算层，不能反写成 source fact。

## 1. 最终输入预算

变更前只统计 selected text 或 StageView 的局部估算，不能约束实际 provider request。当前预算范围已经扩展到最终序列化 envelope：

- StageView；
- typed anchors 和 source citations；
- retrieval hits；
- upstream claims；
- external evidence；
- provider instructions；
- response schema；
- request provenance。

运行时在发送前重新计算最终 envelope。超预算时使用确定性切片、continuation 和 source-coverage rescue；无法安全容纳的单位产生 blocking record，不允许静默遗漏，也不允许长文回退为整篇注入。

长文 acceptance 同时记录 `token_budget` 与 `hard_serialized_token_budget`。lexical control 必须在最终 envelope 内保持 must-hit recall 1.0 和 critical-anchor miss 0.0，否则整个 case 失败。

## 2. Source Plane 与制品体积

Source Plane 现在包含：

- 原始文件 source-document root；
- 全规范化 range 与 gap；
- AnchoredTextUnit；
- text/non-text source element；
- native identity、raw payload、reading order、结构关系、page/geometry；
- range、element、structure、capability coverage manifest。

制品仍采用内容寻址存储，但验收不再只看逻辑 digest。100k+ case 已测量 aggregate artifact bytes、CAS unique bytes、deduplication ratio、rebuild reuse、build peak memory 和 bounded/streaming reads。历史 immutable artifact 通过语义解码和内部 digest/identity 校验读取；新 schema rebuild 不重写历史。

这意味着早期“小输入被重复嵌套序列化放大”的观测已成为历史基线，而不是当前未处理结论。后续 schema 扩展仍必须继续跑同一体积门禁。

## 3. Agent 宿主边界

当前已有 host-neutral 的 StageRequest/StageCandidate 合同、持久 mailbox、Skill、CLI 与 HTTP 接口。真实 Claude Code provider：

- 启动官方非交互 CLI；
- 复用宿主已有认证和模型配置；
- 不要求 Readwelt 保存独立 API key；
- 对每个 stage 保存 host/version/request receipt；
- 通过相同 typed candidate settlement 返回结果。

Codex、Gemini 和 OpenCode 可以消费 host-neutral 协议，但尚不能写成“全部真实宿主已验收”。下一步应使用同一篇 golden article、同一 StageRequest schema、相同六阶段 journey 和相同 receipt 字段做真实进程 E2E。

## 4. 中文抽取后端

当前生产路径已经超过单一 regex fallback，包括：

- 默认确定性 regex linguistic fallback；
- 可选 `StanzaLinguisticBackend`；
- 确定性 semantic fallback；
- 对满足严格 schema/grounding 契约的模型开放完整版本化论证定位 taxonomy 的生产 semantic adapter。

Stanza adapter 固定 package/model revision，使用已下载的本地模型，恢复 source offsets，并把 sentence、token、entity、dependency 等输出作为 linguistic locating candidates。模型或可选依赖不可用时生成明确 capability outcome，不降低 Source Plane reachability。

OpenAI-compatible semantic adapter 的 schema、offset/text grounding、未知 taxonomy fail-empty 和完整 capability reporting 已进入生产代码；但本机配置的 `gemma3:1b` control 没有通过完整 taxonomy/grounding 门禁，因此当前不能把它描述成已验证的默认论证抽取模型。它的失败只减少 semantic locating hints，不能减少 Source Plane 完整性；确定性 claim-only fallback 仍明确标记为 partial。

采用边界保持不变：

- Stanza 是可选而非默认；
- HanLP/PaddleNLP 在本轮执行或采用门禁中未获准；
- LTP 的中文预训练模型许可限制商业/机构使用；
- DeepKE 没有被误当成统一生产 extractor，只保留 schema/output 参考价值。

## 5. 真实长文验收

权威语料包含：

- 中文、英文；
- TXT、HTML、native PDF、image-only scanned PDF、EPUB；
- argument、exposition、narrative；
- repeated passages、quotation、table、figure、caption、number、missing structure；
- 100,000+ 字符文档。

`reports/articlegraph-long-document-acceptance-2026-07-27.json` 当前结果：

- 7/7 case passed；
- source unit/range/element/root coverage 全部为 1.0；
- bounded continuation traversal 全部完成；
- hard serialized budget 全部满足；
- native/scanned PDF structural-reference closure 为真；
- lexical final-envelope must-hit gate 通过；
- 报告 digest 为 `sha256:25b905202e73d70f5d8ef52fa2a53f60b052ab9a0d1d3472591ca30e930a7622`。

Docling fallback 的独立真实探针还证明：

- native PDF：865 个有身份的结构记录，parent/child/relation unresolved 全为 0；
- scanned PDF：40 个有身份的结构记录，parent/child/relation unresolved 全为 0；
- OCR、layout 和全部 content-layer traversal 使用显式本地模型，禁止隐式下载；
- 原始 PDF 始终保留为 Source Plane root。

这些结果只证明来源完整性、定位能力、分页可达性和预算纪律。它们不证明 Stage 3–6 已经能稳定发现最有价值的知识缺口或生成高质量迁移原则。

## 6. CompletionPlan

`CompletionPlan` 仍是明确缺口。当前六阶段 policy 中关于 gap、boundary、counterfactual 和 transfer 的任务要求，不等于可调度的补全计划。

下一阶段至少需要持久化：

- gap identity、kind 和 source/claim/reasoning references；
- 为什么缺口阻断理解；
- `internal_reasoning`、`external_research` 或 `user_clarification` 的 completion mode；
- evidence requirements；
- completion criteria；
- completion result 与新知识；
- conflict、uncertainty 和 unresolved state；
- dependency、priority、budget、attempt lineage。

CompletionPlan 必须建立在已冻结的文章内部理解和完整 Source Plane 之上。外部研究不能反向改写 Stage 1–2 的文章内主线，也不能把系统推断伪装成作者原话。

## 最终判断

Readwelt 当前可以准确描述为：

> 已完成完整 Source Plane、可追溯 ArticleGraph locating substrate、SourceIndex、hard-budget StageView traversal、可选中文/PDF 后端和真实长文工程验收；六阶段执行底座可运行，CompletionPlan 与 Completion Engine 尚未实现。

因此项目已经从“ArticleGraph 是否能支撑长文定位”的验证期进入 Completion Engine 建设前夜，但不能描述成完整深度阅读产品已经完成。

# Dense retrieval：以 ReadingBundle 为参照的检索架构

Dense retrieval 不是给 `SemanticAtlas` 增加一列向量。Readwelt 把
`ReadingBundle` 的约束拆到检索层，使召回结果和阅读结论一样可追溯、可限定。

| ReadingBundle 里的约束 | 检索层对应物 | 作用 |
|---|---|---|
| 固定的 `ReadingStage` | `RetrievalPlan.stage` | 六阶段不会共用一个含糊查询 |
| `source_claim_ids` | `RetrievalPlan.source_claim_ids` | 查询能追到已结算的上游 claim |
| `anchor_ids` | `required_anchor_ids` | 上游 claim 的原始证据优先保留 |
| `StageArtifact` | `SemanticEvidencePacket` | 每阶段得到独立、有预算的证据产物 |
| `ReadingGap` | `omitted` / `omitted_section_ids` | 预算造成的缺口不被伪装成全文阅读 |
| claim provenance | `RetrievalHit` | 记录 lexical、dense 与融合排名 |
| bundle status | `coverage_complete` | 检索不足会进入认识状态，而不是静默丢失 |

## 执行路径

```text
SemanticAtlas
    │
    ├── Rust 可复用 lexical index（BM25+ 默认）─┐
    │                                           ├── Rust RRF
    └── DenseEncoder（可选）→ Rust DenseIndex ──┘       │
                                                        ▼
                                      Rust 章节平衡 + token budget
                                                        │
                                                         ▼
Stage-aware EvidencePacket ──> StageRequest ──> StageArtifact
```

Python 只负责构造 `RetrievalPlan`、调用模型适配器和投影领域对象。倒排索引、
BM25/BM25+/BM25L 计分、dense cosine、RRF、章节轮询与预算裁剪都在
`readwelt-core` 中执行。索引按 atlas digest 在进程内复用；一次建索引后，六阶段只
提交 query 和 top-k，不再逐查询重建词表，也不把全量文档重新穿过 PyO3 边界。

`RetrievalIndex` 接收任意 token 序列，并从传入文档动态建立词表；内核没有中文
关键词白名单或固定业务词典。`readwelt-zh-bigram-en-word-v1` 只是当前默认、
可版本化的 tokenizer。Atlas 同时保存 tokenizer version 和生成后的 tokens，因此
未来可替换分词器或加入领域词典，而不改变 scorer 与索引接口；不同 tokenizer 的
召回差异必须进入同一真实语料 benchmark 比较。

`DenseEncoder` 只有两个任务接口：

- `encode_documents`：对当前 `SemanticAtlas` 的锚点编码，按 atlas digest、
  provider、model、revision 和 dimensions 写入项目内版本化 `.f32` 缓存，
  六阶段与后续进程复用。
- `encode_queries`：对用户目的、阶段职责和已接受/限定的上游 claim 编码。

它不拥有阶段编排、预算、覆盖策略或 claim lineage。这样本地
Sentence Transformers、未来的 ONNX 后端和 OpenAI-compatible embedding 服务
可以替换，而不会改变阅读规则。

预算足以容纳全部 anchors 时，`full-coverage-v1` 直接按原文顺序生成 packet，
不执行 BM25、文档 embedding 或 query embedding。Hybrid retrieval 只处理
“证据必须被删选”的情况。

## 为什么使用 hybrid，而不是 dense-only

Dense 擅长中文释义和跨措辞召回；BM25 系列擅长人名、数字、术语和原文精确命中。
两者原始分数量纲不同，所以使用 Reciprocal Rank Fusion，而不是直接相加余弦分数
与 BM25 分数。融合后仍执行章节平衡和 orientation anchor 保底，避免相关性排序把
整章或文章开头完全挤掉。

当前 lexical 默认是 BM25+。理由是它对长锚点中的匹配提供长度归一化后的正下界，
而 Readwelt 的锚点长度可能从段落跨到整节；这是一项结构性选择，不是已经被质量
基准证明的胜出。合成中文 seed 上 BM25、BM25+、BM25L 的质量指标目前相同，默认值
要在真实中文语料和独立相关性标注加入后重新裁决。

真实 smoke test 中，查询“市场无效”对三个候选的 dense cosine 分数为：

```text
价格没有充分反映公开信息。       0.578771
市场举办古典音乐节并组织演出。   0.558649
制度会改变交易成本。             0.546672
```

它证明释义项能够越过包含“市场”字面的干扰项，但分差不大。因此 dense 是召回通道，
不是最终真理判定；后续 reranker 必须由独立 benchmark 决定是否启用。

## 本地运行边界

- 默认不启用 dense，也不下载 Torch 或模型。
- `READWELT_DENSE_MODEL=auto` 启用固定 revision 的
  `Alibaba-NLP/gte-multilingual-base`。
- 模型缓存位于项目 `.readwelt/cache/models`，不需要 PostgreSQL、Qdrant
  或其他数据库。
- 文档向量位于 `.readwelt/cache/embeddings`；manifest 不匹配、尺寸错误或文件
  损坏时会重新编码，不会读取成另一模型的向量。
- lexical index 和 dense index 在单次进程内按 atlas digest 复用；`.f32` 文档向量
  可跨进程复用。lexical 跨进程持久化和 dense mmap 尚未实现，不把它们写成现有能力。
- `READWELT_DENSE_DEVICE=auto` 优先 CUDA，缺少 CUDA 时退回 CPU。
- `transformers` 固定在 4.x；GTE 当前固定 revision 的 remote code 与
  Transformers 5.x 存在实际运行兼容问题。

模型选择依据是官方 model card 声明的 75 种语言、768 维、最长 8192 tokens 和
Apache-2.0 许可：
[GTE multilingual base](https://huggingface.co/Alibaba-NLP/gte-multilingual-base)。
查询/文档分开编码遵循 Sentence Transformers 的
[semantic search 指南](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html)。

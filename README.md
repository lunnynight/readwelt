# Readwelt

[![CI](https://github.com/lunnynight/readwelt/actions/workflows/ci.yml/badge.svg)](https://github.com/lunnynight/readwelt/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Readwelt 是一个本地优先的逆向阅读后端。它不是摘要器，也不是聊天界面；它先冻结文章
内部理解，再解压背景、恢复作者模型、检验边界，最后只迁移经压力测试后仍成立的原则。

当前没有前端，也不要求 PostgreSQL、Redis 或工作流平台。项目状态默认保存在当前目录的
`./.readwelt`，使用原子 manifest、append-only events 和 content-addressed artifacts。

## 已实现的链路

```text
Xberg 结构化导入
→ Rust 规范化 / 稳定锚点 / SHA-256 CAS
→ 非生成式 Semantic Atlas（统计、去重、MinHash、BM25、coverage）
→ 有预算的 EvidencePacket
→ 固定六阶段阅读与确定性门禁
→ ledger、canonical JSON bundle、中文阅读报告
```

六阶段固定为：

1. 文章主线
2. 论证结构
3. 知识解压
4. 作者模型与竞争解释中介
5. 隐含假设、反例和适用边界
6. 仅从 Stage 5 已结算主张生成思想迁移

模型只提交候选；锚点、阶段顺序、证据可见性、Stage 4 竞争解释、Stage 6 lineage、
coverage gaps 和最终 ledger 由运行时门禁控制。

## 安装

需要 Python 3.13、Rust stable 和 `uv`。

```powershell
uv sync --all-extras
uv run pytest
```

Xberg 固定为 `1.0.0rc38`。CPU 提供完整功能；CUDA 不参与 schema、digest、状态机或
恢复逻辑，因此没有 GPU 也不影响正确性。

## CLI

导入和非模型语义预处理：

```powershell
uv run readwelt import .\article.txt --json
uv run readwelt prepare <document_id> --json
uv run readwelt batch-prepare .\docs\a.pdf .\docs\b.docx --concurrency 8 --json
```

批处理使用有界队列、失败隔离、输入去重、定期原子 checkpoint 和断点跳过；清洗阶段
不会调用 LLM。

本地 OpenAI-compatible 服务（Ollama、llama.cpp、vLLM 等）：

```powershell
$env:READWELT_LOCAL_MODEL = "your-model"
$env:READWELT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
uv run readwelt read .\article.txt --provider local --json
```

远程 OpenAI-compatible API：

```powershell
$env:READWELT_API_MODEL = "your-model"
$env:READWELT_API_KEY = "..."
$env:READWELT_API_BASE_URL = "https://api.example.com/v1"
uv run readwelt read .\article.txt --provider api --json
```

同时配置多个 provider 时必须显式选择 `primary`、`fallback` 或 `compare`；系统不会
静默决定。`compare` 出现实质分歧时会明确停止，等待中介策略。

外部 Claude Code、Codex 或其他 Agent：

```powershell
uv run readwelt read .\article.txt --provider-mode agent_takeover --json
```

运行会停在当前阶段。外部 Agent 通过 MCP 拉取版本化 `StageRequest`，提交带
`provenance.request_digest` 的 `StageCandidate`；request/candidate 是 append-only，
不能覆盖历史，提交后流水线自动推进到下一阶段。

## 接口

- CLI：`import`、`prepare`、`batch-prepare`、`read`、`show`
- FastAPI：导入、预处理、批处理、启动 run、状态、外部 Agent pull/submit
- MCP：同一 application service，另提供 artifact 与 stage-request resources

安装 `--all-extras` 后可直接启动：

```powershell
uv run readwelt-api   # 127.0.0.1:8000
uv run readwelt-mcp   # stdio MCP server
```

CLI 是本机用户入口，可以显式导入外部路径。API/MCP 对已有文件路径限制在当前
Readwelt workspace（`.readwelt` 的父目录）内，artifact 读取始终限制在 project root。

## 目录

```text
crates/readwelt-core/      Rust 确定性内核
crates/readwelt-py/        PyO3 边界
src/readwelt/application/  用例编排与恢复
src/readwelt/semantic/     非生成式语义预处理
src/readwelt/stages/       六阶段门禁与 ledger
src/readwelt/providers/    local / API / external Agent
src/readwelt/projections/  JSON bundle 与 Markdown 报告
design/                    技术规格
research/                  HMC 与语义工具研究
```

本地状态和模型可见输入/输出都留在 `.readwelt`；源文件不会被原地修改。

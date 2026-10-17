<div align="center">

# Readwelt

### 先读懂文章，再展开文章压缩掉的世界。

面向读者的 AI 深度阅读工具：恢复文章的论点与推理，补足理解所需的背景，检验结论边界，再提取可迁移的方法。

[![CI](https://github.com/lunnynight/readwelt/actions/workflows/ci.yml/badge.svg)](https://github.com/lunnynight/readwelt/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-C9A227.svg)](LICENSE)

</div>

## Readwelt 做什么

Readwelt 不是把文章缩短，而是帮助读者弄清：作者提出了什么主张、论据如何支持它、哪些前提被省略，以及结论在什么条件下成立。

阅读顺序：

```text
恢复文章主张与关系 → 解压概念和背景 → 重建作者的问题世界 → 检验边界 → 提炼可迁移方法
```

文章自身的理论主张、论证结构、方法和实践目的分开处理。不能用一个有依据的写作目的，替代全文的思想内容。第三阶段会将概念、背景和隐含前提保留为可追溯至主张与原文引文的结构化解压单元。

## 使用 Readwelt Skill

如果你的 AI 助手支持 Agent Skills，可直接使用 [`skills/readwelt/SKILL.md`](skills/readwelt/SKILL.md)。把文章或文本文件交给助手，并要求“请帮我读懂这篇文章”。纯 Skill 阅读不需要启动 Readwelt 服务或安装 CLI。

## 使用 CLI

### 从源码安装

当前仓库提供源码运行方式；需要 [uv](https://docs.astral.sh/uv/)、Python 3.13 和 Rust stable：

```powershell
git clone https://github.com/lunnynight/readwelt.git
cd readwelt
uv sync
```

查看命令：

```powershell
uv run readwelt --help
```

Readwelt 可使用本地或远程 OpenAI-compatible 模型，或复用 Claude Code。模型与认证通过对应环境变量或宿主配置提供；不要把 API key 写进文章文件或提交到仓库。

本地模型示例：

```powershell
$env:READWELT_LOCAL_MODEL = "your-model"
$env:READWELT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
uv run readwelt read .\article.md --provider local --json
```

远程 API 示例：

```powershell
$env:READWELT_API_MODEL = "your-model"
$env:READWELT_API_KEY = "your-key"
$env:READWELT_API_BASE_URL = "https://api.example.com/v1"
uv run readwelt read .\article.md --provider api --json
```

运行环境自检：

```powershell
uv run readwelt doctor
```

`read` 直接开始阅读；`import` 与 `prepare` 用于需要显式管理文档和准备结果的工作流。其他子命令见 `--help`。

## 开发

```powershell
uv sync --group dev
uv run pytest
uv run ruff check .
```

## 项目内容

- `skills/readwelt/`：可直接交给兼容 Agent Skills 的助手使用的阅读 Skill。
- `src/readwelt/`、`crates/`：CLI、Python 接口与 Rust 核心实现。
- `evals/readwelt/`：阅读行为的测试案例、评分标准和对比方法。
- `docs/architecture/`：面向贡献者的架构说明。

Readwelt 采用 MIT 许可证，详见 [LICENSE](LICENSE)。第三方代码与材料说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

<div align="center">

# Readwelt

### 帮读者真正读懂材料，而不只是读完。

面向读者的 AI 阅读方法与 Skill：按你的目的和卡点，展开材料压缩掉的知识、经验、实践与推理。

[![CI](https://github.com/lunnynight/readwelt/actions/workflows/ci.yml/badge.svg)](https://github.com/lunnynight/readwelt/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-C9A227.svg)](LICENSE)

</div>

## Readwelt 做什么

Readwelt 不是把材料缩短，而是帮你把还连不起来的东西连起来：它面对的对象可以是一篇文章、一段课程、一次对话或一份实践记录。

它会按你的目的和已有理解选择阅读动作，例如：

- 还原材料面对的处境、人物、对象与实践条件；
- 让概念之间的依赖、流程的推进、对话的转折或论证的支撑关系变得可见；
- 补足阻挡你理解的概念、假设、背景和前置知识；
- 区分已经成立的内容、仍不确定的内容，以及批评或外部证据会改变什么；
- 说明哪些内容可以迁移到新情境，哪些条件一变就会失效。

这些是可选择的阅读动作，不是固定顺序，也不是统一报告模板。材料只有一个论点时不必硬凑结构；你只需要三句话摘要时，也不会被套上完整分析。

## 使用 Readwelt Skill

[`skills/readwelt/SKILL.md`](skills/readwelt/SKILL.md) 是唯一的产品入口。把材料交给支持 Agent Skills 的助手，并说明你想解决的理解问题即可，不需要安装运行时、启动服务或配置模型。

安装方式取决于你的宿主：将 `skills/readwelt/` 放入宿主的技能目录，或直接让助手读取该文件。

示例请求：

```text
请用 Readwelt 帮我读懂这份材料：我卡在它为什么这样组织论证。
```

```text
这段对话里双方到底在争什么？我只需要能复述清楚，不需要完整报告。
```

## 评测

[`evals/readwelt/`](evals/readwelt/) 保存阅读行为的案例、评分标准与对比方法，覆盖范围声明、说话者归属、条件保持、普通摘要请求等容易出错的情形。

```powershell
python evals/readwelt/check_quotes.py <source> <report>
```

该脚本只检查显式引文是否与原文逐字对应，不判断含义、归属或推论是否成立。

## 项目内容

- `skills/readwelt/`：产品本体，即 Agent Skill。
- `evals/readwelt/`：行为评测案例、评分标准与结果记录。
- `CONTEXT.md`：阅读领域的术语与边界。
Readwelt 采用 MIT 许可证，详见 [LICENSE](LICENSE)。第三方代码与材料说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

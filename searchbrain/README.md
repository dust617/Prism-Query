# 🧠 SearchBrain — 给 AI Agent 的智能搜索大脑

> **SearchBrain 不是一个新的搜索引擎，而是一个看懂问题、自动联网、帮你把结果整理好的"搜索大脑"。**
>
> *SearchBrain is not another search engine. It's a "search brain" that figures out what you actually need, goes online when it's truly necessary, and hands you clean, trustworthy results.*

---

## 💡 这是什么？/ What is this?

你有没有发现：同一个 AI 模型，在官方网页端（ChatGPT、Gemini、Claude 网页版）问问题时搜索很聪明，但一换到 CLI、桌面端、或第三方 Agent，搜索能力就"变瞎"了？

**原因很简单**：官方网页端的强，不是靠一个搜索接口，而是靠一整套"该不该搜、搜什么、去哪搜、搜到什么程度、结果可不可信"的智能判断。

**SearchBrain 就是把这一整套判断搬出来，做成一个任何 Agent 都能插上就用的独立服务。**

> Ever noticed how the same AI model searches smartly in the official web app, but goes blind in CLI / desktop / third-party agents? That's because the official apps don't rely on a single search API — they rely on a whole orchestration: *when to search, what to search, where to search, how deep to go, and whether the results are trustworthy.*

> **SearchBrain** extracts that orchestration and wraps it into a standalone service any AI agent can plug into.

---

## ✨ 特点 / Features

### 🧠 智能判断"该不该搜" — *Knows when NOT to search*
不是所有问题都需要联网。`解释什么是TCP` → 不搜；`Python 最新稳定版是什么` → 搜；`比较两种数据库的一致性模型` → 不搜（模型知识够）；`X上大家怎么评价GPT` → 搜（模型编不出真实舆情）。它区分的是：**稳定知识 vs 需要外部验证的动态事实**。

### 🎯 搜索深度自动调节 — *Depth that adapts*
简单问题 1 次搜索就结束（S1）；复杂调研自动多源交叉验证（S3）；真正重要的研究才进入深度模式（S4）。内部五档深度（S0-S4），用户只需说 `auto`，废话少花。

### 🌍 多搜索源，各用所长 — *Route to the best search source*
中文问题 → GLM；英文问答 → Perplexity；语义检索/找报告 → Exa；抓网页 → Firecrawl；SERP 补充 → Tavily；全文 → AnySearch；深度 → DeepSeek；中文深度 → 豆包。**一次搜索只选最合适的一家，绝不"全都打一遍"。**

### 💰 成本敏感，先便宜够用 — *Cost-aware, cheap-first*
先在便宜够用的源上搜，只有发现明确信息缺口、并且补齐价值大于成本时，才升级到更强的源。**搜的是"最合适的"，不是"最贵的"。**

### 🛡️ 结果带置信度 — *Results come with confidence*
每个回答都带一个 0-1 的置信分，如实反映"信息够不够全、够不够权威"。Agent 能据此决定是否采信，而不是盲目相信。

### 🔌 MCP 即插即用 — *Plug-and-play via MCP*
一个命令接入 Claude Code / Codex / OpenCode / 任何支持 MCP 的 Agent，只暴露一个 `search(query, mode)`。

---

## 🏗️ 架构 / Architecture

```
                 Orchestrator  (只暴露一个 search())
       ┌───────────────┼────────────────┐
  Decision Plane   Execution Plane   Evidence Plane
  决策层             执行层            证据层
  Trigger / Depth   Search/Fetch     Normalize / Dedupe
  Policy / Router   Provider         SourceAssign / Assess / Gap
```

**决策层**回答四个问题：该不该搜？搜多深？信什么类型的来源？让谁搜？
**执行层**：各搜索 Provider 真正去搜。
**证据层**：把各家结果归一化成统一"证据"，评估够不够、还缺什么，缺了且值得才补搜。

*Decision plane answers: should we search? how deep? what kind of sources to trust? who searches? Execution plane actually fetches. Evidence plane normalizes everything into uniform evidence, judges sufficiency, and only re-searches when there's a real gap worth filling.*

---

## 🚀 快速开始 / Quick Start

```bash
# 1. 安装（带 MCP 支持）
pip install -e ./searchbrain[mcp]

# 2. 配凭据：项目根建 .searchbrain-credentials.env（每个 Provider 一个 key，缺哪个就少用哪个）
#    OPENROUTER_API_KEY=...   EXA_API_KEY=...   FIRECRAWL_API_KEY=...
#    TAVILY_API_KEY=...       ANYSEARCH_API_KEY=...   ARK_API_KEY=...

# 3. 用起来
from searchbrain import search
r = search("Python 最新稳定版", mode="auto")
print(r.answer)          # 直接答案（问答型源）
print(r.results)         # 统一证据（标题/链接/摘要/来源类型）
print(r.confidence)      # 置信度 0-1
print(r.trace)           # 用了几次搜索、花了多少钱、为什么停

# CLI
PYTHONIOENCODING=utf-8 python -m searchbrain "你的问题" --json

# MCP（接入 Claude Code / Codex / OpenCode）
python -m searchbrain.mcp_server
```

---

## 📦 输出结构 / Output (one schema everywhere)

```json
{
  "answer": "带引用的直接回答（可为空）",
  "evidence": [{"title": "", "url": "", "snippet": "", "source_type": "official_docs|community|social|news|web", "provider": "glm"}],
  "sources": ["https://..."],
  "confidence": 0.83,
  "trace": {"searched": true, "depth": "S3", "providers": ["perplexity","tavily"], "queries": 2, "cost": 0.0037, "stop_reason": "sufficient_information"}
}
```

`evidence` 是核心资产——每个条目都标注了来源类型和 Provider，方便 Agent 判断取舍。

---

## 🔗 搜索源 / Providers（全部真实 API 实测接入）

| Provider | 特长 | 典型场景 |
|---|---|---|
| **GLM 智谱** | 中文关键词搜索，便宜快速 | 中文/国内问题 |
| **Perplexity** | 问答 + 逐条引用 | 英文综合、舆情 |
| **Exa** | 语义检索，找"意思相近" | 项目/报告/竞品调研 |
| **DeepSeek** | 自动改写多查询 + 深度 | 复杂调研 |
| **Tavily** | 独立 SERP，结构化 + answer | 网页结果补充 |
| **AnySearch** | 全文正文，区域感知 | 中英文全文 |
| **Firecrawl** | 抓页/网页理解 | 需要读具体页面 |
| **豆包** | 中文深度（模型自动搜） | 中文深度补充 |

新增一个源 = 写一个类 + 注册一行，Router 自动识别。详见 **DEVELOPER.md**。

---

## ✅ 测试 / Evals（数据驱动，不玄学）

```bash
python evals/run_evals.py            # 决策层（不触发网络）
python evals/run_evals.py --live     # 追加真实搜索抽样
```

当前 52 条真实问题：**Trigger Precision/Recall 1.0 · Depth 12/12 · Router 12/12**。
新增 case 直接追加到 `evals/*.jsonl`——每次改动跑一遍，就知道有没有退化。

---

## 🗺️ 路线图 / Roadmap

- **V0.1（当前）**：核心四件事分离 + 8 搜索源 + MCP + Evals ✅
- **V0.2**：结果压缩（compact/facts/full）、HTTP API、成本统计、搜索缓存
- **V0.3**：Research Loop、交叉验证增强、来源可信度模型
- **V1.0**：Search Memory、领域搜索策略、长期知识库

---

## 📚 文档 / Docs

- **DEVELOPER.md** — 给开发者/Agent 读的设计思路、为什么这样设计、如何扩展
- 详尽调研与设计历史为本项目私有文档，未公开

*Made for AI agents, by an agent. 欢迎使用、扩展、反馈。*
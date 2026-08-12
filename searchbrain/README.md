# SearchBrain 初版骨架

给任意 LLM / CLI / Agent 的智能搜索中间层。核心思想：

> **搜索的预期信息收益 > 搜索成本时才搜**；"该不该搜"和"该搜多深"彻底拆开；Best-fit first + Cost-aware；只有明确信息缺口才补搜。

面向开发者的完整说明见 **[DEVELOPER.md](DEVELOPER.md)**（精简、无隐私）。

## 三层架构

```
                 Orchestrator  (只看一个 search())
       ┌───────────────┼────────────────┐
  Decision Plane   Execution Plane   Evidence Plane
  Trigger / Depth  Search/Fetch     Normalize / Dedupe
  Policy / Router  Provider         SourceAssign / Assess / Gap
```

- **Decision Plane（决策层）**：该不该搜 / 搜多深 / 信什么源 / 让谁搜
- **Execution Plane（执行层）**：Provider 执行搜索、抓取
- **Evidence Plane（证据层）**：统一证据归一并评估（够不够 / 还缺什么）

## 核心概念

| 概念 | 说明 |
|---|---|
| **S0-S4** | 内部五级深度档（不搜 / 廉价 / 一般 / 多源 / 深度研究） |
| **Initial Depth + 动态升级** | 初始预算，发现明确缺口且值得才动态加深（S1 可能 1 次就够） |
| **SearchNeedScore** | 该不该搜（新鲜度+可验证+比较+准确风险+不确定+要来源），超阈值(0.35)才搜 |
| **Source Policy** | 权威相对问题类型（查官网→官方源；查体验→社区源），非固定权重 |
| **Best-fit Router** | 先选最擅长该问题的能力源，同等效果才比便宜 |
| **InfoGap** | 信息缺口；有明确缺口 + 价值>成本 + 预算允许 才补搜 |

## 使用

```bash
pip install -e ./searchbrain[mcp]   # 带 MCP；或 sys.path 指向 searchbrain/

# Python
from searchbrain import search
r = search("Python 最新稳定版", mode="auto")
print(r.answer, r.results, r.trace)

# CLI
PYTHONIOENCODING=utf-8 python -m searchbrain "你的问题"
PYTHONIOENCODING=utf-8 python -m searchbrain "你的问题" --mode quality --json

# MCP（供 Claude Code / Codex / OpenCode / GPT CLI 等调用）
python -m searchbrain.mcp_server   # stdio server，只暴露 search(query, mode)
```

## 统一输出结构（MCP/CLI/Python 同一 schema）

```json
{
  "answer": "...",
  "evidence": [{"title":"","url":"","snippet":"","source_type":"",
                "provider":"","published_at":null}],
  "sources": ["https://..."],
  "confidence": 0.0,
  "trace": {"searched":true,"depth":"S2","providers":[],"queries":1,
            "cost":0.0,"latency_ms":0,"stop_reason":"sufficient"}
}
```

`evidence` 是核心资产；`answer` 可为空（问答型 Provider 有值）。

## Provider（真实 API 实测）

| Provider | 能力 | 触发场景 |
|---|---|---|
| GLM（智谱） | search_web / research | 中文/国内 |
| Perplexity（OpenRouter） | search_web / answer_with_citations | 国外/问答/舆情 |
| Exa | search_web / fetch_url / research | 语义/项目/报告 |
| Firecrawl | fetch_url / extract_page / crawl_site | 网页理解 |
| DeepSeek | search_web / research / answer_with_citations | 深度/改写 |
| Tavily | search_web / answer_with_citations / global | SERP 补充 |
| AnySearch | search_web / global | 全文搜索（区域感知） |
| Doubao 豆包 | search_web / research / answer_with_citations / zh | 中文深度补充（模型自动搜） |

新增源：实现 `providers/base.py` 的 `SearchProvider`，在 `providers/register.py` 注册。

## 配置

凭据放项目根 `.searchbrain-credentials.env`（本机私有，不入仓库）：
```
OPENROUTER_API_KEY=...
EXA_API_KEY=...
FIRECRAWL_API_KEY=...
```
智谱/DeepSeek 自动从 `~/.pi/agent/auth.json` 读取。

## Evals（数据驱动调优，不玄学）

```bash
python evals/run_evals.py            # 决策层（Trigger/Depth/Router，不触发网络）
python evals/run_evals.py --live     # 追加真实搜索抽样（计费）
```

当前指标：Trigger Precision/Recall 1.0，Depth 8/8，Router 7/7。新增 case 直接追加到 `evals/*.jsonl`。

## 待完善（按规划，核心稳定后再做）
- InfoGap JSON 化（小模型输出结构化缺口）
- fetch_url 作为内部 capability（Firecrawl）——仅当 snippet 不足时才抓 1-3 页，不默认执行
- Research Loop / 交叉验证 / 结果压缩 / HTTP API / 搜索记忆
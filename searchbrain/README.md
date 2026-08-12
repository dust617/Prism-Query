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
pip install -e ./searchbrain   # 或 sys.path 指向 searchbrain/

# Python
from searchbrain import search
r = search("Python 最新稳定版", mode="auto")
print(r.answer, r.results, r.trace)

# CLI
PYTHONIOENCODING=utf-8 python -m searchbrain "你的问题"
PYTHONIOENCODING=utf-8 python -m searchbrain "你的问题" --mode quality --json
```

## Provider（真实 API 实测）

| Provider | 能力 | 触发场景 |
|---|---|---|
| GLM（智谱） | search_web / research | 中文/国内 |
| Perplexity（OpenRouter） | search_web / answer_with_citations | 国外/问答/舆情 |
| Exa | search_web / fetch_url / research | 语义/项目/报告 |
| Firecrawl | fetch_url / extract_page / crawl_site | 网页理解 |
| DeepSeek | search_web / research / answer_with_citations | 深度/改写 |

新增源：实现 `providers/base.py` 的 `SearchProvider`，在 `providers/register.py` 注册。

## 配置

凭据放 `.searchbrain-credentials.env`（本机私有，不入仓库）：
```
OPENROUTER_API_KEY=...
EXA_API_KEY=...
FIRECRAWL_API_KEY=...
```
智谱/DeepSeek 自动从 `~/.pi/agent/auth.json` 读取。

## 待完善（按规划，核心稳定后再做）
- InfoGap JSON 化（小模型输出结构化缺口）
- Evals 测试集（Trigger/Depth/Policy/Router 各 cases，统计准确率/成本）
- 最小 MCP wrapper（只暴露 search）
- Research Loop / 交叉验证 / 结果压缩 / HTTP API / 搜索记忆
# SearchBrain — 开发者概要

> 面向后续开发者 / Agent 的精简说明：整体设计思路、为什么这样设计、如何扩展与运行。
> 详细设计、调研、演进历史见非公开文档（未纳入本仓库）。

## 这是什么

给任意 LLM / CLI / Agent 用的**智能搜索中间层**。不是搜索引擎，而是一个"搜索大脑"：

> 决定该不该搜、搜什么、去哪搜、花多少钱搜、搜到什么程度、结果是否可信、还缺什么、是否值得继续。

## 为什么这样设计

很多类似项目最后变成一个巨大的 Agent Prompt（"请判断是否搜索、选源、搜几次、判断结果"），全交给模型决定，导致可控性 / 成本 / 调试都很差。

所以 SearchBrain 把问题**彻底拆开成独立模块**，每个环节可单独调试与优化：

| 模块 | 决策平面 | 回答的问题 |
|---|---|---|
| Trigger | 决策层 | 该不该搜？ |
| Depth / Budget | 决策层 | 搜多深？ |
| Source Policy | 决策层 | 该信什么类型来源？ |
| Router | 决策层 | 该让谁搜？ |
| Evidence Plane | 证据层 | 结果够不够？还缺什么？ |

核心思想：
- **该不该搜 和 该搜多深 完全拆开**（两个独立评分）
- **权威相对问题类型**（查官网资料→官网源优先；查体验→社区源优先），不是固定域名权重
- **Best-fit first, Cost-aware**：先找最擅长这个问题的源，同等效果才比便宜
- **初始深度 + 动态升级**：先给初始预算，只有发现明确信息缺口且值得才动态加深
- **补搜必须对应明确缺口**（InfoGap），没有明确缺口就停，绝不"为了搜而搜"

## 模块与文件

```
searchbrain/
├── searchbrain/
│   ├── trigger.py      # SearchNeedScore：该不该搜
│   ├── depth.py        # SearchDepth + S0-S4 + Budget（初始+动态升级）
│   ├── policy.py       # Source Policy：信什么类型来源
│   ├── router.py       # Best-fit Router：选能力→选 Provider
│   ├── evidence.py     # 证据层：normalize/dedupe/assess/gap
│   ├── orchestrator.py # 主控制器（只暴露 search()）
│   ├── models.py       # 数据模型（Evidence/InfoGap/Budget/...）
│   └── providers/      # base + glm + perplexity + exa + firecrawl + deepseek
```

## 如何扩展（加一个新搜索源）

1. 在 `providers/` 新增一个类，继承 `providers/base.py` 的 `SearchProvider`
2. 实现统一的 `search(request) -> ProviderResult`（返回 `SearchItem` 列表，可带 `answer`）
3. 声明 `capabilities`（如 `search_web` / `search_social` / `research` / `answer_with_citations`）和 `cost_level`
4. 在 `providers/register.py` 注册（按是否配 key 决定）

核心代码无需修改——Router 会自动按能力路由，Evidence 层会自动归一化。

## 运行

```bash
# 凭据放 .searchbrain-credentials.env（不在仓库内）或 ~/.pi/agent/auth.json
# 包内：
from searchbrain import search
r = search("Python 最新稳定版", mode="auto")
print(r.answer, r.results, r.trace)

# CLI
PYTHONIOENCODING=utf-8 python -m searchbrain "你的问题"
PYTHONIOENCODING=utf-8 python -m searchbrain "你的问题" --mode quality --json

# MCP（供 Claude Code / Codex / OpenCode / GPT CLI 等调用）
# 已配置到本机 Claude Code 和 Codex：
#   claude mcp add searchbrain -e PYTHONPATH=<searchbrain目录> -- python -m searchbrain.mcp_server
#   codex mcp add searchbrain -e PYTHONPATH=<searchbrain目录> -- python -m searchbrain.mcp_server
# 或直接运行： python -m searchbrain.mcp_server
```

## InfoGap 模型化（可选、默认开）

S3/S4 档位且规则找不到机械缺口时，会调用小模型（DeepSeek）分析已有证据，
输出结构化"还缺什么"（missing_information），由系统判断值不值得补搜。

- 规则 gap 找机械缺口（数量不足/来源单一）；模型 gap 找语义缺口（缺官方价格/一手资料）
- 关闭：在 `config.py` 设 `Defaults.GAP_MODEL_ENABLED = False`
- 失败/超时会静默回退到规则版，不中断主流程

## 测试

```bash
cd searchbrain
python -c "from searchbrain.trigger import compute_need_score; print(compute_need_score('解释TCP')[0])"   # 应接近 0（不搜）
```
真实搜索会调用已配 key 的 Provider，成本通常 <$0.01/次。

## 边界与注意
- Provider 的 key 只在 `config.py` 加载，代码里不落明文
- S0 问题（稳定知识/写作/计算）不触发搜索
- 舆情/时效类问题有"强信号"，会强制触发搜索
- `search_social` 目前缺少专项源（xAI 未接入），舆情暂由 Perplexity/问答型承担
"""Search Trigger：判断"这个问题该不该搜索"。

核心思想（用户文档）：
    不要先判断"问题简单还是复杂"，而先判断
    "答案是否依赖模型外部的、可变化或需要验证的信息"。

SearchNeedScore = 新鲜度需求 + 外部可验证性 + 模型不确定度 + 准确性风险 + 用户要求来源

初版用规则关键词打分（够用、零成本、可解释），后续可换小模型。
"""
from __future__ import annotations

import re


# ---- 各维度关键词（中英文）----
_FRESHNESS = re.compile(
    r"最新|现在|当前|今天|昨天|今年|本月|本周|最近|刚刚|最新版|多久|何时|"
    r"价格|收费|涨价|降价|版本|发布|宣布|更新|上线|推出|行情|动态|新闻|走势|"
    r"202[0-9]|最新状态|current|latest|new|news|price|pricing|release|"
    r"version|update|today|now|recent|2026|2027"
)
_VERIFIABLE = re.compile(
    r"支持吗|支持.*吗|多少钱|收费|价格|是否|对不对|真假的|谁|哪个|哪家|"
    r"有没有|存在|API|MCP|文档|官方|网址|链接|怎么用|怎么买|在哪|"
    r"support|api|mcp|docs|official|how much|price|is it|does .* support|exists"
)
_UNCERTAINTY = re.compile(
    r"查一下|查证|验证|核实|确认|最新|有没有变化|是不是真的|靠谱吗|可信吗|"
    r"verify|check|confirm|uncertain|up to date|recent"
)
_ACCURACY = re.compile(
    r"多少钱|什么时候|几点|版本号|数字|数据|日期|时间|政策|法规|标准|"
    r"¥|￥|\$|\d+(\.\d+)?%|同比|环比|涨幅|规模|人数|how many|how much|when|"
    r"version|number|date|policy|regulation|percent|\d{4}"
)
_USER_SOURCE = re.compile(
    r"给我.*来源|要.*引用|出处|引用|来源|查一下|搜一下|最新|source|citation|"
    r"reference|cite|find|search"
)
# 比较/调研类：答案依赖多个对象的外部实际信息，且通常需查证最新情况
_COMPARISON = re.compile(
    r"比较|对比|哪个好|哪个适合|哪个更|优缺点|推荐|评测|测评|对比分析|"
    r"谁更好|更适合|选择哪个|调研|分析|选取|compare|comparison|"
    r"which is better|which.*适合|pros and cons|review|recommend|pick"
)
# 负面信号：明显不需要外部的稳定知识 / 计算 / 写作
_NO_SEARCH = re.compile(
    r"解释|什么是(?!最新)|证明|计算|翻译|总结.*文档|改写|写一段|写个|"
    r"解释一下|define|explain|prove|calculate|translate|summarize|compose|write.*code|solve|推导"
)
# 强信号：命中即强烈倾向搜索（时效/舆情/价格类——模型无法凭空给出真实外部信息）
_STRONG = re.compile(
    r"最新|最近|近期|最新动态|何时|什么时候|价格|多少钱|售价|版本|发布|宣布|涨价|降价|推出|202[0-9]|"
    r"评价|怎么看|舆情|口碑|反馈|x上|twitter|reddit|大家觉得|风评|"
    r"该不该|值不值得|要不要|是否应该|适合吗|值得吗|"
    r"(分析|调研|研究|盘点|评估).{0,6}(市场|行业|格局|竞争|趋势|机会|电商|工具|产品|领域)|"
    r"(市场|行业|格局|竞争|趋势|机会).{0,4}(分析|调研|研究)|"
    r"latest|price|pricing|version|release|review|sentiment|feedback|cost"
)


def _score(regex: re.Pattern, text: str) -> float:
    """命中任一关键词则该维度=1，否则 0。可后续细化成部分命中计分。"""
    return 1.0 if regex.search(text) else 0.0


# 各维度权重（总和应使 need_score 落在 0-1 附近）
_WEIGHTS = {
    "freshness": 0.25,
    "verifiable": 0.20,
    "comparison": 0.20,
    "uncertainty": 0.10,
    "accuracy": 0.15,
    "user_source": 0.10,
}


def compute_need_score(query: str) -> tuple[float, dict[str, float], float]:
    """返回 (need_score, 各维度分, 负面抑制)。

    need_score 越高越值得搜索。负面信号直接压低评分。
    """
    # 比较维度：只有“比较 + 具体实体（API/工具/价格/版本等外部对象）”才高分；
    # 纯概念比较（如数据库一致性模型）模型知识足够，不应触发。
    comp_raw = _score(_COMPARISON, query)
    concrete = _score(_VERIFIABLE, query) or _score(_FRESHNESS, query)
    dims = {
        "freshness": _score(_FRESHNESS, query),
        "verifiable": _score(_VERIFIABLE, query),
        "comparison": comp_raw * (0.5 + 0.5 * concrete),
        "uncertainty": _score(_UNCERTAINTY, query),
        "accuracy": _score(_ACCURACY, query),
        "user_source": _score(_USER_SOURCE, query),
    }
    score = sum(_WEIGHTS[k] * v for k, v in dims.items())
    penalty = 0.0
    if _NO_SEARCH.search(query):
        penalty = 0.25 if not dims["user_source"] and not dims["freshness"] else 0.0
    # 强信号：命中直接抬到触发阈值（时效/舆情/价格——必须搜）
    if _STRONG.search(query):
        score = max(score, 0.5)
    return max(0.0, min(1.0, score - penalty)), dims, penalty


def is_time_sensitive(query: str) -> bool:
    """时效/强信号问题：结果会随时间变化，不宜缓存。

    命中新鲜度维度或强信号（价格/最新/舆情/版本等）即视为时效敏感。
    """
    return bool(_FRESHNESS.search(query) or _STRONG.search(query))
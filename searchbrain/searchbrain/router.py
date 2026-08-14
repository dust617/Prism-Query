"""Provider Router：这次应该让谁搜？Best-fit first，Cost-aware。

核心思想（用户评审修正）：
    不要把 Cheap-first 理解成"永远最便宜的先搜"。
    应该是：
        先找"最适合解决这个问题"的 Provider（能力/语言/来源匹配）
            ↓
        如果有多个效果差不多
            ↓
        优先便宜那个

流程：choose_capability() → choose_provider_for_capability()
      （先决定需要什么能力，再决定谁最擅长这个能力）
"""
from __future__ import annotations

import re

from .models import SearchLevel, SearchRequest
from .policy import classify_intent
from .providers.base import available

# Source Policy 的问题类型 → 需要的搜索能力
_INTENT_CAP = {
    "official": "search_web",               # 官方/价格 → 通用网页搜索
    "experience": "answer_with_citations",  # 体验/口碑 → 问答+引用（社区更易命中）
    "social": "search_social",              # 舆情 → 社媒搜索
    "news": "search_web",
    "technical": "search_code",             # 技术/项目 → 代码/项目搜索
    "general": "search_web",
}

# 中文检测：中文问题优先有中文能力的源
_ZH = re.compile(r"[\u4e00-\u9fff]")

# 成本档加分（同等能力下便宜优先）
_COST_BONUS = {"low": 2, "medium": 1, "high": 0}


def choose_capability(query: str) -> str:
    """根据问题类型决定需要什么搜索能力。"""
    intent = classify_intent(query)
    return _INTENT_CAP.get(intent, "search_web")


def choose(query: str, used: set[str], level: SearchLevel,
           request: SearchRequest) -> str | None:
    """选下一个 Provider 名（capability 匹配 → 语言匹配 → 成本）。

    返回 None 表示没有可用候选（应该停止）。
    """
    cap = choose_capability(query)
    is_zh = bool(_ZH.search(query))

    # 1) 先找"最适合"的：支持所需能力的 Provider
    candidates = [p for p in available()
                  if cap in p.capabilities and p.name not in used]
    # 2) 退化：没有专项能力时退到通用网页搜索
    if not candidates:
        candidates = [p for p in available()
                      if "search_web" in p.capabilities and p.name not in used]
    if not candidates:
        return None

    # 3) Best-fit + Cost-aware 打分
    best, best_score = None, -1
    for p in candidates:
        s = 0
        # 语言匹配（最优先）：中文→zh 源；非中文→global 源（zh 源不并列）
        if is_zh:
            if "zh" in p.capabilities:
                s += 4
        else:
            if "global" in p.capabilities:
                s += 2
        # 成本（同等能力下便宜优先）
        s += _COST_BONUS.get(p.cost_level, 1)
        # 专项能力命中（该能力越专越好）
        if cap in ("answer_with_citations", "search_social") and \
                cap in p.capabilities:
            s += 2
        # 免费源优先加分（如方舟 DeepSeek-V4-Flash 免费 token）：
        #    同效果下优先让免费/便宜源先摸一遍，花冤枉钱前先试免费，
        #    发现价值缺口再升级。语言匹配(+4)仍优先，不会被免费反压。
        if "free" in p.capabilities:
            s += 2
        # 用户手动指定
        if request.provider_hint and p.name == request.provider_hint:
            s += 10
        if s > best_score:
            best_score, best = s, p.name
    return best
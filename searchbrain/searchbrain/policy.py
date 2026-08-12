"""Source Policy：决定"这个问题应该相信什么类型的来源"。

核心思想（用户文档）：
    "权威"是相对于问题而言的，不是一个网站固定拥有的分数。
    - 查"GLM API 支持什么/多少钱" → 官网/官方文档压倒性优先
    - 查"GLM 实际体验/稳定性" → GitHub issue、开发者社区更重要
    - 查"舆情" → X/Reddit/论坛更重要

初版：按问题类型给来源类别的偏好权重，用于对结果重排。
"""
from __future__ import annotations

import re

from .models import SearchItem

# 问题类型 → 来源偏好权重 {official, community, social, technical, news}
# 权重越高，该类型来源越靠前。
_PREF = {
    "official": {"official": 1.0, "technical": 0.6, "news": 0.3,
                 "community": 0.2, "social": 0.1},
    "experience": {"community": 1.0, "social": 0.8, "technical": 0.6,
                   "official": 0.3, "news": 0.2},
    "social": {"social": 1.0, "community": 0.7, "news": 0.4,
               "official": 0.1, "technical": 0.1},
    "news": {"news": 1.0, "official": 0.5, "technical": 0.3,
             "community": 0.2, "social": 0.3},
    "technical": {"technical": 1.0, "official": 0.8, "community": 0.6,
                  "news": 0.2, "social": 0.1},
    "general": {"official": 0.5, "technical": 0.4, "community": 0.5,
                "news": 0.5, "social": 0.3},
}

# 来源类型 → 域名特征
_OFFICIAL = re.compile(
    r"(\.gov|\.gob|\.gov\.br|docs\.|openai\.com|anthropic\.com|bigmodel\.cn|"
    r"aliyun\.com|azure\.com|aws\.amazon\.com|google\.com|developers\.|"
    r"platform\.|microsoft\.com|firecrawl\.dev|exa\.ai|tavily\.com"
    r"|\.org$|\.edu$|\.mil)", re.I)
_COMMUNITY = re.compile(r"(github\.com|stackoverflow\.com|reddit\.com|"
                        r"zhihu\.com|v2ex\.com|discord|forum|issues)", re.I)
_SOCIAL = re.compile(r"(x\.com|twitter\.com|weibo\.com|threads\.net|"
                     r"reddit\.com|t\.me|facebook\.com)", re.I)
_NEWS = re.compile(
    r"(news|reuters|bloomberg|bbc|cnn|techcrunch|the-verge|"
    r"theverge|36kr|pingwest|ithome|sina|163|sohu|qq\.com)", re.I)
_TECHNICAL = re.compile(r"(github\.com|stackoverflow\.com|gitlab|"
                        r"readthedocs|w3\.org|arxiv|docs\.|developer\.)", re.I)


def classify_intent(query):
    """判断问题最偏向哪种来源。"""
    q = query.lower()
    if re.search(r"体验|稳定性|口碑|评价|好用吗|怎么样|坑|问题|bug|反馈|"
                 r"experience|stable|reliable|review|issues|bug", q):
        return "experience"
    if re.search(r"舆情|怎么看|讨论|争议|社区|x上|twitter|reddit|论坛|"
                 r"opinion|discuss|sentiment|social", q):
        return "social"
    if re.search(r"新闻|最新.*发布|宣布|推出|行情|动态|news|release|"
                 r"announce|trend", q):
        return "news"
    if re.search(r"github|gitlab|开源|代码|源码|框架|electron|tauri|react|vue|"
                 r"sdk|library|dependency|npm|pip|stackoverflow|技术栈|活跃度|stars|项目仓库", q):
        return "technical"
    if re.search(r"官方|api|mcp|文档|docs|接口|参数|价格|多少钱|单价|支持|规格|"
                 r"spec|how much|price|support|能不能|好不好|收费标准", q):
        return "official"
    return "general"
def _source_type(url: str) -> str:
    if _OFFICIAL.search(url):
        return "official"
    if _SOCIAL.search(url):
        return "social"
    if _COMMUNITY.search(url):
        return "community"
    if _TECHNICAL.search(url):
        return "technical"
    if _NEWS.search(url):
        return "news"
    return "general"


def rerank(query: str, items: list[SearchItem]) -> list[SearchItem]:
    """按来源策略重排结果。不改动原列表内容，只调整顺序。

    排序分 = 0.6 × 相关性分 + 0.4 × 来源偏好分（针对该问题的来源类型要求）
    """
    if not items:
        return items
    intent = classify_intent(query)
    pref = _PREF.get(intent, _PREF["general"])
    ranked = []
    for ix, it in enumerate(items):
        # 相关性基础分：用原始 score，若没有则用位置衰减
        rel = it.score if it.score > 0 else max(0.0, 1.0 - ix * 0.1)
        st = _source_type(it.url)
        src_bonus = pref.get(st, 0.3)
        ranked.append((it, 0.6 * rel + 0.4 * src_bonus))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return [it for it, _ in ranked]
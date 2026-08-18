"""证据处理层（Evidence Plane）。

负责把各 Provider 的原始结果归一化为统一 Evidence，并评估：
    Normalize → Dedupe → Assess(是否足够) → DetectGap(还缺什么)
决策层和执行层之外，这一层是 SearchBrain 真正区别于"多 API 聚合器"的部分。
"""
from __future__ import annotations

import datetime as _dt
import re as _re

from .models import Evidence, InfoGap, ProviderResult, SearchItem, SearchLevel
from .policy import _OFFICIAL, _SOCIAL, _COMMUNITY, _NEWS, _TECHNICAL


def _source_type(url: str) -> str:
    stone = {_OFFICIAL: "official_docs", _SOCIAL: "social",
             _COMMUNITY: "community", _TECHNICAL: "technical",
             _NEWS: "news"}
    for pat, label in stone.items():
        if pat.search(url):
            return label
    return "web"


def normalize(result: ProviderResult) -> list[Evidence]:
    """把 ProviderResult 的 items 转成统一 Evidence（以 provider/url 标来源类型）。"""
    now = _dt.datetime.now().isoformat(timespec="seconds")
    evs = []
    for it in result.items:
        evs.append(Evidence(
            url=it.url, title=it.title, snippet=it.snippet,
            source_type=_source_type(it.url), provider=result.provider,
            published_at=it.published_at, retrieved_at=now,
            relevance=it.score if it.score > 0 else 0.0,
            authority=0.0,  # 由 Policy 在评估时按问题类型赋值
        ))
    return evs


def dedupe(evidences: list[Evidence], max_items: int = 8) -> list[Evidence]:
    """按 url 去重；多 Provider 时按源均衡保留。"""
    seen: set[str] = set()
    by_src: dict[str, list[Evidence]] = {}
    for e in evidences:
        by_src.setdefault(e.provider, []).append(e)
    per_src = max(2, max_items // max(1, len(by_src)))
    out: list[Evidence] = []
    for items in by_src.values():
        for e in items[:per_src]:
            if e.url and e.url in seen:
                continue
            if e.url:
                seen.add(e.url)
            out.append(e)
    return out[:max_items]


# 证据层 source_type 标签 → Source Policy 偏好表键：
# 归一化层用更语义化的 official_docs 作为对外标签，策略层偏好表用 official。
_SRC_TO_POLICY = {"official_docs": "official"}


def apply_source_policy(query: str, evidences: list[Evidence]) -> list[Evidence]:
    """用 Source Policy 给证据的来源类型赋权威度（相对问题类型）。

    权威度是"相对问题类型"的：查官方参数时 official 来源权威最高，
    查体验口碑时 community 来源最高——不是域名固定权重。
    """
    from .policy import classify_intent, _PREF
    intent = classify_intent(query)
    pref = _PREF.get(intent, _PREF["general"])
    for e in evidences:
        policy_key = _SRC_TO_POLICY.get(e.source_type, e.source_type)
        e.authority = pref.get(policy_key, 0.3)
    return evidences


# ---- 词面相关性（供排序兜底） ----

# 中英文常见停用词：不参与相关性计算（避免"的/了/最新"等干扰）
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "and", "or", "for",
    "with", "in", "on", "of", "to", "it", "this", "that", "how", "what",
    "why", "when", "where", "which", "who", "do", "does", "did", "can",
    "could", "will", "would", "should", "vs", "versus", "compare",
    "最新", "现在", "当前", "怎么", "如何", "什么", "哪个", "哪些",
    "是否", "的", "了", "和", "与", "或", "吗", "呢", "啊",
}


def _terms(text: str) -> set[str]:
    """把文本切成检索词：英文单词（>=2 字符）+ 中文二元组（去标点/数字）。"""
    terms: set[str] = set()
    for w in _re.findall(r"[a-z0-9]{2,}", text.lower()):
        if w not in _STOP:
            terms.add(w)
    for run in _re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for i in range(len(run) - 1):
            bigram = run[i:i + 2]
            if bigram not in _STOP:
                terms.add(bigram)
    return terms


def lexical_relevance(query: str, evidence: Evidence) -> float:
    """query 与 title+snippet 的词面重合度（0-1）。

    多数 Provider 不返回 score，relevance 长期为 0；这里用词面重合
    给一个可解释的相关性估计，供结果排序使用。
    """
    q_terms = _terms(query)
    if not q_terms:
        return 0.0
    text_terms = _terms(f"{evidence.title} {evidence.snippet}")
    hit = sum(1 for t in q_terms if t in text_terms)
    return hit / len(q_terms)


def assess(query: str, evidences: list[Evidence],
           results: list[ProviderResult], level: SearchLevel) -> bool:
    """评估现有证据是否足够（覆盖 + 多搜索源 + 是否有答案）。

    返回 True 表示足够，可以停止。
    "多源"指不同 Provider（搜索源）交叉验证，而非仅 URL 来源类型。
    """
    n = len(evidences)
    # 来源数 = 有 items 或 有 answer 的 Provider（问答型也算交叉验证来源）
    n_prov = len({r.provider for r in results if r.items or r.answer})
    has_ans = any(r.answer for r in results)
    if level == SearchLevel.S1:
        return n >= 1 or has_ans
    if level == SearchLevel.S2:
        return n >= 2 or has_ans
    if level == SearchLevel.S3:
        # 2+ 来源交叉 + 有内容即可（问答型源只给 answer 不给条目，n 放宽到 2）
        return n >= 2 and n_prov >= 2
    if level == SearchLevel.S4:
        return n >= 3 and n_prov >= 2 and has_ans
    return True


def detect_gap(query: str, evidences: list[Evidence],
               results: list[ProviderResult], level: SearchLevel,
               budget) -> InfoGap | None:
    """检测信息缺口。补搜必须对应明确缺口；没有缺口就停止。"""
    n = len(evidences)
    n_prov = len({r.provider for r in results if r.items or r.answer})
    if n == 0 and not any(r.answer for r in results):
        return InfoGap("无任何结果，需要换源重试", importance=0.9)
    # 多源档位但搜索源单一 → 需要交叉验证
    if level in (SearchLevel.S3, SearchLevel.S4) and n_prov < 2:
        return InfoGap("搜索源单一，需多源交叉验证",
                       preferred_source_type="web", importance=0.8)
    # 覆盖不足
    if level in (SearchLevel.S3, SearchLevel.S4) and n < 3:
        return InfoGap("结果数量不足", importance=0.6)
    return None  # 没有明确缺口 → 停止
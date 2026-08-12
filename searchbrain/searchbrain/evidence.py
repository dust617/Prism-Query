"""证据处理层（Evidence Plane）。

负责把各 Provider 的原始结果归一化为统一 Evidence，并评估：
    Normalize → Dedupe → Assess(是否足够) → DetectGap(还缺什么)
决策层和执行层之外，这一层是 SearchBrain 真正区别于"多 API 聚合器"的部分。
"""
from __future__ import annotations

import datetime as _dt

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
    """把 ProviderResult 的 items 转成统一 Evidence（start以 provider/url 标来源类型）。"""
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


def apply_source_policy(query: str, evidences: list[Evidence]) -> list[Evidence]:
    """用 Source Policy 给证据的来源类型赋权威度（相对问题类型）。"""
    from .policy import classify_intent, _PREF
    intent = classify_intent(query)
    pref = _PREF.get(intent, _PREF["general"])
    for e in evidences:
        e.authority = pref.get(e.source_type, 0.3)
    return evidences


def assess(query: str, evidences: list[Evidence],
           results: list[ProviderResult], level: SearchLevel) -> bool:
    """评估现有证据是否足够（覆盖 + 来源多样性 + 是否有答案）。

    返回 True 表示足够，可以停止。
    """
    n = len(evidences)
    n_st = len({e.source_type for e in evidences})
    has_ans = any(r.answer for r in results)
    if level == SearchLevel.S1:
        return n >= 1 or has_ans
    if level == SearchLevel.S2:
        return n >= 2 or has_ans
    if level == SearchLevel.S3:
        return n >= 3 and n_st >= 2
    if level == SearchLevel.S4:
        return n >= 4 and n_st >= 2 and has_ans
    return True


def detect_gap(query: str, evidences: list[Evidence],
               results: list[ProviderResult], level: SearchLevel,
               budget) -> InfoGap | None:
    """检测信息缺口。补搜必须对应明确缺口；没有缺口就停止。"""
    n = len(evidences)
    n_st = len({e.source_type for e in evidences})
    if n == 0 and not any(r.answer for r in results):
        return InfoGap("无任何结果，需要换源重试", importance=0.9)
    # 多源档位但来源类型单一 → 需要交叉验证
    if level in (SearchLevel.S3, SearchLevel.S4) and n_st < 2:
        return InfoGap("来源类型单一，需多源交叉验证",
                       preferred_source_type="web", importance=0.8)
    # 覆盖不足
    if level in (SearchLevel.S3, SearchLevel.S4) and n < 3:
        return InfoGap("结果数量不足", importance=0.6)
    return None  # 没有明确缺口 → 停止
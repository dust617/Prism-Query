"""Evaluator：评估搜索结果的质量（confidence）。

confidence 综合：证据数量、来源类型多样性、是否有直接答案、来源权威度。
供 Agent 判断"这个答案有多可信"，也是后续 Router 调优的依据。
"""
from __future__ import annotations

from .models import Evidence, ProviderResult, SearchLevel


def compute_confidence(query: str, evidences: list[Evidence],
                       results: list[ProviderResult],
                       level: SearchLevel, searched: bool) -> float:
    if not searched:
        return 0.0
    conf = 0.30  # 基础分（确实搜了）
    n = len(evidences)
    n_st = len({e.source_type for e in evidences if e.source_type != "web"})
    has_ans = any(r.answer for r in results)
    # 证据数量：最多 +0.25
    conf += min(0.25, n * 0.05)
    # 来源类型多样性（非 web 的明确类型越多越可信）：最多 +0.20
    conf += min(0.20, n_st * 0.07)
    # 有直接答案：+0.15（问答型 Provider 的总结）
    if has_ans:
        conf += 0.15
    # 来源权威度（Source Policy 已按问题类型赋值）：最多 +0.10
    if evidences:
        avg_auth = sum(e.authority for e in evidences) / len(evidences)
        conf += min(0.10, avg_auth * 0.10 * 2)
    return round(min(1.0, conf), 2)
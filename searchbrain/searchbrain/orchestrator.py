"""SearchBrain 主控制器：Trigger → Initial Depth → Capability Router → 搜索 → 证据评估 → 动态升级。

对外只暴露一个 search()。内部把"决策层 / 执行层 / 证据层"串起来：
    Decision Plane:  trigger / depth / policy / budget
    Execution Plane: providers（执行搜索）
    Evidence Plane:  normalize / dedupe / assess / gap
"""
from __future__ import annotations

from .config import Defaults
from .depth import Budget, compute_depth_score, decide_level
from .evidence import (apply_source_policy, assess, dedupe, detect_gap,
                       normalize)
from .models import (Evidence, InfoGap, ProviderResult, SearchLevel,
                     SearchMode, SearchRequest, SearchResponse, SearchTrace)
from .providers.base import available, get
from .providers.register import load_providers
from .router import choose, choose_capability
from .trigger import compute_need_score

_loaded = False


def _ensure_providers() -> None:
    global _loaded
    if not _loaded:
        load_providers()
        _loaded = True


def _pick_answer(results: list[ProviderResult]) -> str | None:
    """优先取问答型 Provider 的总结。"""
    for res in results:
        if res.answer:
            return res.answer
    return None


def _rank_evidence(query: str, evidences: list[Evidence]) -> list[Evidence]:
    """证据排序：相关性 60% + 来源权威度 40%（权威度由 Source Policy 赋值）。"""
    def _key(e: Evidence):
        return 0.6 * e.relevance + 0.4 * e.authority + 0.1
    return sorted(evidences, key=_key, reverse=True)


def search(request: SearchRequest | str,
           mode: SearchMode = SearchMode.AUTO,
           max_cost: float | None = None,
           max_queries: int | None = None) -> SearchResponse:
    """统一搜索入口。可传 SearchRequest 或直接传 query 字符串。"""
    _ensure_providers()
    if isinstance(request, str):
        request = SearchRequest(query=request, mode=mode,
                                max_cost=max_cost, max_queries=max_queries)

    trace = SearchTrace()
    trace.depth_score = compute_depth_score(request.query)

    # 1) Decision Plane —— Trigger：该不该搜
    need_score, dims, penalty = compute_need_score(request.query)
    trace.need_score = need_score
    if need_score < Defaults.NEED_THRESHOLD:
        trace.level = SearchLevel.S0.value
        trace.stop_reason = "below_need_threshold"
        return SearchResponse(query=request.query, results=[], trace=trace)

    # 2) Decision Plane —— Initial Depth：搜多深（初始预算，可动态升级）
    level = decide_level(need_score, trace.depth_score, request.mode)
    trace.level = level.value
    budget = Budget(level, max_cost or request.max_cost,
                    max_queries or request.max_queries)

    # 3) Execution + Evidence Plane 迭代
    results: list[ProviderResult] = []
    evidences: list[Evidence] = []
    used: set[str] = set()
    last_gap: InfoGap | None = None

    while True:
        # 预算不足时：有明确缺口且预算可升级 → 动态升级；否则停止
        if not budget.can_continue:
            if last_gap and budget.can_escalate():
                budget.escalate()
            else:
                trace.stop_reason = "budget_exhausted"
                break

        cap = choose_capability(request.query)
        pname = choose(request.query, used, level, request)
        if pname is None:
            trace.stop_reason = "no_more_providers"
            break
        used.add(pname)
        provider = get(pname)
        if provider is None:
            continue

        result = provider.search(request)
        results.append(result)
        budget.consume(1, result.estimated_cost)
        trace.providers_used.append(pname)
        trace.capabilities_used.append(cap)
        trace.queries += 1
        trace.rounds += 1
        trace.estimated_cost += result.estimated_cost

        # 证据层：normalize → dedupe → source policy
        evidences = dedupe(evidences + normalize(result), request.max_results)
        evidences = apply_source_policy(request.query, evidences)

        # 足够？→ 停止
        if assess(request.query, evidences, results, level):
            trace.stop_reason = "sufficient_information"
            break
        # 不够 → 找明确缺口
        last_gap = detect_gap(request.query, evidences, results, level, budget)
        if last_gap is None or last_gap.importance < 0.5:
            trace.stop_reason = "no_clear_gap"
            break
        # 有缺口 → 继续循环（预算不足时循环顶部会决定是否 escalate）

    evidences = _rank_evidence(request.query, evidences)
    trace.latency_ms = sum(r.latency_ms for r in results)
    if not trace.stop_reason:
        trace.stop_reason = "budget_exhausted"

    return SearchResponse(query=request.query,
                          answer=_pick_answer(results),
                          results=evidences,
                          trace=trace)
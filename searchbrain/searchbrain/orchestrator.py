"""SearchBrain 主控制器：Trigger → Initial Depth → Capability Router → 搜索 → 证据评估 → 动态升级。

对外只暴露一个 search()。内部把"决策层 / 执行层 / 证据层"串起来：
    Decision Plane:  trigger / depth / policy / budget
    Execution Plane: providers（执行搜索）
    Evidence Plane:  normalize / dedupe / assess / gap
"""
from __future__ import annotations

from .config import Defaults, normalize_search_bias
from .depth import Budget, compute_depth_score, decide_level
from .evaluator import compute_confidence
from .evidence import (apply_source_policy, assess, dedupe, detect_gap,
                       normalize)
from .gap_model import detect_gap_with_model
from .models import (Evidence, InfoGap, ProviderResult, SearchLevel,
                     SearchMode, SearchRequest, SearchResponse, SearchTrace)
from .providers.base import available, get
from .providers.register import load_providers
from .router import choose, choose_capability
from .trigger import compute_need_score
from . import usage as _usage

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


def _fetch_missing_pages(evidences: list[Evidence], results: list[ProviderResult],
                        max_fetch: int = 2) -> tuple[list[Evidence], bool]:
    """读页闭环：snippet 不足时抓关键页面补正文（经济先用免费管线）。

    本地直抓(SSRF 防护)优先、Firecrawl 其次、Jina Reader 兜底，全部免 key 可用；
    不再依赖 Firecrawl key 才能触发。返回 (新增 evidence, 是否抓过)。
    """
    from .providers.fetch_local import fetch_web
    # 候选：snippet 短且有 URL 的证据（按 relevance 排序）
    cands = sorted(
        [e for e in evidences if e.url and len(e.snippet) < 200],
        key=lambda e: e.relevance, reverse=True)[:max_fetch]
    if not cands:
        return [], False
    added = []
    for e in cands:
        body, source = fetch_web(e.url)
        if body and len(body) > 100:
            added.append(Evidence(
                url=e.url, title=e.title, snippet=body,
                source_type=e.source_type, provider=source or "local",
                relevance=e.relevance, authority=e.authority))
    return added, bool(added)


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
    # 搜索倾向系数：只放大“是否触发”，不放大“初始深度”。“多出来的倾向”
    # 先落到免费/便宜源上，值不值得往下挖仍由 InfoGap 的 importance /
    # expected_value 决定（避免“为搜而搜、为偏而深”）。
    bias = normalize_search_bias(request.search_bias, Defaults.SEARCH_BIAS)
    need_eff = min(1.0, need_score * bias)
    trace.need_score = need_eff
    trace.search_bias = bias
    if need_eff < Defaults.NEED_THRESHOLD:
        trace.level = SearchLevel.S0.value
        trace.searched = False
        trace.stop_reason = "below_need_threshold"
        return SearchResponse(query=request.query, results=[], trace=trace,
                              confidence=0.0)

    # 2) Decision Plane —— Initial Depth：搜多深（初始预算，可动态升级）
    #    用“原始” need_score 定深：bias 提触发但不加深，深挖交给缺口升级。
    level = decide_level(need_score, trace.depth_score, request.mode)
    trace.level = level.value
    budget = Budget(level, max_cost or request.max_cost,
                    max_queries or request.max_queries)

    # 3) Execution + Evidence Plane 迭代
    results: list[ProviderResult] = []
    evidences: list[Evidence] = []
    used: set[str] = set()
    last_gap: InfoGap | None = None
    model_gap_checked = False

    while True:
        # 预算不足时：有明确缺口且预算可升级 → 动态升级；否则停止
        if not budget.can_continue:
            if last_gap and budget.can_escalate():
                budget.escalate()
            else:
                trace.stop_reason = "budget_exhausted"
                break

        # Research Loop：若有缺口建议的新查询，用它演进补搜（而非原 query）
        loop_query = (last_gap.suggested_query or request.query)             if last_gap and last_gap.suggested_query else request.query
        cap = choose_capability(loop_query)
        pname = choose(loop_query, used, level, request)
        if pname is None:
            trace.stop_reason = "no_more_providers"
            break
        used.add(pname)
        provider = get(pname)
        if provider is None:
            continue

        result = provider.search(SearchRequest(
            query=loop_query, mode=request.mode, max_results=request.max_results,
            provider_hint=request.provider_hint))
        results.append(result)
        budget.consume(1, result.estimated_cost)
        trace.providers_used.append(pname)
        trace.capabilities_used.append(cap)
        trace.queries += 1
        trace.rounds += 1
        trace.estimated_cost += result.estimated_cost

        # 决策平面 Source Policy：证据层归一化 + 权威度赋值
        evidences = dedupe(evidences + normalize(result), request.max_results)
        evidences = apply_source_policy(request.query, evidences)

        # 足够？→ 停止
        if assess(request.query, evidences, results, level):
            trace.stop_reason = "sufficient_information"
            break
        # 不够 → 先规则找机械缺口
        last_gap = detect_gap(request.query, evidences, results, level, budget)
        # 读页闭环：S3/S4 且已有 URL 但 snippet 不足 → 抓 1-2 页补正文
        if last_gap is not None and level in (SearchLevel.S3, SearchLevel.S4)                 and budget.can_continue:
            fetched, fetched_any = _fetch_missing_pages(evidences, results)
            if fetched_any:
                evidences = dedupe(evidences + fetched, request.max_results)
                evidences = apply_source_policy(request.query, evidences)
                if assess(request.query, evidences, results, level):
                    trace.stop_reason = "sufficient_information"
                    break
        # 深度档 + 模型启用 → 用模型判语义缺口（规则机械判断之外，决定"值不值得继续"）
        if level in (SearchLevel.S3, SearchLevel.S4)                 and Defaults.GAP_MODEL_ENABLED and not model_gap_checked:
            model_gap_checked = True
            model_gap = detect_gap_with_model(request.query, evidences, results)
            if model_gap is not None:
                last_gap = model_gap  # 模型缺口覆盖规则缺口（更了解语义还缺什么）
        # 补搜价值判断：importance 达标 且 expected_value 达标（价值 > 成本）
        if last_gap is None or last_gap.importance < 0.5                 or last_gap.expected_value < 0.5:
            trace.stop_reason = "no_clear_gap"
            break
        # 有缺口 → 记录并继续循环（预算不足时顶部决定 escalate）
        trace.last_gap = last_gap.to_dict()

    evidences = _rank_evidence(request.query, evidences)
    trace.searched = True
    trace.latency_ms = sum(r.latency_ms for r in results)
    if not trace.stop_reason:
        trace.stop_reason = "budget_exhausted"
    confidence = compute_confidence(request.query, evidences, results,
                                    level, True)

    n_prov = len({r.provider for r in results if r.items or r.answer})
    resp = SearchResponse(query=request.query,
                          answer=_pick_answer(results),
                          results=evidences,
                          trace=trace,
                          confidence=confidence,
                          cross_validated=n_prov >= 2)
    # 用量日志（token 明细从各 Provider 的 raw_metadata 汇总，不阻塞主流程）
    try:
        sb_tokens = {}
        for r in results:
            tk = r.raw_metadata.get("tokens") if isinstance(r.raw_metadata, dict) else None
            if tk:
                sb_tokens[r.provider] = sb_tokens.get(r.provider, 0) + tk
        _usage.record(resp, sb_tokens)
    except Exception:
        pass
    return resp
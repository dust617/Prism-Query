"""Depth & Budget Controller：决定"应该搜多深"并约束成本。

核心思想（用户文档）：
    "该不该搜"（trigger）和"该搜多深"（depth）完全拆开。

SearchDepthScore = 问题覆盖面 + 来源冲突程度 + 结论重要程度 + 所需来源多样性

映射到内部五级 S0-S4，再由 mode 决定预算上限。
"""
from __future__ import annotations

import re

from .models import SearchLevel, SearchMode

# 深度维度关键词
_COVERAGE = re.compile(
    r"比较|对比|分析|调研|研究|市场|推荐|哪个好|优缺点|趋势|报告|评估|"
    r"方案|选择|选项|格局|竞争|行业|机会|盘点|行情|该不该|值不值得|要不要|"
    r"compare|analysis|research|market|recommend|pros|cons|trend|report|"
    r"evaluate|options|landscape|competition|opportunity"
)
_CONFLICT = re.compile(
    r"争议|质疑|真假|口碑|评价|看法|社区|反馈|吐槽|靠谱吗|可信吗|"
    r"controversy|dispute|review|feedback|opinion|community|reliable"
)
_IMPORTANCE = re.compile(
    r"决定|投资|采购|决策|创业|风险|大额|重要|关键|该不该|值不值得|要不要|"
    r"critical|investment|decision|risk|important|budget|选型"
)
_DIVERSITY = re.compile(
    r"比较|对比|竞品|多家|不同|行业|厂商|供应商|哪个好|alternatives|"
    r"compare|competitor|different|industry|providers|which|竞争|格局|竞品对比"
)


def _score(regex: re.Pattern, text: str) -> float:
    return 1.0 if regex.search(text) else 0.0


def compute_depth_score(query: str) -> float:
    dims = {
        "coverage": _score(_COVERAGE, query),
        "conflict": _score(_CONFLICT, query),
        "importance": _score(_IMPORTANCE, query),
        "diversity": _score(_DIVERSITY, query),
    }
    # 权重：覆盖面 + 多样性 是核心，冲突和重要性为加分
    return 0.35 * dims["coverage"] + 0.25 * dims["diversity"] \
        + 0.20 * dims["conflict"] + 0.20 * dims["importance"]


# mode -> 默认深度档
_MODE_LEVEL = {
    SearchMode.ECONOMY: SearchLevel.S1,
    SearchMode.BALANCED: SearchLevel.S2,
    SearchMode.QUALITY: SearchLevel.S3,
    SearchMode.DEEP: SearchLevel.S4,
}


def decide_level(need_score: float, depth_score: float,
                 mode: SearchMode) -> SearchLevel:
    """根据 need_score + depth_score 决定 S0-S4。

    - need_score 低于触发阈值 → S0（不搜，由 orchestrator 拦截）
    - AUTO 模式：both 高分走高，否则走低
    """
    if mode == SearchMode.AUTO:
        # 简单事实（need 中高、depth 低）→ S1/S2
        if depth_score < 0.3:
            return SearchLevel.S1 if need_score < 0.6 else SearchLevel.S2
        if depth_score < 0.6:
            return SearchLevel.S2 if need_score < 0.7 else SearchLevel.S3
        return SearchLevel.S3 if need_score < 0.8 else SearchLevel.S4
    return _MODE_LEVEL.get(mode, SearchLevel.S2)


# 各深度的预算上限 (initial_queries, max_queries, max_rounds)
# initial 是首次放宽的预算；max 是动态升级后的上限（防止失控）
_LEVEL_BUDGET = {
    SearchLevel.S1: (1, 3, 2),
    SearchLevel.S2: (2, 4, 2),
    SearchLevel.S3: (4, 8, 3),
    SearchLevel.S4: (8, 12, 4),
}


class Budget:
    """搜索预算。任何循环先问 can_continue，防止无限搜索。

    采用 Initial + Max 两档：
    - 初始用 initial 预算（S1 可能 1 次就够）
    - 发现缺口时通过 escalate() 动态放宽到 max（不影响最终深度声明）
    """

    def __init__(self, level: SearchLevel, max_cost: float | None = None,
                 max_queries: int | None = None):
        q, qmax, r = _LEVEL_BUDGET.get(level, (2, 4, 2))
        self.level = level
        self.initial_queries = q
        self.max_queries = max_queries or qmax
        self.max_cost = max_cost if max_cost is not None else 0.20
        self.used_queries = 0
        self.used_cost = 0.0
        self.round = 0
        self.max_rounds = r
        self.escalated = False

    @property
    def can_continue(self) -> bool:
        return (self.used_queries < self.initial_queries
                and self.used_cost < self.max_cost
                and self.round < self.max_rounds)

    def can_escalate(self) -> bool:
        """是否还能动态升级（预算还没到绝对上限）。"""
        return (self.used_queries < self.max_queries
                and self.round < self.max_rounds)

    def escalate(self) -> None:
        """动态升级：放宽初始预算到绝对值上限（如 S1→S2/S3 的量）。"""
        self.initial_queries = self.max_queries
        # 轮次上限同步放宽到查询上限，避免轮次先卡死
        self.max_rounds = max(self.max_rounds, self.max_queries)
        self.escalated = True

    def consume(self, queries: int = 1, cost: float = 0.0) -> None:
        self.used_queries += queries
        self.used_cost += cost
        self.round += 1
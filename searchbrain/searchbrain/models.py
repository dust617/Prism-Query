"""SearchBrain 数据模型。

所有 Provider 返回统一结构，核心系统不感知厂商差异。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SearchMode(str, Enum):
    """用户可见的搜索模式。系统内部映射到 S0-S4 深度档。"""
    AUTO = "auto"
    ECONOMY = "economy"
    BALANCED = "balanced"
    QUALITY = "quality"
    DEEP = "deep"


class SearchLevel(str, Enum):
    """内部五级深度策略（用户文档定义）。"""
    S0 = "S0"  # 不搜索
    S1 = "S1"  # 1 次廉价搜索
    S2 = "S2"  # 1 主源 + 必要时补 1 次
    S3 = "S3"  # 2-3 来源 + 补漏
    S4 = "S4"  # Research Agent / 多轮


@dataclass
class SearchRequest:
    query: str
    mode: SearchMode = SearchMode.AUTO
    max_results: int = 8
    freshness_days: Optional[int] = None          # 限时搜索
    domains: list[str] = field(default_factory=list)   # 限定域名
    exclude_domains: list[str] = field(default_factory=list)
    provider_hint: Optional[str] = None           # 手动指定 Provider
    max_cost: Optional[float] = None              # 美元上限
    max_queries: Optional[int] = None             # 查询次数上限
    require_citations: bool = True


@dataclass
class SearchItem:
    title: str
    url: str
    snippet: str = ""
    source: str = ""                              # 哪个 Provider 返回
    published_at: Optional[str] = None
    score: float = 0.0


@dataclass
class ProviderResult:
    provider: str
    query: str
    items: list[SearchItem] = field(default_factory=list)
    answer: Optional[str] = None                  # 问答型 Provider 的总结
    latency_ms: int = 0
    estimated_cost: float = 0.0                   # 美元
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class Evidence:
    """证据层统一结构：所有 Provider 的原始结果最终都归一化为 Evidence。

    source_type 标识“这是什么类型的证据”（官方文档/社区/社媒/新闻/技术），
    供 Source Policy 和评估层使用。
    """
    url: str
    title: str = ""
    snippet: str = ""
    source_type: str = "web"          # official_docs/community/social/news/technical/web
    provider: str = ""
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    relevance: float = 0.0            # 与问题的相关性
    authority: float = 0.0            # 该类型来源的权威度（由 Policy 决定，非固定）


@dataclass
class InfoGap:
    """信息缺口。补搜必须对应明确缺口，且满足价值 > 成本才允许继续。"""
    description: str
    importance: float = 0.5                       # 0-1
    preferred_source_type: str = "web"            # 这个缺口最好用什么类型的源补
    suggested_query: str = ""
    expected_value: float = 0.5                   # 补齐后预计价值 0-1


@dataclass
class SearchTrace:
    """一次搜索的完整轨迹，用于调试和成本核算。"""
    level: str = SearchLevel.S0.value
    need_score: float = 0.0
    depth_score: float = 0.0
    providers_used: list[str] = field(default_factory=list)
    capabilities_used: list[str] = field(default_factory=list)
    queries: int = 0
    rounds: int = 0
    estimated_cost: float = 0.0
    latency_ms: int = 0
    stop_reason: str = ""


@dataclass
class SearchResponse:
    query: str
    answer: Optional[str] = None
    results: list[Evidence] = field(default_factory=list)  # 归一化后的证据层
    trace: SearchTrace = field(default_factory=SearchTrace)
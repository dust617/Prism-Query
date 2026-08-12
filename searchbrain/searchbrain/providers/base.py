"""Provider 抽象基类与注册。

所有 Provider 实现统一的 search() 接口，返回 ProviderResult。
核心系统不感知厂商差异；新增搜索源只需实现一个类并注册。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from ..models import ProviderResult, SearchRequest


class SearchProvider(ABC):
    name: str = ""
    # 统一能力标签（不再把所有东西都当“搜索引擎”）：
    #   search_web      通用网页搜索
    #   search_social   社媒/舆情搜索（X/Reddit/论坛）
    #   search_code     GitHub/代码搜索
    #   fetch_url       抓取指定 URL
    #   extract_page    网页结构化提取
    #   crawl_site      整站/列表抓取
    #   research        多步深度研究
    #   answer_with_citations  问答+逐条引用
    capabilities: set[str] = set()
    # 成本档：low / medium / high
    cost_level: str = "medium"

    @abstractmethod
    def search(self, request: SearchRequest) -> ProviderResult:
        """执行一次搜索，返回统一结构。"""

    def supports(self, cap: str) -> bool:
        return cap in self.capabilities

    def _timed(self, fn, request: SearchRequest) -> ProviderResult:
        t0 = time.time()
        result = fn(request)
        result.latency_ms = int((time.time() - t0) * 1000)
        return result


# 注册表：name -> provider 实例（由 register.py 或各模块填充）
_PROVIDERS: dict[str, SearchProvider] = {}


def register(provider: SearchProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get(name: str) -> Optional[SearchProvider]:
    return _PROVIDERS.get(name)


def available() -> list[SearchProvider]:
    return list(_PROVIDERS.values())
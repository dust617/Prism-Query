"""智谱 GLM Web Search Provider（独立 Raw Search，中文强）。

实测：0.6-1.6s，返回结构化结果，支持 search_std/search_pro 引擎。
成本：search_std ¥0.01、search_pro ¥0.03/次（约 $0.004-0.005）。
"""
from __future__ import annotations

import json
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
_HEADERS = {"Content-Type": "application/json"}


class GLMProvider(SearchProvider):
    name = "glm"
    capabilities = {"search_web", "research"}
    cost_level = "low"
    _engine = "search_pro"  # 默认较高质量中文引擎

    def __init__(self, engine: str | None = None):
        self._engine = engine or self._engine
        self._key = get_key("ZHIPU_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        body = {
            "search_query": request.query,
            "search_engine": self._engine,
            "search_model": "glm-4.7",
        }
        req = urllib.request.Request(
            _URL, data=json.dumps(body).encode(),
            headers={**_HEADERS, "Authorization": f"Bearer {self._key}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
        except Exception as exc:  # 网络/限流等，向上带上下文
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)})
        items = []
        for r_ in data.get("search_result", [])[: request.max_results]:
            items.append(SearchItem(
                title=r_.get("title", ""),
                url=r_.get("link", ""),
                snippet=r_.get("content", ""),
                source=self.name,
                published_at=r_.get("publish_date"),
            ))
        return ProviderResult(provider=self.name, query=request.query,
                              items=items,
                              raw_metadata=data.get("search_intent", []),
                              estimated_cost=0.005)
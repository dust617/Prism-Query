"""Tavily Provider（独立 SERP 搜索，简单、agent 友好，带 answer）。

实测：返回结构化结果 + score + AI answer。
成本：免费 1000 credits/月；超出 pay-as-you-go（basic=1 credit/$0.008、advanced=2 credits）。
"""
from __future__ import annotations

import json
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_URL = "https://api.tavily.com/search"


class TavilyProvider(SearchProvider):
    name = "tavily"
    capabilities = {"search_web", "answer_with_citations", "global", "cheap"}
    cost_level = "low"

    def __init__(self):
        self._key = get_key("TAVILY_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        body = {
            "api_key": self._key,
            "query": request.query,
            "max_results": min(request.max_results, 8),
            "include_answer": True,
        }
        req = urllib.request.Request(
            _URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
        except Exception as exc:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)})
        items = []
        for r_ in data.get("results", [])[: request.max_results]:
            items.append(SearchItem(
                title=r_.get("title", ""),
                url=r_.get("url", ""),
                snippet=r_.get("content", ""),
                source=self.name,
                score=float(r_.get("score") or 0.0),
            ))
        return ProviderResult(provider=self.name, query=request.query,
                              items=items, answer=data.get("answer"),
                              estimated_cost=0.003)
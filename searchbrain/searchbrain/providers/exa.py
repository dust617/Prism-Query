"""Exa Provider（语义搜索，擅长找项目/GitHub/报告；/answer 带引用）。

实测：/search 1.5-2s，/answer 1.7s。
成本：/search $7/1k、/answer $5/1k 请求（约 $0.005-0.007/次）。
"""
from __future__ import annotations

import json
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_SEARCH = "https://api.exa.ai/search"
_ANSWER = "https://api.exa.ai/answer"


class ExaProvider(SearchProvider):
    name = "exa"
    capabilities = {"search_web", "fetch_url", "research", "answer_with_citations"}
    cost_level = "medium"

    def __init__(self):
        self._key = get_key("EXA_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        # 语义搜索找项目/报告
        body = {"query": request.query,
                "numResults": min(request.max_results, 10),
                "type": "auto"}
        result = self._post(_SEARCH, body)
        items = []
        for r_ in result.get("results", []):
            items.append(SearchItem(
                title=r_.get("title", ""),
                url=r_.get("url", ""),
                snippet=(r_.get("text") or r_.get("snippet") or "")[:300],
                source=self.name,
                score=float(r_.get("score") or 0.0),
            ))
        return ProviderResult(provider=self.name, query=request.query,
                              items=items, estimated_cost=0.007)

    def answer(self, query: str) -> ProviderResult:
        """问答式搜索，返回带引用的总结。适合需要直接答案的场景。"""
        if not self._key:
            return ProviderResult(provider=self.name, query=query,
                                  raw_metadata={"error": "no key"})
        body = {"query": query, "text": True}
        result = self._post(_ANSWER, body)
        items = []
        for s in result.get("sources", [])[:5]:
            items.append(SearchItem(title=s.get("title", ""),
                                    url=s.get("url", ""), source=self.name))
        return ProviderResult(provider=self.name, query=query,
                              items=items, answer=result.get("answer"),
                              estimated_cost=0.005)

    def _post(self, url: str, body: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "x-api-key": self._key}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as exc:
            return {"results": [], "error": str(exc)}
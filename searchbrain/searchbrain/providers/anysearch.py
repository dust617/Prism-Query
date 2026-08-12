"""AnySearch Provider（全文正文搜索，区域感知，免费额度高）。

实测：返回整页内容（截断），支持 cn/intl 区域。
成本：免费约 1000 次/天（Key 已配置）。
"""
from __future__ import annotations

import json
import re
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_URL = "https://api.anysearch.com/v1/search"
_ZH = re.compile(r"[\u4e00-\u9fff]")


class AnySearchProvider(SearchProvider):
    name = "anysearch"
    capabilities = {"search_web", "global", "cheap"}
    cost_level = "low"

    def __init__(self):
        self._key = get_key("ANYSEARCH_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        body = {"query": request.query,
                "max_results": min(request.max_results, 8)}
        # 区域感知：中文问题走 cn，否则 intl
        body["region"] = "cn" if _ZH.search(request.query) else "intl"
        req = urllib.request.Request(
            _URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
        except Exception as exc:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)})
        results = data.get("data", {}).get("results", [])
        items = []
        for r_ in results[: request.max_results]:
            items.append(SearchItem(
                title=r_.get("title", ""),
                url=r_.get("url", ""),
                snippet=(r_.get("content") or r_.get("snippet") or "")[:300],
                source=self.name,
            ))
        return ProviderResult(provider=self.name, query=request.query,
                              items=items, estimated_cost=0.001)
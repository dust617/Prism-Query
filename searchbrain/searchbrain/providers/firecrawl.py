"""Firecrawl Provider（搜索 + 抓页，网页理解层）。

实测：/search 6-12s 命中官方页；/scrape 返回干净 markdown。
成本：按 credits（免费额度内 0，之后按量）。
"""
from __future__ import annotations

import json
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_SEARCH = "https://api.firecrawl.dev/v2/search"
_SCRAPE = "https://api.firecrawl.dev/v2/scrape"


class FirecrawlProvider(SearchProvider):
    name = "firecrawl"
    capabilities = {"fetch_url", "extract_page", "crawl_site", "search_web", "global"}
    cost_level = "medium"

    def __init__(self):
        self._key = get_key("FIRECRAWL_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        body = {"query": request.query, "limit": min(request.max_results, 8)}
        req = urllib.request.Request(
            _SEARCH, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
        except Exception as exc:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)})
        items = []
        web = data.get("data", {}).get("web", []) if isinstance(
            data.get("data"), dict) else []
        for r_ in web[: request.max_results]:
            items.append(SearchItem(
                title=r_.get("title", ""),
                url=r_.get("url", ""),
                snippet=r_.get("description", ""),
                source=self.name,
            ))
        return ProviderResult(provider=self.name, query=request.query,
                              items=items, estimated_cost=0.003)

    def scrape(self, url: str, max_chars: int = 2000) -> str:
        """抓取指定 URL 正文（markdown）。失败返回空串。"""
        if not self._key:
            return ""
        body = {"url": url, "formats": ["markdown"], "onlyMainContent": True}
        req = urllib.request.Request(
            _SCRAPE, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode())
            md = data.get("data", {}).get("markdown", "")
            return md[:max_chars]
        except Exception:
            return ""
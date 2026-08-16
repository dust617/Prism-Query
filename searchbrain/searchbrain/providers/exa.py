"""Exa Provider（语义搜索，擅长找项目/GitHub/报告；/answer 带引用）。

两条路径：
  1. 有 EXA_API_KEY → 官方 API（/search $7/1k、/answer $5/1k 请求，约 $0.005-0.007/次）。
  2. 无 key → 零配置走 Exa 托管 MCP（mcp.exa.ai/mcp，免费额度内可用）。
     关键：必须带浏览器 User-Agent（裸 Python-urllib 会被 403）；
     rate limit(429) 时提示加 key 升级。
"""
from __future__ import annotations

import json
import re
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_SEARCH = "https://api.exa.ai/search"
_ANSWER = "https://api.exa.ai/answer"
_MCP_URL = "https://mcp.exa.ai/mcp"
_MCP_TOOL = "web_search_exa"         # 返回格式化文本块(Title/URL/Highlights)
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class ExaProvider(SearchProvider):
    name = "exa"
    capabilities = {"search_web", "fetch_url", "research", "answer_with_citations", "global"}
    cost_level = "medium"

    def __init__(self):
        self._key = get_key("EXA_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return self._search_mcp(request)   # 零配置降级：无需 key
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

    def _search_mcp(self, request: SearchRequest) -> ProviderResult:
        """零配置：无 key 时经 Exa 托管 MCP 搜索（免费额度内）。"""
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": _MCP_TOOL,
                            "arguments": {"query": request.query,
                                           "type": "auto",
                                           "numResults": min(request.max_results, 5)}}}
        req = urllib.request.Request(
            f"{_MCP_URL}?tools={_MCP_TOOL}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "x-exa-source": "searchbrain",
                     "User-Agent": _UA},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read().decode("utf-8", "ignore")
        except Exception as exc:
            msg = str(exc)
            if "403" in msg:
                msg = "Exa MCP 403（UA 被拦/额度）；配置 EXA_API_KEY 走官方 API"
            elif "429" in msg:
                msg = "Exa MCP 免 key 额度暂满(429)；配置 EXA_API_KEY 升级"
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": msg[:200], "path": "mcp"})
        text = self._mcp_text(raw)
        if not text:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "Exa MCP 空响应", "path": "mcp"})
        items = []
        for block in re.split(r"(?m)(?=^Title: )", text):
            m_t = re.match(r"^Title: (.+)", block)
            m_u = re.search(r"^URL: (.+)", block, re.M)
            m_c = re.search(r"\n(?:Highlights:|Text:)\s*\n", block)
            if not m_u:
                continue
            url = m_u.group(1).strip()
            content = ""
            if m_c:
                content = block[m_c.end():].strip()
            items.append(SearchItem(
                title=m_t.group(1).strip() if m_t else url,
                url=url,
                snippet=content[:300],
                source=self.name,
            ))
        return ProviderResult(provider=self.name, query=request.query,
                              items=items, estimated_cost=0.0,
                              raw_metadata={"path": "mcp"})

    @staticmethod
    def _mcp_text(raw: str) -> str:
        """从 SSE 响应（data: {...}）提取 result.content 的 text。"""
        for line in raw.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            if obj.get("result"):
                for c in (obj["result"].get("content") or []):
                    if isinstance(c, dict) and c.get("type") == "text":
                        return c.get("text") or ""
        return ""

    def answer(self, query: str) -> ProviderResult:
        """问答式搜索，返回带引用的总结。适合需要直接答案的场景。"""
        if not self._key:
            return ProviderResult(provider=self.name, query=query,
                                  raw_metadata={"error": "no key", "path": "mcp"})
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
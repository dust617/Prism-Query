"""DeepSeek Provider（/responses + web_search，自动改写多查询 + 开页验证）。

实测：6-14s，自动把 query 拆成多个查询，返回真实搜索内容。
成本：模型 token 计费（deepseek-chat 输入 $0.27/1M、输出 $1.10/1M 量级）。
"""
from __future__ import annotations

import json
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_URL = "https://api.deepseek.com/responses"


class DeepSeekProvider(SearchProvider):
    name = "deepseek"
    capabilities = {"search_web", "research", "answer_with_citations"}
    cost_level = "low"

    def __init__(self):
        self._key = get_key("DEEPSEEK_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        body = {
            "model": "deepseek-chat",
            "input": request.query,
            "tools": [{"type": "web_search"}],
        }
        req = urllib.request.Request(
            _URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode())
        except Exception as exc:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)})
        # 提取 web_search_call（自动改写的查询）和最终文本
        rewritten = []
        text = ""
        for o in data.get("output", []):
            if o.get("type") == "web_search_call":
                rewritten = o.get("action", {}).get("queries", [])
            elif o.get("type") == "message" and o.get("content"):
                text = o["content"][0].get("text", "")
        usage = data.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        cost = tokens / 1_000_000 * 0.5  # 粗略混合费率
        return ProviderResult(provider=self.name, query=request.query,
                              items=[], answer=text,
                              raw_metadata={"rewritten_queries": rewritten},
                              estimated_cost=cost)
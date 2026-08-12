"""Perplexity Provider（经 OpenRouter，问答式搜索，国外强，带引用）。

实测：sonar 3s / sonar-pro 4.4s / sonar-pro-search 16s，补智谱国外盲区。
成本：sonar 约 $1/1M token；一次搜索回答约几百 token，估 $0.0005-0.002/次。
"""
from __future__ import annotations

import json
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "perplexity/sonar"  # 轻量均衡


class PerplexityProvider(SearchProvider):
    name = "perplexity"
    capabilities = {"search_web", "research", "answer_with_citations"}
    cost_level = "low"

    def __init__(self, model: str | None = None):
        self._model = model or _DEFAULT_MODEL
        self._key = get_key("OPENROUTER_API_KEY")

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": request.query}],
            "max_tokens": 800,
        }
        req = urllib.request.Request(
            _URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
        except Exception as exc:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)})
        if "choices" not in data:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata=data)
        content = data["choices"][0]["message"].get("content", "")
        # 粗略按 token 估算成本（sonar 输出 $1/1M，输入 $1/1M）
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens") or (len(content) // 4)
        cost = tokens / 1_000_000 * 1.0
        return ProviderResult(provider=self.name, query=request.query,
                              items=[], answer=content,
                              raw_metadata=usage, estimated_cost=cost)
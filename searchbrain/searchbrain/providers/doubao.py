"""豆包 Provider（火山方舟联网内容插件，模型自动搜，中文/全球都可用）。

实测：doubao-seed-2-1-pro-260628 + responses + web_search tool 真实触发搜索，
返回带引用的完整回答。免费 2 万次/月（联网内容插件）。
注意：模型自动判断是否搜索（B 类），耗时较长（约 30-70s），适合深度/补充。
"""
from __future__ import annotations

import json
import urllib.request

from ..config import get_key
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"


class DoubaoProvider(SearchProvider):
    name = "doubao"
    capabilities = {"search_web", "research", "answer_with_citations",
                    "zh", "global"}
    cost_level = "medium"

    def __init__(self):
        self._key = get_key("ARK_API_KEY")
        self._model = get_key("DOUBAO_MODEL") or "doubao-seed-2-1-pro-260628"

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._key:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no key"})
        body = {
            "model": self._model,
            "input": request.query,
            "tools": [{"type": "web_search"}],
        }
        req = urllib.request.Request(
            _URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode())
        except Exception as exc:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)})
        # 提取 web_search_call（是否触发搜索）和最终回答
        searched = False
        text = ""
        for o in data.get("output", []):
            if o.get("type") == "web_search_call":
                searched = True
            elif o.get("type") == "message" and o.get("content"):
                text = o["content"][0].get("text", "")
        return ProviderResult(provider=self.name, query=request.query,
                              items=[], answer=text or None,
                              raw_metadata={"searched": searched},
                              estimated_cost=0.005)
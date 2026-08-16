"""keyless DuckDuckGo Provider（免 API key 的免费英文兜底源）。

POST html.duckduckgo.com/html/，浏览器 UA 匿名调用；stdlib 解析。
特征：免费、无需凭据；偶发验证码/限流（429/403 时如实返回错误走路由兜底）。
不承担中文/语义检索场景（由 GLM/Exa 覆盖）。
"""
from __future__ import annotations

import html as _html
import re
import urllib.parse
import urllib.request

from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_URL = "https://html.duckduckgo.com/html/"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 结果卡片：标题链接 + 摘要
_RE_LINK = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                      re.S)
_RE_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)


def _real_url(redirect: str) -> str:
    """DDG HTML 的结果链接是重定向包装，解出真实 URL。"""
    if "duckduckgo.com/l/?" in redirect:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(redirect).query)
        target = q.get("uddg") or q.get("uddg")
        if target:
            return urllib.parse.unquote(target[0])
    return redirect


class DuckDuckGoProvider(SearchProvider):
    name = "ddg"
    capabilities = {"search_web", "free", "cheap"}   # 免费、英文向
    cost_level = "low"

    def search(self, request: SearchRequest) -> ProviderResult:
        data = urllib.parse.urlencode({"q": request.query}).encode()
        req = urllib.request.Request(
            _URL, data=data,
            headers={"User-Agent": _UA,
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                page = r.read().decode("utf-8", "ignore")
        except Exception as exc:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": str(exc)[:200]})

        links = _RE_LINK.findall(page)
        snippets = _RE_SNIPPET.findall(page)
        items = []
        for i, (href, title) in enumerate(links[: request.max_results]):
            url = _real_url(href)
            snippet = re.sub(r"<[^>]+>", "", snippets[i]) if i < len(snippets) else ""
            snippet = _html.unescape(snippet).strip()
            items.append(SearchItem(
                title=_html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
                or url,
                url=url, snippet=snippet[:200], source=self.name))
        return ProviderResult(provider=self.name, query=request.query,
                              items=items, estimated_cost=0.0)
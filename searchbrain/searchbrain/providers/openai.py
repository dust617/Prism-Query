"""OpenAI Web Search Provider（Responses API 的 web_search 工具）。

两条路径（互斥，按可用性选择）：
  1. 已登录的 OpenAI 会话（首选）—— 复用本机 Pi/Codex 已保存的登录凭据，
     调用 OpenAI 托管 web_search 能力（订阅内不计费）。已在域内实测打通。
  2. 真 API Key —— 调 api.openai.com/v1/responses（按量计费）。
  3. Responses 兼容网关 —— OPENAI_RESPONSES_URL 覆盖端点（配合 API Key）。

凭据统一由 config.resolve_openai_auth() 解析；secret 绝不落日志/输出。
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request

from ..config import resolve_openai_auth
from ..models import ProviderResult, SearchItem, SearchRequest
from .base import SearchProvider

_SEARCH_TIMEOUT = 90
_DEFAULT_MODEL = "gpt-5.6-terra"          # 同 pi-web-access 的 terra 默认档
_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
_OPENAI_URL = "https://api.openai.com/v1/responses"
_UTM_PARAM = "utm_source=openai"

_INSTRUCTIONS = (
    "Search the web and return a concise answer grounded only in the web results. "
    "Include clickable source citations in the response text when possible."
)


def _redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "<REDACTED>")
    return text


def _jwt_payload(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


def _is_codex_jwt(token: str) -> bool:
    return "https://api.openai.com/auth" in _jwt_payload(token)


def _chatgpt_account_id(token: str) -> str | None:
    auth = _jwt_payload(token).get("https://api.openai.com/auth")
    if isinstance(auth, dict):
        v = auth.get("chatgpt_account_id")
        if isinstance(v, str) and v:
            return v
    return None


def _clean_url(raw: str) -> str:
    """去掉 OpenAI 来源追踪参数（同 pi-web-access）。"""
    try:
        head, _, tail = raw.partition("?")
        if _UTM_PARAM not in tail:
            return raw
        params = [p for p in tail.split("&") if p and p != _UTM_PARAM]
        return head + ("?" + "&".join(params) if params else "")
    except Exception:
        return raw.replace(f"?{_UTM_PARAM}", "")


class OpenAIProvider(SearchProvider):
    """OpenAI web_search：订阅授权(Codex) 或 API Key，或 Responses 网关。

    kind ∈ {"codex", "key"}。同一 provider 实例固定一种路径。
    """
    name = "openai"
    capabilities = {"search_web", "research", "answer_with_citations",
                    "global", "free", "cheap"}  # 订阅内不计费 → free
    cost_level = "low"

    def __init__(self):
        self._secret, self._kind = resolve_openai_auth() or (None, "codex")
        self._model = os.environ.get("OPENAI_SEARCH_MODEL") or _DEFAULT_MODEL
        if self._kind == "codex":
            # 订阅授权：响应里带 url_citation，足够构建证据层
            self._url = _CODEX_URL
            self._extra_headers: dict[str, str] = {
                "OpenAI-Beta": "responses=experimental",
            }
            if _is_codex_jwt(self._secret or ""):
                acc = _chatgpt_account_id(self._secret or "")
                if acc:
                    self._extra_headers["chatgpt-account-id"] = acc
                self._extra_headers["originator"] = "searchbrain"
        else:
            gateway = os.environ.get("OPENAI_RESPONSES_URL") or None
            self._url = gateway or _OPENAI_URL
            self._extra_headers = {}

    def search(self, request: SearchRequest) -> ProviderResult:
        if not self._secret:
            return ProviderResult(provider=self.name, query=request.query,
                                  raw_metadata={"error": "no openai auth"})
        body = {
            "model": self._model,
            "instructions": _INSTRUCTIONS,
            "input": [{"role": "user",
                       "content": [{"type": "input_text", "text": request.query}]}],
            "tools": [{"type": "web_search"}],
            "include": ["web_search_call.action.sources"],
            "store": False,
            "stream": True,
            "tool_choice": "required",
            "parallel_tool_calls": True,
        }
        headers = {
            "Authorization": f"Bearer {self._secret}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        req = urllib.request.Request(
            self._url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            output = self._stream(req)
        except Exception as exc:
            return ProviderResult(
                provider=self.name, query=request.query,
                raw_metadata={"error": _redact(str(exc), [self._secret or ""])[:300]})

        answer = self._extract_answer(output)
        items = self._extract_citations(output)
        if not answer and not items:
            return ProviderResult(
                provider=self.name, query=request.query,
                raw_metadata={"error": "web_search returned no answer or sources"})
        # Codex 路径费用计入订阅；API Key 路径也收窄为象征性估算
        return ProviderResult(
            provider=self.name, query=request.query,
            items=items, answer=answer,
            estimated_cost=0.0 if self._kind == "codex" else 0.002,
            raw_metadata={"auth": "codex" if self._kind == "codex" else "key",
                          "model": self._model})

    # ---- 内部：SSE 流解析 ----
    @staticmethod
    def _stream(req: urllib.request.Request) -> list[dict]:
        items: list[dict] = []
        done: dict | None = None
        with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    ev = json.loads(payload)
                except Exception:
                    continue
                if ev.get("type") == "response.output_item.done" and \
                        isinstance(ev.get("item"), dict):
                    items.append(ev["item"])
                if ev.get("type") in ("response.done", "response.completed") and \
                        isinstance(ev.get("response"), dict):
                    done = ev["response"]
        out = done.get("output") if isinstance(done, dict) else None
        return out if isinstance(out, list) and out else items

    @staticmethod
    def _extract_answer(output: list[dict]) -> str:
        parts: list[str] = []
        for it in output:
            if not isinstance(it, dict) or it.get("type") != "message":
                continue
            for c in it.get("content") or []:
                if isinstance(c, dict) and isinstance(c.get("text"), str) \
                        and c["text"].strip():
                    parts.append(c["text"])
        return "\n".join(parts).strip()

    @classmethod
    def _extract_citations(cls, output: list[dict]) -> list[SearchItem]:
        results: list[SearchItem] = []
        seen: set[str] = set()

        def add(title: str | None, url: str | None) -> None:
            if not isinstance(url, str) or not url.strip():
                return
            u = _clean_url(url)
            if u in seen:
                return
            seen.add(u)
            results.append(SearchItem(
                title=title or u, url=u, source="openai"))

        for it in output:
            if not isinstance(it, dict):
                continue
            if it.get("type") == "message":
                for c in it.get("content") or []:
                    if not isinstance(c, dict):
                        continue
                    for a in c.get("annotations") or []:
                        if isinstance(a, dict) and a.get("type") == "url_citation":
                            add(a.get("title"), a.get("url"))
            elif it.get("type") == "web_search_call":
                for group in (_safe_get(it, ("action", "sources")),
                              it.get("sources"), it.get("results")):
                    if not isinstance(group, list):
                        continue
                    for s in group:
                        if not isinstance(s, dict):
                            continue
                        add(s.get("title") or s.get("caption"),
                            s.get("url") or s.get("source_website_url"))
        return results


def _safe_get(item: dict, keys: tuple[str, ...]):
    cur = item
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur
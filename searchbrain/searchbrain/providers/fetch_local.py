"""本地网页抓取管线（fetch_url 闭环的免费降级路径）。

顺序：本地直抓（SSRF 防护 + 轻量正文提取）→ Firecrawl（有 key）→ Jina Reader（免 key）。
目标：不花钱也能读页；有 Firecrawl key 时作为兜底增强 JS 渲染页面。
安全：仅 http/https；目标域名解析后逐 IP 检查私网/环回/链路本地/保留/组播，阻断；
      重定向（最多 3 跳）每跳重新校验；响应 5MB 上限；20s 超时。
"""
from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from ..config import get_key

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TIMEOUT = 20
_MAX_BYTES = 5 * 1024 * 1024        # 5MB 上限（同 pi-web-access）
_MAX_REDIRECTS = 3
_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "aside",
              "header", "form", "iframe", "svg", "video", "audio"}
_TEXT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote",
              "pre", "td", "th", "figcaption", "dt", "dd"}


class _Extract(HTMLParser):
    """轻量正文提取：正文标签文本 + title；跳过噪声标签。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._skip = 0
        self._in_title = False
        self._chunks: list[str] = []
        self._cur: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _TEXT_TAGS and not self._skip:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _TEXT_TAGS and not self._skip:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        if data.strip():
            self._cur.append(data.strip())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def _flush(self):
        if self._cur:
            self._chunks.append(" ".join(self._cur))
            self._cur = []

    def body_text(self, max_chars: int) -> str:
        self._flush()
        parts: list[str] = []
        if self.title:
            parts.append(self.title.strip())
        parts += [c for c in self._chunks if c]
        out = "\n".join(parts)
        return out[:max_chars]


_PROXY_SEGMENT = ipaddress.ip_network("198.18.0.0/15")  # RFC2544 代理虚拟出口段


def _host_ips(host: str) -> list[str]:
    """解析域名全部 A/AAAA，解析失败返回空列表。"""
    try:
        infos = socket.getaddrinfo(host, None,
                                   socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    ips: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


def _ssrf_blocked(url: str) -> str | None:
    """校验目标是否可安全直连；返回错误信息，None 表示安全。"""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "invalid url"
    if parts.scheme not in ("http", "https"):
        return f"unsupported scheme: {parts.scheme}"
    host = parts.hostname or ""
    if not host:
        return "no host"
    ips = _host_ips(host)
    if not ips:
        return "dns resolution failed"
    for ip in ips:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if addr in _PROXY_SEGMENT:
            # 198.18.0.0/15 RFC2544 基准测试段：本机 TUN 代理（Clash/Surge 等）
            # 常把出口流量解析到该段，属正常公网请求，放行
            continue
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast
                or addr.is_unspecified):
            return f"blocked private/loopback ip: {ip}"
    return None


def _http_get(url: str) -> bytes | None:
    """SSRF 防护下的本地直抓（重定向逐跳校验 + 大小上限）。返回 None 表示失败。"""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        blocked = _ssrf_blocked(current)
        if blocked:
            return None
        req = urllib.request.Request(
            current, headers={"User-Agent": _UA,
                              "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                if r.status in (301, 302, 303, 307, 308):
                    loc = r.headers.get("Location")
                    if not loc:
                        return None
                    current = urllib.parse.urljoin(current, loc)
                    continue
                data = r.read(_MAX_BYTES + 1)
                if len(data) > _MAX_BYTES:
                    return None
                return data
        except (urllib.error.HTTPError, urllib.error.URLError,
                socket.timeout, TimeoutError, OSError):
            return None
    return None


def _jina_reader(url: str, max_chars: int) -> str:
    """Jina Reader 免 key 兜底：服务端渲染 JS 页面，返回 markdown。

    默认关闭（本机实测 403 被风控）：设 SEARCHBRAIN_ENABLE_JINA=1 才启用。
    """
    import os as _os
    if not _os.environ.get("SEARCHBRAIN_ENABLE_JINA"):
        return ""
    req = urllib.request.Request(
        f"https://r.jina.ai/{url}", headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            body = r.read(_MAX_BYTES + 1)
        if len(body) > _MAX_BYTES:
            return ""
        text = body.decode("utf-8", "ignore")
        return text.strip()[:max_chars]
    except Exception:
        return ""


def fetch_web(url: str, max_chars: int = 2000) -> tuple[str, str]:
    """抓取网页正文（带来源标记）。

    返回 (正文, source)。source ∈ {"local", "firecrawl", "jina", ""}。
    任何环节失败都返回 ("", "")，由调用方决定是否补抓。
    """
    raw = _http_get(url)
    if raw:
        try:
            parser = _Extract()
            parser.feed(raw.decode("utf-8", "ignore"))
            text = parser.body_text(max_chars)
            if len(text.strip()) > 100:
                return text, "local"
        except Exception:
            pass
    # 本地失败/太短 → Firecrawl（有 key）
    key = get_key("FIRECRAWL_API_KEY")
    if key:
        try:
            from .firecrawl import FirecrawlProvider  # 延迟避免循环导入
            body = FirecrawlProvider().scrape(url, max_chars)
            if len(body) > 100:
                return body, "firecrawl"
        except Exception:
            pass
    # 仍失败 → Jina Reader（免 key）
    body = _jina_reader(url, max_chars)
    if len(body) > 100:
        return body, "jina"
    return "", ""
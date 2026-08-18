"""SearchBrain 极简 HTTP API（零依赖，stdlib）。

把 search() 暴露成一个本地 HTTP 服务，供任何能发 HTTP 的客户端调用：

    POST /search   {"query": "...", "mode": "auto", "search_bias": null,
                    "output": "full|compact|facts"}
    GET  /health   {"ok": true, "version": "..."}

运行：
    python -m searchbrain.http_server
    # 或指定端口：SEARCHBRAIN_HTTP_PORT=8973 python -m searchbrain.http_server

默认只监听 127.0.0.1（本机）；如需局域网访问设 SEARCHBRAIN_HTTP_HOST=0.0.0.0。
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .models import SearchMode, SearchRequest
from .orchestrator import search

_HOST = __import__("os").environ.get("SEARCHBRAIN_HTTP_HOST", "127.0.0.1")
_PORT = int(__import__("os").environ.get("SEARCHBRAIN_HTTP_PORT", "8973"))


def _handler_payload(handler: BaseHTTPRequestHandler) -> dict | None:
    """读取并解析请求体 JSON；失败返回 None 并写 400。"""
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        length = 0
    if length <= 0:
        handler._send_json({"error": "empty body"}, 400)
        return None
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        handler._send_json({"error": "invalid json"}, 400)
        return None


class SearchBrainHandler(BaseHTTPRequestHandler):
    server_version = "SearchBrain/0.1"

    # ---- HTTP 方法 ----
    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._send_json({"ok": True, "version": __version__})
            return
        if self.path == "/":
            self._send_json({"service": "SearchBrain",
                             "endpoints": ["POST /search", "GET /health"]})
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/search":
            self._send_json({"error": "not found"}, 404)
            return
        payload = _handler_payload(self)
        if payload is None:
            return
        query = (payload.get("query") or "").strip()
        if not query:
            self._send_json({"error": "query is required"}, 400)
            return
        mode_raw = payload.get("mode", "auto")
        mode = SearchMode(mode_raw) if mode_raw in SearchMode._value2member_map_ \
            else SearchMode.AUTO
        bias = payload.get("search_bias")
        try:
            request = SearchRequest(query=query, mode=mode, search_bias=bias)
            resp = search(request)
        except Exception as exc:  # 搜索内部异常不外泄细节，返回 500
            self._send_json({"error": "search failed",
                             "detail": str(exc)[:200]}, 500)
            return
        output = payload.get("output", "full")
        if output == "compact":
            body = resp.compact_dict()
        elif output == "facts":
            body = resp.facts_dict()
        else:
            body = resp.to_dict()
        self._send_json(body)

    # ---- 工具 ----
    def _send_json(self, obj, status: int = 200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()

    def log_message(self, fmt, *args):
        # 默认每请求都打日志，静音以避免污染 stdio（MCP/嵌入场景）
        pass


def create_server(host: str | None = None,
                  port: int | None = None) -> ThreadingHTTPServer:
    """构造（但不启动）服务器，便于测试与嵌入。"""
    return ThreadingHTTPServer((host or _HOST, port or _PORT),
                               SearchBrainHandler)


def main() -> int:
    server = create_server()
    print(f"SearchBrain HTTP API 监听 http://{_HOST}:{_PORT}")
    print(f"  POST /search  |  GET /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

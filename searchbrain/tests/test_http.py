"""HTTP API 集成测试：本地起服务（随机端口），验证 /health 与 /search。"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from searchbrain.http_server import create_server


class HTTPAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        return resp.status, body

    def _post(self, path, payload):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", path, body=json.dumps(payload),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        return resp.status, body

    def test_health(self) -> None:
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])

    def test_index(self) -> None:
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("search", body)

    def test_search_s0_no_network(self) -> None:
        # "解释什么是TCP" 是稳定知识，S0 不触发网络搜索，测试安全
        status, body = self._post("/search", {"query": "解释什么是TCP"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("trace", data)
        self.assertFalse(data["trace"]["searched"])

    def test_search_missing_query_400(self) -> None:
        status, body = self._post("/search", {"mode": "auto"})
        self.assertEqual(status, 400)

    def test_search_invalid_json_400(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/search", body="{not json",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 400)

    def test_unknown_route_404(self) -> None:
        status, _ = self._get("/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()

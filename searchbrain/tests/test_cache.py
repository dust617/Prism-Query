"""搜索缓存单元测试（用隔离的临时目录，不触碰真实缓存）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from searchbrain import cache
from searchbrain.models import ProviderResult, SearchItem


def _result() -> ProviderResult:
    return ProviderResult(
        provider="fake", query="解释什么是TCP",
        items=[SearchItem(title="TCP", url="http://tcp.example",
                          snippet="transmission control protocol")],
        answer=None, estimated_cost=0.001, raw_metadata={"tokens": 123},
    )


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_dir = os.environ.get("SEARCHBRAIN_CACHE_DIR")
        self._old_disable = os.environ.get("SEARCHBRAIN_DISABLE_CACHE")
        os.environ["SEARCHBRAIN_CACHE_DIR"] = self.tmp.name
        os.environ.pop("SEARCHBRAIN_DISABLE_CACHE", None)

    def tearDown(self) -> None:
        if self._old_dir is None:
            os.environ.pop("SEARCHBRAIN_CACHE_DIR", None)
        else:
            os.environ["SEARCHBRAIN_CACHE_DIR"] = self._old_dir
        if self._old_disable is None:
            os.environ.pop("SEARCHBRAIN_DISABLE_CACHE", None)
        else:
            os.environ["SEARCHBRAIN_DISABLE_CACHE"] = self._old_disable
        self.tmp.cleanup()

    def test_round_trip_hit(self) -> None:
        cache.clear()
        cache.put("fake", "解释什么是TCP", "auto", 8, _result())
        got = cache.get("fake", "解释什么是TCP", "auto", 8)
        self.assertIsNotNone(got)
        self.assertEqual(len(got.items), 1)
        # 命中：成本归零、tokens 剔除、打 cached 标记
        self.assertEqual(got.estimated_cost, 0.0)
        self.assertNotIn("tokens", got.raw_metadata)
        self.assertTrue(got.raw_metadata.get("cached"))

    def test_time_sensitive_never_cached(self) -> None:
        cache.clear()
        cache.put("fake", "现在价格多少", "auto", 8, _result())
        self.assertIsNone(cache.get("fake", "现在价格多少", "auto", 8))

    def test_empty_result_not_cached(self) -> None:
        cache.clear()
        empty = ProviderResult(provider="fake", query="q")
        cache.put("fake", "q", "auto", 8, empty)
        self.assertIsNone(cache.get("fake", "q", "auto", 8))

    def test_corrupt_file_treated_as_miss(self) -> None:
        cache.clear()
        cache.put("fake", "解释什么是TCP", "auto", 8, _result())
        # 找到缓存文件并写坏它
        files = list(Path(self.tmp.name).glob("*.json"))
        self.assertTrue(files)
        files[0].write_text("{not valid json", encoding="utf-8")
        self.assertIsNone(cache.get("fake", "解释什么是TCP", "auto", 8))

    def test_disable_via_env(self) -> None:
        os.environ["SEARCHBRAIN_DISABLE_CACHE"] = "1"
        cache.clear()
        cache.put("fake", "解释什么是TCP", "auto", 8, _result())
        self.assertIsNone(cache.get("fake", "解释什么是TCP", "auto", 8))

    def test_clear_and_stats(self) -> None:
        cache.clear()
        cache.put("fake", "解释什么是TCP", "auto", 8, _result())
        self.assertGreaterEqual(cache.stats()["entries"], 1)
        n = cache.clear()
        self.assertGreaterEqual(n, 1)
        self.assertEqual(cache.stats()["entries"], 0)


if __name__ == "__main__":
    unittest.main()

"""证据层单元测试：来源类型标签、权威度赋值、去重、词面相关性。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from searchbrain.evidence import (_source_type, apply_source_policy, dedupe,
                                  lexical_relevance, normalize)
from searchbrain.models import Evidence, ProviderResult, SearchItem
from searchbrain.policy import classify_intent


class SourceTypeTests(unittest.TestCase):
    def test_official_docs_label(self) -> None:
        self.assertEqual(_source_type("https://openai.com/docs/api"), "official_docs")
        self.assertEqual(_source_type("https://www.google.com/search"), "official_docs")

    def test_community_and_social_labels(self) -> None:
        self.assertEqual(_source_type("https://github.com/x/y"), "community")
        self.assertEqual(_source_type("https://x.com/user/status/1"), "social")

    def test_fallback_web(self) -> None:
        self.assertEqual(_source_type("https://some-random-site.example/x"), "web")


class AuthorityTests(unittest.TestCase):
    def test_official_intent_gives_official_full_authority(self) -> None:
        # 回归：official_docs 标签必须映射到策略表的 official 键（曾恒为 0.3）
        ev = Evidence(url="https://openai.com/docs", title="t", snippet="s",
                      source_type="official_docs")
        apply_source_policy("OpenAI API 支持什么参数", [ev])
        self.assertEqual(ev.authority, 1.0)

    def test_experience_intent_prefers_community(self) -> None:
        ev = Evidence(url="https://github.com/x/y/issues", title="t", snippet="s",
                      source_type="community")
        apply_source_policy("这个库好用吗 稳定性", [ev])
        self.assertEqual(ev.authority, 1.0)

    def test_generic_web_gets_default(self) -> None:
        ev = Evidence(url="https://x.example/a", title="t", snippet="s",
                      source_type="web")
        apply_source_policy("随便问问", [ev])
        self.assertEqual(ev.authority, 0.3)


class DedupeTests(unittest.TestCase):
    def _mk(self, url, provider):
        return Evidence(url=url, title="t", snippet="s", provider=provider)

    def test_dedupe_by_url(self) -> None:
        evs = [self._mk("http://a", "p1"), self._mk("http://a", "p2"),
               self._mk("http://b", "p1")]
        out = dedupe(evs, max_items=8)
        urls = {e.url for e in out}
        self.assertEqual(urls, {"http://a", "http://b"})

    def test_respects_max_items(self) -> None:
        evs = [self._mk(f"http://x/{i}", "p1") for i in range(20)]
        self.assertLessEqual(len(dedupe(evs, max_items=8)), 8)


class LexicalRelevanceTests(unittest.TestCase):
    def test_match_scores_higher_than_no_match(self) -> None:
        ev = Evidence(url="http://x", title="Python 3.13 release notes",
                      snippet="stable version released")
        hit = lexical_relevance("Python 最新稳定版", ev)
        miss = lexical_relevance("xyzzy foobar quux", ev)
        self.assertGreater(hit, miss)

    def test_no_query_terms_returns_zero(self) -> None:
        ev = Evidence(url="http://x", title="t", snippet="s")
        self.assertEqual(lexical_relevance("！！！", ev), 0.0)

    def test_bounded_zero_to_one(self) -> None:
        ev = Evidence(url="http://x", title="foo bar baz", snippet="")
        s = lexical_relevance("foo bar", ev)
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 1.0)


class ClassifyIntentTests(unittest.TestCase):
    def test_technical_before_experience(self) -> None:
        self.assertEqual(classify_intent("某GitHub项目活跃度"), "technical")

    def test_experience(self) -> None:
        self.assertEqual(classify_intent("这个库稳定性怎么样"), "experience")

    def test_official(self) -> None:
        self.assertEqual(classify_intent("OpenAI API 支持什么参数"), "official")

    def test_social(self) -> None:
        self.assertEqual(classify_intent("这个产品的舆情如何"), "social")


if __name__ == "__main__":
    unittest.main()

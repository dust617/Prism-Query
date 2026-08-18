"""Trigger 与 Depth/Budget 单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from searchbrain.depth import Budget, decide_level, compute_depth_score
from searchbrain.models import SearchLevel, SearchMode
from searchbrain.trigger import compute_need_score, is_time_sensitive


class TriggerTests(unittest.TestCase):
    def test_stable_knowledge_scores_low(self) -> None:
        need, _, _ = compute_need_score("解释什么是TCP")
        self.assertLess(need, 0.35)

    def test_fresh_price_scores_high(self) -> None:
        need, _, _ = compute_need_score("OpenAI 最新模型价格")
        self.assertGreaterEqual(need, 0.5)

    def test_time_sensitive_detection(self) -> None:
        self.assertTrue(is_time_sensitive("现在价格多少"))
        self.assertTrue(is_time_sensitive("2026年最新版本"))
        self.assertFalse(is_time_sensitive("解释什么是TCP"))
        self.assertFalse(is_time_sensitive("证明勾股定理"))


class DepthTests(unittest.TestCase):
    def test_mode_maps_to_fixed_levels(self) -> None:
        self.assertEqual(decide_level(1.0, 1.0, SearchMode.ECONOMY), SearchLevel.S1)
        self.assertEqual(decide_level(1.0, 1.0, SearchMode.BALANCED), SearchLevel.S2)
        self.assertEqual(decide_level(1.0, 1.0, SearchMode.QUALITY), SearchLevel.S3)
        self.assertEqual(decide_level(1.0, 1.0, SearchMode.DEEP), SearchLevel.S4)

    def test_depth_score_increases_for_research_terms(self) -> None:
        self.assertGreater(compute_depth_score("分析行业竞争格局"), 0.0)
        self.assertEqual(compute_depth_score("解释TCP"), 0.0)


class BudgetTests(unittest.TestCase):
    def test_initial_budget_then_escalate(self) -> None:
        b = Budget(SearchLevel.S1)
        self.assertTrue(b.can_continue)
        b.consume(1)
        self.assertFalse(b.can_continue)
        self.assertTrue(b.can_escalate())
        b.escalate()
        self.assertTrue(b.can_continue)
        self.assertTrue(b.escalated)

    def test_max_queries_caps_escalation(self) -> None:
        b = Budget(SearchLevel.S1, max_queries=2)
        b.consume(1)
        b.escalate()
        b.consume(1)
        self.assertFalse(b.can_escalate())

    def test_cost_limit_stops_continue(self) -> None:
        b = Budget(SearchLevel.S4, max_cost=0.01)
        b.consume(1, cost=0.02)
        self.assertFalse(b.can_continue)


if __name__ == "__main__":
    unittest.main()

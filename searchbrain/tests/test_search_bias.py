from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from searchbrain.config import normalize_search_bias
from searchbrain.models import SearchLevel, SearchRequest, SearchResponse, SearchTrace
from searchbrain import router


class SearchBiasTests(unittest.TestCase):
    def test_default_bias_flips_current_point_three_boundary(self) -> None:
        bias = normalize_search_bias(None, 1.20)
        self.assertEqual(bias, 1.20)
        self.assertGreaterEqual(0.30 * bias, 0.35)

    def test_bias_is_finite_and_bounded(self) -> None:
        self.assertEqual(normalize_search_bias(float("nan"), 1.2), 1.2)
        self.assertEqual(normalize_search_bias(float("inf"), 1.2), 1.2)
        self.assertEqual(normalize_search_bias(-2.0, 1.2), 0.5)
        self.assertEqual(normalize_search_bias(99.0, 1.2), 3.0)
        self.assertTrue(math.isfinite(normalize_search_bias(None, 1.2)))

    def test_trace_serializes_effective_bias_and_scores(self) -> None:
        response = SearchResponse(
            query="fixture",
            trace=SearchTrace(
                searched=False,
                level=SearchLevel.S0.value,
                need_score=0.36,
                search_bias=1.2,
                depth_score=0.25,
            ),
        )
        trace = response.to_dict()["trace"]
        self.assertEqual(trace["need_score"], 0.36)
        self.assertEqual(trace["search_bias"], 1.2)
        self.assertEqual(trace["depth_score"], 0.25)
        self.assertEqual(response.compact_dict()["trace"]["search_bias"], 1.2)

    def test_free_provider_bonus_breaks_an_equal_fit_tie(self) -> None:
        original = router.available
        paid = SimpleNamespace(
            name="paid", capabilities={"search_web", "global"},
            cost_level="medium",
        )
        free = SimpleNamespace(
            name="free", capabilities={"search_web", "global", "free"},
            cost_level="medium",
        )
        router.available = lambda: [paid, free]
        try:
            selected = router.choose(
                "latest protocol update", set(), SearchLevel.S1,
                SearchRequest(query="latest protocol update"),
            )
        finally:
            router.available = original
        self.assertEqual(selected, "free")


if __name__ == "__main__":
    unittest.main()

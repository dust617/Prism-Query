"""Evals runner：用测试集统计 SearchBrain 决策层准确率与成本。

用法：
    python evals/run_evals.py            # 决策层（Trigger/Depth/Router，不触发网络）
    python evals/run_evals.py --live     # 额外跑真实搜索（需 key，计费）

统计指标：
    Trigger: Precision / Recall / 漏搜率 / 过度搜索率
    Depth:   档位命中率
    Router:  能力选择命中率
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from searchbrain.depth import decide_level, compute_depth_score
from searchbrain.models import SearchMode, SearchLevel
from searchbrain.router import choose_capability
from searchbrain.trigger import compute_need_score

EVALS = Path(__file__).resolve().parent
NEED_THRESHOLD = 0.35


def load_cases(name: str) -> list[dict]:
    path = EVALS / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def run_trigger() -> dict:
    cases = load_cases("trigger_cases.jsonl")
    tp = fp = tn = fn = 0
    for c in cases:
        need, _, _ = compute_need_score(c["query"])
        pred = need >= NEED_THRESHOLD
        exp = c["expected_search"]
        tp += pred and exp
        fp += pred and not exp
        tn += not pred and not exp
        fn += not pred and exp
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    return {
        "cases": len(cases), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(prec, 2), "recall": round(rec, 2),
        "漏搜率": round(fn / (tp + fn) if tp + fn else 0, 2),
        "过度搜索率": round(fp / (tn + fp) if tn + fp else 0, 2),
    }


def run_depth() -> dict:
    cases = load_cases("depth_cases.jsonl")
    hit = 0
    detail = []
    for c in cases:
        need, _, _ = compute_need_score(c["query"])
        depth = compute_depth_score(c["query"])
        lvl = decide_level(need, depth, SearchMode.AUTO)
        ok = lvl.value == c["expected_level"]
        hit += ok
        detail.append((c["query"][:24], c["expected_level"], lvl.value, "✓" if ok else "✗"))
    return {"cases": len(cases), "命中": hit, "命中率": round(hit / len(cases), 2),
            "detail": detail}


def run_router() -> dict:
    cases = load_cases("router_cases.jsonl")
    hit = 0
    detail = []
    for c in cases:
        cap = choose_capability(c["query"])
        ok = cap == c["expected_cap"]
        hit += ok
        detail.append((c["query"][:26], c["expected_cap"], cap, "✓" if ok else "✗"))
    return {"cases": len(cases), "命中": hit, "命中率": round(hit / len(cases), 2),
            "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="额外跑真实搜索")
    args = ap.parse_args()

    print("=" * 50)
    print("SearchBrain Evals（决策层，不触发网络）")
    print("=" * 50)

    t = run_trigger()
    print(f"\n[Trigger] {t['cases']} 条 | Precision={t['precision']} "
          f"Recall={t['recall']} | 漏搜率={t['漏搜率']} 过度搜索率={t['过度搜索率']}")

    d = run_depth()
    print(f"\n[Depth] {d['cases']} 条 | 命中率={d['命中率']} ({d['命中']}/{d['cases']})")
    for q, exp, got, mark in d["detail"]:
        print(f"    {q:<26} 期望={exp} 实际={got} {mark}")

    r = run_router()
    print(f"\n[Router] {r['cases']} 条 | 能力命中率={r['命中率']} ({r['命中']}/{r['cases']})")
    for q, exp, got, mark in r["detail"]:
        print(f"    {q:<28} 期望={exp} 实际={got} {mark}")

    if args.live:
        print("\n" + "=" * 50)
        print("真实搜索抽样（计费，需 key）")
        print("=" * 50)
        from searchbrain import search
        for q in ["Python 最新稳定版", "某API现在支持MCP吗"]:
            resp = search(q)
            print(f"\n  Q: {q}")
            print(f"     depth={resp.trace.level} searched={resp.trace.searched} "
                  f"conf={resp.confidence} cost=${resp.trace.estimated_cost:.5f} "
                  f"stop={resp.trace.stop_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
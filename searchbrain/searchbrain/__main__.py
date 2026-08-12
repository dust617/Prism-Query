"""SearchBrain 命令行入口。

用法：
    python -m searchbrain "你的问题"
    python -m searchbrain "你的问题" --mode quality
"""
from __future__ import annotations

import argparse
import json
import sys

from .models import SearchMode
from .orchestrator import search


def main() -> int:
    parser = argparse.ArgumentParser(description="SearchBrain 智能搜索")
    parser.add_argument("query", help="要搜索的问题")
    parser.add_argument("--mode", default="auto",
                        choices=[m.value for m in SearchMode])
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    resp = search(args.query, mode=SearchMode(args.mode))

    if args.json:
        print(json.dumps({
            "query": resp.query,
            "answer": resp.answer,
            "results": [{"title": i.title, "url": i.url,
                         "snippet": i.snippet[:120], "provider": i.provider,
                         "source_type": i.source_type}
                        for i in resp.results],
            "trace": {
                "level": resp.trace.level,
                "need_score": round(resp.trace.need_score, 2),
                "providers": resp.trace.providers_used,
                "capabilities": resp.trace.capabilities_used,
                "queries": resp.trace.queries,
                "cost": round(resp.trace.estimated_cost, 5),
                "stop": resp.trace.stop_reason,
            },
        }, ensure_ascii=False, indent=2), file=sys.stdout)
        return 0

    print(f"查询: {resp.query}")
    print(f"深度: {resp.trace.level} | "
          f"需搜分: {resp.trace.need_score:.2f} | "
          f"Provider: {','.join(resp.trace.providers_used) or '-'} | "
          f"能力: {','.join(resp.trace.capabilities_used) or '-'} | "
          f"查询数: {resp.trace.queries} | "
          f"成本: ${resp.trace.estimated_cost:.5f} | "
          f"停止: {resp.trace.stop_reason}")
    if resp.answer:
        print(f"\n[答案] {resp.answer[:400]}")
    print(f"\n结果 {len(resp.results)} 条:")
    for it in resp.results:
        print(f"  · [{it.provider}/{it.source_type}] {it.title[:46]}")
        print(f"      {it.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
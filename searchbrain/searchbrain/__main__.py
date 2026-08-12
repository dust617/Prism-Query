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
        print(json.dumps(resp.to_dict(), ensure_ascii=False, indent=2),
              file=sys.stdout)
        return 0

    print(f"查询: {resp.query}")
    print(f"深度: {resp.trace.level} | 需搜分: {resp.trace.need_score:.2f} | "
          f"搜索: {'是' if resp.trace.searched else '否'} | "
          f"置信: {resp.confidence:.2f} | "
          f"Provider: {','.join(resp.trace.providers_used) or '-'} | "
          f"查询: {resp.trace.queries} | 成本: ${resp.trace.estimated_cost:.5f} | "
          f"停止: {resp.trace.stop_reason}")
    if resp.answer:
        print(f"\n[答案] {resp.answer[:400]}")
    print(f"\n结果 {len(resp.results)} 条 (置信 {resp.confidence}):")
    for it in resp.results:
        print(f"  · [{it.provider}/{it.source_type}] {it.title[:46]}")
        print(f"      {it.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
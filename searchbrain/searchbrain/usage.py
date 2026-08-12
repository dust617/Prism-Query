"""用量记录：每次搜索的 token/成本日志（本地 jsonl，本机私有）。

记录内容（不含任何凭据/敏感数据）：
    时间、query（截断）、深度档、各 Provider、查询次数、
    估算成本、耗时、各 Provider token 消耗（如有）
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from .models import SearchResponse

# 日志目录：~/.searchbrain/（用户目录，不在任何仓库内）
_LOG_DIR = Path(os.environ.get("SEARCHBRAIN_LOG_DIR",
                               str(Path.home() / ".searchbrain")))
_LOG_FILE = _LOG_DIR / "usage.log"


def record(resp: SearchResponse,
           tokens_by_provider: dict | None = None) -> None:
    """把一次搜索写入用量日志（追加 jsonl 行）。

    tokens_by_provider: {provider: token数}，由 orchestrator 从
    ProviderResult.raw_metadata 汇总传入（SearchResponse 已归一化，不含此信息）。
    """
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        tokens = tokens_by_provider or {}
        entry = {
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
            "query": resp.query[:80],
            "level": resp.trace.level,
            "providers": resp.trace.providers_used,
            "queries": resp.trace.queries,
            "cost": round(resp.trace.estimated_cost, 6),
            "latency_ms": resp.trace.latency_ms,
            "stop": resp.trace.stop_reason,
            "cross_validated": resp.cross_validated,
            "tokens": tokens,
        }
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 用量记录失败不影响主流程


def summary(last_n: int = 30) -> dict:
    """最近 n 次搜索的汇总（成本/次数/Provider 分布）。"""
    if not _LOG_FILE.exists():
        return {"entries": 0, "cost_total": 0.0, "queries_total": 0}
    rows = []
    for line in _LOG_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    rows = rows[-last_n:]
    prov_dist = {}
    tokens = {}
    for r in rows:
        for p in r.get("providers", []):
            prov_dist[p] = prov_dist.get(p, 0) + 1
        for k, v in (r.get("tokens") or {}).items():
            tokens[k] = tokens.get(k, 0) + v
    return {
        "entries": len(rows),
        "cost_total": round(sum(r.get("cost", 0) for r in rows), 6),
        "queries_total": sum(r.get("queries", 0) for r in rows),
        "provider_dist": prov_dist,
        "tokens": tokens,
        "log_file": str(_LOG_FILE),
    }

def main() -> int:
    """CLI：python -m searchbrain.usage [--today] 查看用量报告。"""
    import argparse
    ap = argparse.ArgumentParser(description="SearchBrain 用量统计")
    ap.add_argument("--today", action="store_true", help="只看今天")
    ap.add_argument("-n", type=int, default=30, help="最近 N 次（默认30）")
    args = ap.parse_args()

    if not _LOG_FILE.exists():
        print("暂无用量记录（日志文件:", _LOG_FILE, ")")
        return 0
    rows = []
    for line in _LOG_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if args.today:
        today = _dt.date.today().isoformat()
        rows = [r for r in rows if r.get("ts", "").startswith(today)]
    rows = rows[-args.n:]

    cost = sum(r.get("cost", 0) for r in rows)
    queries = sum(r.get("queries", 0) for r in rows)
    prov_dist = {}
    tokens = {}
    cv = 0
    for r in rows:
        for p_ in r.get("providers", []):
            prov_dist[p_] = prov_dist.get(p_, 0) + 1
        for k, v in (r.get("tokens") or {}).items():
            tokens[k] = tokens.get(k, 0) + v
        if r.get("cross_validated"):
            cv += 1

    print(f"SearchBrain 用量统计（最近 {len(rows)} 次"
          + ("，今天" if args.today else "") + "）")
    print(f"  总成本: ${cost:.5f} | 总查询: {queries} 次 | 交叉验证率: "
          f"{cv}/{len(rows)}")
    print("  Provider 分配:")
    for k, v in sorted(prov_dist.items(), key=lambda x: -x[1]):
        print(f"    {k:<14} {v} 次")
    if tokens:
        print("  Token 消耗:")
        for k, v in tokens.items():
            print(f"    {k:<14} {v}")
    print(f"  日志: {_LOG_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

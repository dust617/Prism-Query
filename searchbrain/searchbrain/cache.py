"""搜索缓存：同一 query+provider 的短期结果复用（本机私有，默认 10 分钟）。

为什么需要：
    - 相同/相近问题短时间内重复搜索（Agent 重试、多轮交互）会重复花钱；
    - 缓存命中直接返回上次结果，省 token、省耗时。

安全边界：
    - 只缓存"非时效"问题。时效/价格/舆情类（见 trigger.is_time_sensitive）
      结果会随时间变化，一律不缓存（既不读也不写）。
    - TTL 默认 600s，环境变量 SEARCHBRAIN_CACHE_TTL 可调（秒）。
    - 环境变量 SEARCHBRAIN_DISABLE_CACHE=1 可整体关闭。
    - 缓存目录默认 ~/.searchbrain/cache（可用 SEARCHBRAIN_CACHE_DIR 覆盖），
      不入仓库，内容为 ProviderResult 的 JSON 序列化（无凭据）。

命中后 estimated_cost 归零、tokens 剔除，避免用量日志重复计费。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .models import ProviderResult, SearchItem
from .trigger import is_time_sensitive

_DEFAULT_DIR = str(Path.home() / ".searchbrain" / "cache")


def _dir() -> Path:
    return Path(os.environ.get("SEARCHBRAIN_CACHE_DIR", _DEFAULT_DIR))


def _ttl() -> float:
    return float(os.environ.get("SEARCHBRAIN_CACHE_TTL", "600") or "600")


def disabled() -> bool:
    return bool(os.environ.get("SEARCHBRAIN_DISABLE_CACHE"))


def _key(provider: str, query: str, mode: str, max_results: int) -> str:
    raw = f"{provider}|{query.strip().lower()}|{mode}|{max_results}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _path(key: str) -> Path:
    return _dir() / f"{key}.json"


def _to_dict(result: ProviderResult) -> dict:
    return {
        "provider": result.provider,
        "query": result.query,
        "items": [{"title": it.title, "url": it.url, "snippet": it.snippet,
                   "source": it.source, "published_at": it.published_at,
                   "score": it.score} for it in result.items],
        "answer": result.answer,
        "latency_ms": result.latency_ms,
        "estimated_cost": result.estimated_cost,
        "raw_metadata": result.raw_metadata,
    }


def _from_dict(d: dict) -> ProviderResult:
    return ProviderResult(
        provider=d.get("provider", ""),
        query=d.get("query", ""),
        items=[SearchItem(**it) for it in d.get("items", [])],
        answer=d.get("answer"),
        latency_ms=d.get("latency_ms", 0),
        estimated_cost=d.get("estimated_cost", 0.0),
        raw_metadata=d.get("raw_metadata", {}),
    )


def get(provider: str, query: str, mode: str,
        max_results: int) -> ProviderResult | None:
    """命中则返回 ProviderResult，否则 None。时效问题与关闭状态一律不读。"""
    if disabled() or is_time_sensitive(query):
        return None
    p = _path(_key(provider, query, mode, max_results))
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        try:
            p.unlink(missing_ok=True)  # 损坏文件视为失效，清理
        except OSError:
            pass
        return None
    if time.time() - float(data.get("ts", 0)) > float(data.get("ttl", _ttl())):
        return None
    result = _from_dict(data.get("result", {}))
    # 命中：本次没有新花费/新耗时，避免用量日志与 trace 重复统计
    result.estimated_cost = 0.0
    result.latency_ms = 0
    meta = dict(result.raw_metadata)
    meta["cached"] = True
    meta.pop("tokens", None)
    result.raw_metadata = meta
    return result


def put(provider: str, query: str, mode: str, max_results: int,
        result: ProviderResult) -> None:
    """写入缓存。时效问题 / 关闭状态 / 空结果不写。"""
    if disabled() or is_time_sensitive(query):
        return
    if not result.items and not result.answer:
        return
    try:
        _dir().mkdir(parents=True, exist_ok=True)
        payload = {"ts": time.time(), "ttl": _ttl(),
                   "result": _to_dict(result)}
        _path(_key(provider, query, mode, max_results)).write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8")
    except (OSError, TypeError, ValueError):
        pass  # 缓存失败不影响主流程


def clear() -> int:
    """清空缓存目录，返回删除的文件数。"""
    n = 0
    d = _dir()
    if d.exists():
        for p in d.glob("*.json"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n


def stats() -> dict:
    """缓存概览：条目数、总大小、目录位置。"""
    d = _dir()
    if not d.exists():
        return {"entries": 0, "bytes": 0, "dir": str(d),
                "ttl": _ttl(), "disabled": disabled()}
    files = list(d.glob("*.json"))
    return {
        "entries": len(files),
        "bytes": sum(p.stat().st_size for p in files),
        "dir": str(d),
        "ttl": _ttl(),
        "disabled": disabled(),
    }

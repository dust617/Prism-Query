"""配置与凭据加载。

凭据从环境变量或本机 .env 文件读取（不写入源码）。
"""
from __future__ import annotations

import math
import os
from pathlib import Path

# 向上查找 .searchbrain-credentials.env（可能在包目录或项目根）
_CRED_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent,  # 项目根
    Path(__file__).resolve().parent.parent,        # packages 目录
]
CRED_FILE = None
for _d in _CRED_CANDIDATES:
    _p = _d / ".searchbrain-credentials.env"
    if _p.exists():
        CRED_FILE = _p
        break
CRED_FILE = CRED_FILE or (Path(os.environ.get(
    "SEARCHBRAIN_CRED_FILE",
    Path(__file__).resolve().parent.parent.parent / ".searchbrain-credentials.env",
)))


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析：KEY=VALUE。已存在的环境变量不覆盖。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_auth_json() -> None:
    """兼容 ~/.pi/agent/auth.json 里的 key（zhipu/deepseek/百炼）。"""
    auth = Path.home() / ".pi" / "agent" / "auth.json"
    if not auth.exists():
        return
    try:
        import json
        data = json.loads(auth.read_text(encoding="utf-8"))
    except Exception:
        return
    mapping = {"zhipu": "ZHIPU_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
    for key_in_json, env_name in mapping.items():
        entry = data.get(key_in_json, {})
        val = entry.get("key") if isinstance(entry, dict) else entry
        if isinstance(val, str) and val and env_name not in os.environ:
            os.environ[env_name] = val


_load_dotenv(CRED_FILE)
_load_auth_json()


def get_key(name: str) -> str | None:
    """读取一个凭据，未配置返回 None。"""
    return os.environ.get(name) or None


def resolve_openai_auth() -> tuple[str, str] | None:
    """解析 OpenAI 搜索凭据，返回 (secret, kind)。kind ∈ {"codex", "key"}。

    优先级：
      1. OPENAI_CODEX_TOKEN 环境变量（已登录的 OpenAI 会话凭据）
      2. 本机 Pi/Codex 已保存的会话登录态
      3. OPENAI_API_KEY（真 API Key，走官方/网关 Responses）

    绝不在日志或返回值中泄露 secret；调用方负责脱敏。
    """
    import json as _json
    from pathlib import Path as _Path

    env_codex = os.environ.get("OPENAI_CODEX_TOKEN") or None
    if env_codex:
        return env_codex, "codex"
    # 本机已有登录会话：Pi 与 Codex 两处都可能是"长期都有"的订阅授权
    candidates = []
    auth_pi = _Path.home() / ".pi" / "agent" / "auth.json"
    if auth_pi.exists():
        try:
            d = _json.loads(auth_pi.read_text(encoding="utf-8"))
            v = (d.get("openai-codex") or {}).get("access")
            if isinstance(v, str) and v:
                candidates.append((v, "codex"))
        except Exception:
            pass
    auth_codex = _Path.home() / ".codex" / "auth.json"
    if auth_codex.exists():
        try:
            d = _json.loads(auth_codex.read_text(encoding="utf-8"))
            v = (d.get("tokens") or {}).get("access_token")
            if isinstance(v, str) and v:
                candidates.append((v, "codex"))
        except Exception:
            pass
    if candidates:
        return candidates[0]
    env_key = os.environ.get("OPENAI_API_KEY") or None
    if env_key:
        return env_key, "key"
    return None


def _env_float(name: str, default: float, minimum: float,
               maximum: float) -> float:
    """读取有界有限 float；非法、NaN/Inf 或越界都回退默认值。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value) or not minimum <= value <= maximum:
        return default
    return value


def normalize_search_bias(value: float | None, default: float = 1.2) -> float:
    """返回真正参与计算的搜索倾向系数（0.5–3.0，非法则回退）。"""
    candidate = default if value is None else value
    try:
        normalized = float(candidate)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(normalized):
        return default
    return min(3.0, max(0.5, normalized))


# 常用阈值（可按需调整；两个都可以用环境变量覆盖）
class Defaults:
    # Search Trigger：超过阈值才搜索（SEARCHBRAIN_NEED_THRESHOLD 可覆盖）。
    NEED_THRESHOLD = _env_float("SEARCHBRAIN_NEED_THRESHOLD", 0.35, 0.0, 1.0)
    # 搜索倾向系数：1.0 = 原样；默认 1.20 会把当前离散评分中的
    # 0.30 临界题提升到 0.36，越过 0.35 阈值，但不提高初始搜索深度。
    # 环境变量 SEARCHBRAIN_SEARCH_BIAS 可覆盖，安全范围 0.5–3.0。
    SEARCH_BIAS = _env_float("SEARCHBRAIN_SEARCH_BIAS", 1.20, 0.5, 3.0)
    # 单次搜索成本上限（美元），超过则强制停止
    MAX_COST = 0.20
    MAX_QUERIES = 12
    MAX_ROUNDS = 4
    # InfoGap 模型化：S3/S4 档位、规则无缺口时，用小模型补判一次
    GAP_MODEL_ENABLED = True
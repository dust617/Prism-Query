"""配置与凭据加载。

凭据从环境变量或本机 .env 文件读取（不写入源码）。
"""
from __future__ import annotations

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


# 常用阈值（可按需调整）
class Defaults:
    # Search Trigger：超过阈值才搜索
    NEED_THRESHOLD = 0.35
    # 单次搜索成本上限（美元），超过则强制停止
    MAX_COST = 0.20
    MAX_QUERIES = 12
    MAX_ROUNDS = 4
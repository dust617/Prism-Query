"""InfoGap 模型化：用小模型分析已有证据，输出结构化"还缺什么"。

为什么需要：
    规则版 gap（evidence.py）只能发现"数量不足/来源单一"这类机械缺口；
    模型版能发现"缺少官方价格""缺少一手资料"这类语义缺口。

设计（用户文档）：
    不要让模型直接问"信息够了吗"（容易变成"再搜搜更好"），
    而是让它输出结构化 missing_information，由系统判断值不值得补。

只在 S3/S4 档位且预算允许时调用（S1/S2 简单问题不值得花模型调用）。
调用失败/超时/解析失败时静默回退到 None（规则版兜底），不中断主流程。
"""
from __future__ import annotations

import json
import re
import urllib.request

from .config import get_key
from .models import Evidence, InfoGap, ProviderResult

_URL = "https://api.deepseek.com/chat/completions"

_SYSTEM = (
    "你是搜索任务的信息缺口分析器。你的任务：判断已有搜索结果对回答用户问题"
    "是否足够；如果不够，指出还缺什么、有多重要、最好用什么类型的来源补、"
    "建议什么补搜关键词。只输出 JSON，不要输出任何其他文字。"
)

_SCHEMA_EXAMPLE = (
    '{"sufficient": true/false, "missing_information": ['
    '{"gap": "缺少什么信息", "importance": 0.0到1.0, '
    '"preferred_source_type": "official/community/social/news/technical/web", '
    '"suggested_query": "补搜关键词", "expected_value": 0.0到1.0}]}'
)


def _build_prompt(query: str, evidences: list[Evidence],
                  has_answer: bool) -> str:
    lines = []
    for e in evidences[:8]:
        lines.append(f"- [{e.source_type}|{e.provider}] {e.title}"
                     f"{': ' + e.snippet[:80] if e.snippet else ''}")
    body = "\n".join(lines) or "(无证据)"
    return (
        f"用户问题: {query}\n\n"
        f"已有证据:\n{body}\n\n"
        f"是否有直接答案: {has_answer}\n\n"
        f"请输出 JSON（字段说明）:\n{_SCHEMA_EXAMPLE}\n"
        f"要求: 只列出真正重要、值得继续花钱搜索的缺口；"
        f"如果 sufficient=true，missing_information 为空数组。"
    )


def _call_model(prompt: str, key: str) -> str | None:
    body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 600,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        _URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


def _parse_gaps(text: str) -> list[dict]:
    """从模型输出提取 JSON（容忍被代码块包裹或前后有杂字）。"""
    if not text:
        return []
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    if data.get("sufficient"):
        return []
    return data.get("missing_information", []) or []


def detect_gap_with_model(query: str, evidences: list[Evidence],
                          results: list[ProviderResult]) -> InfoGap | None:
    """调用小模型检测信息缺口。失败/无缺口返回 None。"""
    key = get_key("DEEPSEEK_API_KEY")
    if not key or not evidences:
        return None
    has_answer = any(r.answer for r in results)
    prompt = _build_prompt(query, evidences, has_answer)
    text = _call_model(prompt, key)
    if not text:
        return None
    gaps = _parse_gaps(text)
    if not gaps:
        return None
    # 取 importance 最高且预期价值 > 成本的缺口
    gaps.sort(key=lambda g: g.get("importance", 0), reverse=True)
    top = gaps[0]
    imp = float(top.get("importance", 0))
    if imp < 0.6:  # 重要度太低不值得补
        return None
    return InfoGap(
        description=str(top.get("gap", ""))[:200],
        importance=imp,
        preferred_source_type=str(top.get("preferred_source_type", "web")),
        suggested_query=str(top.get("suggested_query", "")),
        expected_value=float(top.get("expected_value", 0.5)),
    )
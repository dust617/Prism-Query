"""Provider 统一注册：有 key 的注册收费源；免 key 源（Exa MCP/DDG）始终注册；OpenAI 凭据可解析才注册。"""
from __future__ import annotations

from ..config import get_key, resolve_openai_auth
from .base import register
from .glm import GLMProvider
from .exa import ExaProvider
from .perplexity import PerplexityProvider
from .firecrawl import FirecrawlProvider
from .deepseek import DeepSeekProvider
from .tavily import TavilyProvider
from .anysearch import AnySearchProvider
from .doubao import VolcProvider
from .ddg import DuckDuckGoProvider
from .openai import OpenAIProvider


def load_providers() -> None:
    """按可用 key / 可解析凭据注册 Provider。重复调用安全（覆盖同 name）。"""
    if get_key("ZHIPU_API_KEY"):
        register(GLMProvider())
    # Exa：有 key 走官方 API，无 key 零配置走托管 MCP（始终可用）
    register(ExaProvider())
    if get_key("OPENROUTER_API_KEY"):
        register(PerplexityProvider())
    if get_key("FIRECRAWL_API_KEY"):
        register(FirecrawlProvider())
    if get_key("DEEPSEEK_API_KEY"):
        register(DeepSeekProvider())
    if get_key("TAVILY_API_KEY"):
        register(TavilyProvider())
    if get_key("ANYSEARCH_API_KEY"):
        register(AnySearchProvider())
    if get_key("ARK_API_KEY"):
        # 豆包（Doubao-Seed-2.1-pro，每日免费 token 或按量）
        register(VolcProvider(
            name="doubao", model_env="DOUBAO_MODEL",
            capabilities={"search_web", "research", "answer_with_citations",
                          "zh", "global"}, cost_level="medium"))
        # DeepSeek-V4-Flash（方舟托管，同样支持联网，每日免费 token）
        if get_key("DEEPSEEK_VOLC_MODEL"):
            register(VolcProvider(
                name="deepseek_volc", model_env="DEEPSEEK_VOLC_MODEL",
                capabilities={"search_web", "research", "answer_with_citations",
                              "zh", "global", "cheap", "free"}, cost_level="low"))
    # DuckDuckGo：keyless 免费英文兜底（始终可用）
    register(DuckDuckGoProvider())
    # OpenAI：本机已登录 OpenAI 会话或 API Key，可解析才注册
    if resolve_openai_auth():
        register(OpenAIProvider())
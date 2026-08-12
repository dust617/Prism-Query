"""Provider 统一注册：只注册已配置 key 的 Provider。"""
from __future__ import annotations

from ..config import get_key
from .base import register
from .glm import GLMProvider
from .exa import ExaProvider
from .perplexity import PerplexityProvider
from .firecrawl import FirecrawlProvider
from .deepseek import DeepSeekProvider
from .tavily import TavilyProvider
from .anysearch import AnySearchProvider


def load_providers() -> None:
    """按可用 key 注册 Provider。重复调用安全（覆盖同 name）。"""
    if get_key("ZHIPU_API_KEY"):
        register(GLMProvider())
    if get_key("EXA_API_KEY"):
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
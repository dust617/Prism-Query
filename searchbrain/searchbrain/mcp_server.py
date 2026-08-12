"""最薄 MCP wrapper：只向 Agent 暴露一个 search(query, mode="auto")。

用法：
    python -m searchbrain.mcp_server          # stdio 传输，供 MCP 客户端连接

在支持 MCP 的 CLI（Claude Code / Codex / OpenCode / GPT CLI 等）配置为
本地 stdio server：命令 `python -m searchbrain.mcp_server`。
"""
from __future__ import annotations

from fastmcp import FastMCP

from . import search as sb_search
from .models import SearchMode

mcp = FastMCP("SearchBrain")


@mcp.tool()
def search(query: str, mode: str = "auto") -> dict:
    """智能搜索。

    根据问题自动判断是否需要联网、搜多深、用哪个搜索源，返回统一结果
    （answer / evidence / sources / confidence / trace）。

    Args:
        query: 要搜索的问题。
        mode: auto（自动判断）| economy（最省）| balanced | quality（多源）| deep。
    """
    mode_enum = SearchMode(mode) if mode in SearchMode._value2member_map_ \
        else SearchMode.AUTO
    return sb_search(query, mode=mode_enum).to_dict()


if __name__ == "__main__":
    mcp.run()
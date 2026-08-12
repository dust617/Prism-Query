"""MCP stdio 集成测试：连接 searchbrain.mcp_server 子进程，列出并调用 search 工具。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp import ClientSession

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # searchbrain/
PY = sys.executable


async def main():
    params = StdioServerParameters(
        command=PY,
        args=["-m", "searchbrain.mcp_server"],
        cwd=BASE,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("MCP 已注册工具:", [t.name for t in tools.tools])

            # 调用1：S0 不搜
            res = await session.call_tool(
                "search", {"query": "解释什么是TCP"})
            txt = res.content[0].text if res.content else str(res)
            print("\n[调用] search('解释什么是TCP')")
            print("  结果 trace.searched =", "searched" in txt and "'searched': False" in txt or _snippet(txt, "depth"))

            # 调用2：真实搜索
            res = await session.call_tool(
                "search", {"query": "Python 最新稳定版本", "mode": "auto"})
            txt = res.content[0].text if res.content else str(res)
            print("\n[调用] search('Python 最新稳定版本', mode=auto)")
            import json
            try:
                data = json.loads(txt)
                print("  depth:", data["trace"]["depth"],
                      "| searched:", data["trace"]["searched"],
                      "| providers:", data["trace"]["providers"],
                      "| cost:", data["trace"]["cost"],
                      "| confidence:", data["confidence"],
                      "| evidence数:", len(data["evidence"]))
            except Exception as e:
                print("  原始:", txt[:200], "| err", e)


def _snippet(txt, key):
    import re
    m = re.search(r'"' + key + r'"\s*:\s*"[^"]*"', txt)
    return m.group(0) if m else "?"


if __name__ == "__main__":
    asyncio.run(main())
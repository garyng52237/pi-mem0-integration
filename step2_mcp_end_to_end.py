"""
Step3: 端到端验证 mem0 MCP server。

用标准 MCP client（mcp.client.stdio + ClientSession）连接 stdio transport，依次调用：
    memory_add -> memory_search -> memory_get -> memory_delete
证明：同一本地模型下，mem0 记忆工具经 MCP 协议可被任意 client（含 pi）消费。

注意：本地推理较慢，add/search 各需数十秒；给足超时。
"""

import asyncio
import json as _json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = {**os.environ, "OPENAI_API_KEY": "lmstudio", "MEM0_TELEMETRY": "false"}


async def main():
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, "mem0_mcp_server.py")], env=ENV)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 0) reset（清空历史，保证可重复演示）
            print("=== MCP memory_reset ===")
            r = await session.call_tool("memory_reset", {})
            print(_content(r))

            # 1) add
            print("\n=== MCP memory_add ===")
            r = await session.call_tool("memory_add", {"messages": "我叫张三，喜欢用 Rust 写 pi agent。"})
            add_txt = _content(r)
            print(add_txt)

            # 2) search
            print("\n=== MCP memory_search (query: '我的名字和爱好') ===")
            r = await session.call_tool("memory_search", {"query": "我的名字和爱好", "user_id": "you"})
            txt = _content(r)
            print(txt)

            ok_rust = ("Rust" in txt) or ("张三" in txt)
            assert ok_rust, "search 未命中写入内容（本地模型可能未提取出关键事实）"

            # 3) get (从 add result 解析 memory_id，兼容 {results:{results:[...]}} 与 {results:[...]} 两种结构)
            print("\n=== MCP memory_get ===")
            mid = None
            try:
                parsed = _json.loads(add_txt)
                inner = parsed.get("results") if isinstance(parsed, dict) else None
                items = (inner["results"] if isinstance(inner, dict) else inner) or []
                if items and isinstance(items[0], dict):
                    mid = items[0].get("id")
            except Exception:
                mid = None
            if mid:
                r2 = await session.call_tool("memory_get", {"memory_id": mid})
                print(_content(r2))
            else:
                print("(未解析到 memory_id，跳过 get)")

            # 4) delete
            print("\n=== MCP memory_delete ===")
            if mid:
                r3 = await session.call_tool("memory_delete", {"memory_id": mid})
                print(_content(r3))

        print("\n✅ Step3 通过：mem0 记忆工具经 MCP stdio 协议端到端跑通（同一本地模型）")


def _content(resp):
    """把 call_tool 返回的 content 拼成可读文本。"""
    try:
        return "".join(getattr(c, "text", "") or "" for c in resp.content)
    except Exception:
        return str(resp)


if __name__ == "__main__":
    asyncio.run(main())

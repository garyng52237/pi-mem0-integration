"""
Step2: 把 mem0 封装成一个标准 MCP server，对外暴露记忆工具（add/search/update/delete/get）。

设计要点：
- LLM 与 embedding 共用同一个本地 LM Studio 模型（同一后端），满足"两者用同一个模型"。
- 纯 Python，与 pi（TypeScript）之间通过 MCP 协议解耦——任何 MCP client（包括 pi 的远端/工具层）都可消费。
- transport 默认 stdio（MCP 标准），也可 http；这里保留可配置。

用法：
    ./venv/bin/python mem0_mcp_server.py            # stdio（供 MCP client 连接）
    OPENAI_API_KEY=lmstudio ./venv/bin/python mem0_mcp_server.py --http-port 8123

环境变量：
    LM_URL          LM Studio base url（默认 http://localhost:1234/v1）
    LLM_MODEL       抽取记忆用的模型（默认 Meta-Llama-3.1-8B-Instruct-IQ0_K_S.gguf）
    EMBED_MODEL     embedding 模型（默认 text-embedding-nomic-embed-text-v1.5）
"""

import os
import sys
from typing import Optional

# fastmcp 需在导入 mem0 之前，避免其内部 openai client 被污染
from fastmcp import FastMCP

# 复用 step1 已验证的连接参数（同一本地模型 + nomic 768 维 + text response_format）。
# 可用环境变量覆盖；默认取 step1 实测可达的 URL/模型名。
LM_URL = os.environ.get("LM_URL", "http://localhost:1234/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "ornith-1.5-35b-a3b-apex-mtp-i-compact")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")


def _build_config():
    """构造与 step1 一致的 MemoryConfig（Memory(config=...) 形式，顶层 llm kwarg 不被接受）。"""
    from mem0.configs.base import MemoryConfig

    return MemoryConfig(
        llm={
            "provider": "lmstudio",
            "config": {
                "api_key": "lmstudio",  # 本地常可占位；若服务需 auth 填真实 token
                "lmstudio_base_url": LM_URL,
                "model": LLM_MODEL,
                "temperature": 0.2,
                # vLLM/LM Studio 不接受 mem0 默认的 {"type":"json_object"}（报 400）。
                # 设为 text，让模型返回纯文本 JSON；mem0 parser 自带 extract_json fallback。
                "lmstudio_response_format": {"type": "text"},
            },
        },
        embedder={
            "provider": "lmstudio",
            "config": {
                "api_key": "lmstudio",
                "lmstudio_base_url": LM_URL,
                "model": EMBED_MODEL,
                "embedding_dims": 768,
            },
        },
        vector_store={
            "provider": "qdrant",
            "config": {
                "collection_name": "pi_mem0",
                # nomic-embed-text-v1.5 实际输出 768 维（默认 1536 会导致维度不匹配报错）
                "embedding_model_dims": 768,
                "path": os.path.join(os.path.dirname(__file__), "data", "qdrant"),
            },
        },
    )


mcp = FastMCP("mem0-memory")


def _get_memory() -> Optional[object]:
    try:
        from mem0 import Memory

        return Memory(config=_build_config())
    except Exception as e:  # pragma: no cover
        return {"__error__": str(e)}


@mcp.tool()
def memory_add(messages, user_id="you", metadata=None, agent_id=None):
    """向记忆库写入/提取新记忆。messages 为对话文本或消息列表；返回被提取并存储的记忆条目。"""
    memory = _get_memory()
    if isinstance(memory, dict) and "__error__" in memory:
        return {"ok": False, "error": memory["__error__"]}
    try:
        res = memory.add(messages=messages, user_id=user_id, metadata=metadata, agent_id=agent_id)
        return {"ok": True, "results": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def memory_search(query, user_id="you", agent_id=None, limit=5):
    """按 query 检索最相关的记忆（向量）。返回带 score 的记忆列表。

    mem0 search() 不接受 user_id/agent_id 作顶层参数，须放进 filters。"""
    memory = _get_memory()
    if isinstance(memory, dict) and "__error__" in memory:
        return {"ok": False, "error": memory["__error__"]}
    try:
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if agent_id:
            filters["agent_id"] = agent_id
        res = memory.search(query=query, filters=filters or None, limit=limit)
        return {"ok": True, "results": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def memory_update(memory_id, new_message):
    """更新已有记忆（按 memory_id）。返回更新后的条目。"""
    memory = _get_memory()
    if isinstance(memory, dict) and "__error__" in memory:
        return {"ok": False, "error": memory["__error__"]}
    try:
        res = memory.update(memory_id=memory_id, new_message=new_message)
        return {"ok": True, "results": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def memory_delete(memory_id):
    """删除指定记忆（按 memory_id）。"""
    memory = _get_memory()
    if isinstance(memory, dict) and "__error__" in memory:
        return {"ok": False, "error": memory["__error__"]}
    try:
        res = memory.delete(memory_id=memory_id)
        return {"ok": True, "results": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def memory_get(memory_id):
    """按 memory_id 获取单条记忆详情。"""
    memory = _get_memory()
    if isinstance(memory, dict) and "__error__" in memory:
        return {"ok": False, "error": memory["__error__"]}
    try:
        res = memory.get(memory_id=memory_id)
        return {"ok": True, "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def memory_reset():
    """清空全部记忆与索引（用于可重复演示）。"""
    memory = _get_memory()
    if isinstance(memory, dict) and "__error__" in memory:
        return {"ok": False, "error": memory["__error__"]}
    try:
        memory.reset()
        return {"ok": True, "message": "已清空全部记忆"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _http_main(port: int):
    import uvicorn

    uvicorn.run(mcp._app, host="0.0.0.0", port=port)  # noqa: SLF001


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="mem0 MCP server (本地 LM Studio 模型)")
    ap.add_argument("--http-port", type=int, default=None, help="以 HTTP/SSE transport 运行")
    args = ap.parse_args()
    if args.http_port:
        _http_main(args.http_port)
    else:
        mcp.run("stdio")

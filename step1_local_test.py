"""Step1: mem0本地后端跑通（Python SDK直连LM Studio，add→search→get）。

纯离线：LLM 与 embedder 均指向本地 LM Studio http://192.168.3.58:1234/v1。
运行: OPENAI_API_KEY=lmstudio MEM0_TELEMETRY=false ./pi_with_mem0/venv/bin/python ./pi_with_mem0/step1_local_test.py

本仓库安装的 mem0ai 版本用 pydantic MemoryConfig 构造（非 configure({...})）。
LLM / embedder 均使用 provider="lmstudio"，base url key = "lmstudio_base_url"。
"""
import os, sys

# 确保内层 SDK 包可被解析（仓库根目录 monorepo `mem0` 会遮挡真实 SDK）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mem0", "mem0"))

from mem0 import Memory
from mem0.configs.base import MemoryConfig

LM = "http://192.168.3.58:1234/v1"
LLM_MODEL = "ornith-1.5-35b-a3b-apex-mtp-i-compact"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

memory = Memory(config=MemoryConfig(
    llm={
        "provider": "lmstudio",
        "config": {
            "api_key": "lmstudio",  # 本地常可占位；若服务需 auth 填真实 token
            "lmstudio_base_url": LM,
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
            "lmstudio_base_url": LM,
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
))

print("=== Step1: 清空存储（保证每次可重复演示） ===")
memory.reset()

print("\n=== Step1: add ===")
res = memory.add(
    messages=[{"role": "user", "content": "我叫张三，喜欢用 Rust 写 pi agent。"}],
    user_id="you",
)
print(res)
memory_id = res["results"][0]["id"]

print("\n=== Step1: search ===")
hits = memory.search("我用什么语言？", filters={"user_id": "you"}, limit=3)
print(hits)

print("\n=== Step1: get ===")
one = memory.get(memory_id)
print(one)

# 验证断言
assert res["results"][0]["event"] == "ADD", "add 未返回 ADD"
assert any("Rust" in str(h.get("memory")) for h in hits["results"]), "search 未命中写入内容"
assert one is not None, "get 未取到记忆"
print("\n✅ Step1 通过：本地 mem0 add→search→get 闭环跑通（共用 LM Studio 模型）")

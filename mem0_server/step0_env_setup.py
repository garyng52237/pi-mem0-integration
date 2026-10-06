"""Step0: 环境搭建与可达性自检（本地 mem0 接入的前提）。

跑通本步再进入 Step1。纯离线、无外部联网。
运行: ./mem0_server/venv/bin/python ./mem0_server/step0_env_setup.py

覆盖教程 §一「可达性」自检 + 依赖就绪：
  1. venv Python 可用
  2. mem0 OSS SDK 可 import（需把内层包 ../mem0/mem0 加进 sys.path，避免仓库根 monorepo `mem0` 遮挡）
  3. fastmcp 可 import（Step2 MCP server 依赖）
  4. LM Studio `/v1/models` 同时返回 LLM 与 embedder 两个模型名
  5. LM Studio `/v1/embeddings` 可返回向量
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LM = os.environ.get("LM_URL", "http://localhost:1234/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "ornith-1.5-35b-a3b-apex-mtp-i-compact")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def main():
    ok = True

    # 1) venv Python
    try:
        py = subprocess.run([sys.executable, "--version"], capture_output=True, text=True, timeout=10)
        ok &= check("venv Python", rc := (py.returncode == 0), (py.stdout.strip() or py.stderr.strip()))
    except Exception as e:
        ok &= check("venv Python", False, str(e))

    # 2) mem0 SDK import（优先 pip 安装的 mem0ai；若旁边有本地 clone ../mem0/mem0，则加进 sys.path）
    try:
        _clone = os.path.join(HERE, "..", "mem0", "mem0")
        if os.path.isdir(_clone):
            sys.path.insert(0, _clone)
        from mem0 import Memory
        ok &= check("mem0 OSS SDK import", True, Memory.__module__)
    except Exception as e:
        ok &= check("mem0 OSS SDK import", False, str(e))

    # 3) fastmcp import（Step2 MCP server 依赖）
    try:
        from fastmcp import FastMCP
        ok &= check("fastmcp import", True, FastMCP.__module__)
    except Exception as e:
        ok &= check("fastmcp import", False, str(e))

    # 4) LM Studio /v1/models（需同时含 LLM + embedder）
    try:
        models = subprocess.run(
            ["curl", "-s", "--max-time", "8", f"{LM}/models"],
            capture_output=True, text=True, timeout=15,
        )
        txt = (models.stdout or "").lower()
        has_llm = LLM_MODEL.lower() in txt
        has_embed = EMBED_MODEL.lower() in txt
        ok &= check("LM Studio /v1/models 含 LLM", has_llm, LLM_MODEL)
        ok &= check("LM Studio /v1/models 含 embedder", has_embed, EMBED_MODEL)
    except Exception as e:
        ok &= check("LM Studio /v1/models", False, str(e))

    # 5) LM Studio /v1/embeddings（返回向量）
    try:
        emb = subprocess.run(
            ["curl", "-s", "--max-time", "8", f"{LM}/embeddings",
             "-H", "Content-Type: application/json",
             "--data", '{"model":"%s","input":"hi"}' % EMBED_MODEL],
            capture_output=True, text=True, timeout=15,
        )
        data = (emb.stdout or "").strip()
        ok &= check("LM Studio /v1/embeddings 返回向量", '"embedding"' in data and "data" in data, data[:80])
    except Exception as e:
        ok &= check("LM Studio /v1/embeddings", False, str(e))

    print("\n" + ("✅ Step0 通过：环境就绪，LM Studio 本地可达（LLM + embedder）" if ok else "❌ Step0 未通过：请检查 venv / mem0ai 安装 / LM Studio 可达性"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

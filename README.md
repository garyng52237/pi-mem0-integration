# pi-mem0-integration

把 [mem0](https://github.com/mem0ai/mem0) 记忆系统接入本地模型后端（UnSloth / LM Studio），并以标准 **MCP (Model Context Protocol)** server 的形式对外暴露记忆工具，供 [pi](https://github.com/anthropics/pi)（或任何 MCP client）消费。

各文件按开发顺序组织：

- `step0_env_setup.py` —— 环境搭建与可达性自检
- `step1_local_test.py` —— 本地后端直连跑通（add → search → get）
- `step2_mcp_end_to_end.py` —— 端到端验证 MCP server
- `mem0_mcp_server.py` —— 生产用 MCP server（对外暴露记忆工具）
- `CHANGE.log` —— 开发变更记录

## 为什么需要这个项目

pi 本身不带长期记忆。本项目用 mem0 给 pi 补齐"记忆"能力：

- 对话中产生的事实、偏好、上下文可被自动抽取并持久化；
- 之后可通过向量检索把相关记忆召回；
- 记忆以 MCP 工具的形式暴露，任何 MCP client（包括 pi）都能调用。

mem0 的 LLM 与 embedder 共用同一个本地后端（UnSloth 部署，替换原 LM Studio），满足"两者用同一个模型"。

## 架构

```
pi (MCP client)
   │  MCP stdio
   ▼
mem0_mcp_server.py  ── mem0 SDK ──► 本地模型后端 (UnSloth/LM Studio)
                                      ├─ LLM：ornith-1.5-35b-a3b-apex-mtp-i-compact
                                      └─ Embedder：text-embedding-nomic-embed-text-v1.5
   ▼
Qdrant 向量库（本地，data/ 目录）
```

## 暴露的工具

`mem0_mcp_server.py` 通过 FastMCP 暴露六个工具：

| 工具 | 作用 |
| --- | --- |
| `memory_add` | 向记忆库写入/提取新记忆 |
| `memory_search` | 按 query 检索最相关的记忆 |
| `memory_update` | 更新已有记忆 |
| `memory_delete` | 删除指定记忆 |
| `memory_get` | 获取单条记忆详情 |
| `memory_reset` | 清空全部记忆与索引 |

## 运行方式

### 作为 MCP server（供 MCP client 连接）

```bash
./pi_with_mem0/venv/bin/python mem0_mcp_server.py            # stdio 模式
```

### 作为 HTTP server（可选）

```bash
OPENAI_API_KEY=sk-unsloth-xxxxxxxx ./pi_with_mem0/venv/bin/python mem0_mcp_server.py --http-port 8123
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LM_URL` | `http://192.168.3.58:1234/v1` | UnSloth/LM Studio 后端地址 |
| `LM_API_KEY` | `sk-unsloth-xxxxxxxx` | 后端 API Key |
| `LLM_MODEL` | `ornith-1.5-35b-a3b-apex-mtp-i-compact` | 抽取记忆用的模型 |
| `EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | embedding 模型 |

## 本地快速验证

```bash
# Step0：环境自检（venv / SDK / fastmcp / 后端可达性）
./pi_with_mem0/venv/bin/python step0_env_setup.py

# Step1：本地后端直连跑通
OPENAI_API_KEY=lmstudio MEM0_TELEMETRY=false ./pi_with_mem0/venv/bin/python step1_local_test.py

# Step2：端到端 MCP 验证
./pi_with_mem0/venv/bin/python step2_mcp_end_to_end.py
```

> 本地推理较慢，`add`/`search` 各需数十秒，请给足超时。

## 注意事项

- **同一模型**：LLM 与 embedder 共用同一个本地后端，需保证两者都能返回结果。
- **响应格式**：UnSloth 后端不接受 mem0 默认的 `{"type":"json_object"}`，已设为 `text`，让模型返回纯文本 JSON，由 mem0 parser 自带 `extract_json` fallback 解析。
- **向量维度**：nomic embedder 实测返回 384 维，需与 Qdrant 配置一致，否则点积维度不匹配而报错。

## 依赖

- `mem0ai`（本地 SDK 位于仓库 `../mem0/mem0`）
- `fastmcp` / `mcp`（MCP 协议）
- `uvicorn`（HTTP 模式可选）
- 本地后端：UnSloth 或 LM Studio

## 许可证

本仓库为个人项目，保留所有权利。

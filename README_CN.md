# pi-mem0-integration

<p align="center">
  <a href="README_CN.md">中文</a> ·
  <a href="README.md">English</a>
</p>

一个面向本地 LLM（UnSloth / LM Studio）的 **mem0** 记忆后端，以标准 **MCP (Model Context Protocol)** server 的形式对外暴露记忆工具，供 [pi](https://github.com/anthropics/pi)（或任何 MCP client）读写记忆。

---

## 目录

- [简介](#简介)
- [为什么需要这个项目](#为什么需要这个项目)
- [架构](#架构)
- [暴露的工具](#暴露的工具)
- [前置条件](#前置条件) ⚠️
- [安装](#安装)
- [运行方式](#运行方式)
- [环境变量](#环境变量)
- [部署](#部署)
- [本地快速验证](#本地快速验证)
- [注意事项](#注意事项)
- [仓库结构](#仓库结构)
- [依赖](#依赖)
- [许可证](#许可证)

---

## 简介

`mem0_mcp_server.py` 封装了 [mem0](https://github.com/mem0ai/mem0) SDK，通过 MCP 协议对外暴露六个记忆工具。LLM 与 embedder 共用同一个本地后端（UnSloth 替换原 LM Studio），两者跑在同一模型上。

## 为什么需要这个项目

pi 本身不带长期记忆。本项目用 mem0 给 pi 补齐"记忆"能力：

- 对话中产生的事实、偏好、上下文被自动抽取并持久化；
- 之后通过向量检索把相关记忆召回；
- 记忆以 MCP 工具的形式暴露，任何 MCP client（包括 pi）都能调用。

## 架构

```
pi / pi-forge  (MCP client)          ← 需自行安装 pi-agent（见下文）
   │  MCP stdio
   ▼
mem0_mcp_server.py  ── mem0 SDK ──►  本地模型后端 (UnSloth / LM Studio)
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

## 前置条件 ⚠️

> ⚠️ **重要：本仓库只是「记忆后端」部分，必须先自行安装 pi-agent。**
>
> 本项目只负责把 mem0 记忆能力通过 MCP 暴露出来。要真正跑起带记忆的 pi，
> 你需要先拥有自己的 **pi-agent（pi 框架本体）**，再让 pi 通过这个 MCP server 连接记忆。
> 本仓库不包含 pi-agent，也不替你做 pi 的安装/初始化。

完整步骤见 [部署](#部署)。

## 安装

```bash
cd pi_with_mem0
python -m venv venv
source venv/bin/activate
pip install mem0ai fastmcp
```

## 运行方式

### 作为 MCP server（stdio 模式）

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
| `LM_URL` | `http://192.168.3.58:1234/v1` | UnSloth / LM Studio 后端地址 |
| `LM_API_KEY` | `sk-unsloth-xxxxxxxx` | 后端 API Key |
| `LLM_MODEL` | `ornith-1.5-35b-a3b-apex-mtp-i-compact` | 抽取记忆用的模型 |
| `EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | embedding 模型 |

## 部署

1. **先安装 pi-agent（pi 框架本体）**（本仓库不提供）。
   - 下载并安装好 pi-agent。
   - 确保有一个可用的本地模型后端（UnSloth 或 LM Studio），
     本仓库默认指向 `http://192.168.3.58:1234/v1`。

2. **安装本仓库依赖**（见 [安装](#安装)）。

3. **连接 MCP 服务。**
   - 以 stdio 方式启动 mem0 MCP server：
     ```bash
     ./pi_with_mem0/venv/bin/python mem0_mcp_server.py
     ```
   - 在 pi-agent 的配置里（如 `mcp.json`）登记该 server，
     把 `LM_URL`/`LM_API_KEY` 等环境变量注入进去，pi 即可使用记忆工具。

4. **验证。**
   - 跑 `./pi_with_mem0/venv/bin/python step2_mcp_end_to_end.py` 确认 MCP 端到端可用。

> 本地推理较慢，连接与记忆操作各需数十秒，请给足超时。

## 本地快速验证

```bash
# Step0：环境自检（venv / SDK / fastmcp / 后端可达性）
./pi_with_mem0/venv/bin/python step0_env_setup.py

# Step1：本地后端直连跑通（add → search → get）
OPENAI_API_KEY=lmstudio MEM0_TELEMETRY=false ./pi_with_mem0/venv/bin/python step1_local_test.py

# Step2：端到端 MCP 验证
./pi_with_mem0/venv/bin/python step2_mcp_end_to_end.py
```

## 注意事项

- **同一模型**：LLM 与 embedder 共用同一个本地后端，需保证两者都能返回结果。
- **响应格式**：UnSloth 后端不接受 mem0 默认的 `{"type":"json_object"}`（报 400），已设为 `text`，让模型返回纯文本 JSON，由 mem0 parser 自带 `extract_json` fallback 解析。
- **向量维度**：nomic embedder 实测返回 384 维，需与 Qdrant 配置维度一致，否则点积维度不匹配而报错。
- **查询健壮性**：`memory_search` 会把 `query` 归一化为非空字符串，并始终附带 `user_id` filter，因此不会因为输入被包装（如 `{"query": "..."}`）或缺少 filter 而失败。

## 仓库结构

| 文件 | 说明 |
| --- | --- |
| `step0_env_setup.py` | 环境搭建与可达性自检 |
| `step1_local_test.py` | 本地后端直连跑通（add → search → get） |
| `step2_mcp_end_to_end.py` | 端到端验证 MCP server |
| `mem0_mcp_server.py` | 生产用 MCP server（对外暴露记忆工具） |
| `CHANGE.log` | 开发变更记录 |

## 依赖

- `mem0ai`（本地 SDK 位于仓库 `../mem0/mem0`）
- `fastmcp` / `mcp`（MCP 协议）
- `uvicorn`（可选，HTTP 模式）
- 本地后端：UnSloth 或 LM Studio

## 许可证

本仓库为个人项目，保留所有权利。

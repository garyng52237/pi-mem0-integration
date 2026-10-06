# pi-mem0：pi-agent × mem0 持久记忆集成（独立可移植 kit）

让 **pi-agent** 拥有持久记忆，且 LLM（抽取/改写记忆）与 embedding（向量化）**共用同一个本地 LM Studio 模型**。纯离线、无外部联网。

> 本目录是「我们的代码 + 安装说明」的独立 kit——不打包第三方大依赖
> （mem0ai SDK / pi CLI / Python venv），通过 `mem0_server/requirements.txt` + `setup_venv.sh` 重建环境，
> 因此小巧、可移植。原始工作副本仍在 `/home/gary/pi_agent_mem0_project/`（未改动）。

---

## 1. 架构（为什么这样结合）

mem0 = Python，pi = TypeScript，存在语言边界。**结论先行**：用 **MCP server** 作为两者之间最干净、可热插拔的契约层——
Python 把 mem0 封装成标准 MCP server（同一本地模型对外暴露记忆工具），pi 作为 MCP client 消费，无需改动 pi 核心代码。

```
pi-agent (TS) ──MCP stdio──▶ mem0_mcp_server.py (fastmcp 4.x, 6 tools)
                                    │
                    LLM + embedding 共用同一本地模型
                                    ▼
                         LM Studio @ http://localhost:1234/v1（可配置）
```

记忆工具：`memory_add / memory_search / memory_update / memory_delete / memory_get / memory_reset`。

---

## 2. 目录结构

```
pi_mem0_project/
├── README.md                         # 本指南
├── extensions/memory/                # pi ↔ mem0 桥接扩展（TypeScript，jiti 热加载）
│   ├── index.ts                      # 注册 MCP 工具；默认指向 ./mem0_server/
│   ├── package.json                  # Node deps: @modelcontextprotocol/sdk ^1.0.0, typebox 1.3.27
│   └── debug/                        # 调试辅助（cap_client.mjs / dbg_client.mjs + wrappers）
├── mem0_server/                      # mem0 MCP server + 环境自检/测试脚本
│   ├── mem0_mcp_server.py            # fastmcp 4.x，6 个记忆工具
│   ├── step0_env_setup.py            # 环境可达性自检（venv / mem0ai / LM Studio）
│   ├── step1_local_test.py           # 纯离线 add→search→get 闭环
│   ├── step2_mcp_end_to_end.py       # 标准 MCP stdio 端到端调用
│   ├── requirements.txt              # Python 依赖（对齐已验证 venv 版本）
│   └── setup_venv.sh                 # 创建独立 venv 并安装依赖
├── scripts/
│   └── pi-mem0                       # 终端唤醒命令（cd 到目标 pi 项目 → 跑 pi CLI）
└── docs/                             # 详细分析 / 集成总结 / 变更日志
    ├── 结合分析报告.md
    ├── INTEGRATION_SUMMARY.md
    └── CHANGE.log
```

---

## 3. 前置条件

- **LM Studio** 已加载同一本地模型，且 `/v1/models` 同时返回 LLM 与 embedder：
  - LLM: `ornith-1.5-35b-a3b-apex-mtp-i-compact`
  - Embedder: `text-embedding-nomic-embed-text-v1.5`（实测输出 **768 维**，非默认 1536）
  - URL: `http://localhost:1234/v1`（可用 `PI_MEM0_PROVIDER_URL` 或 `LM_URL` 覆盖）
- **pi CLI** 已安装（bundled bundle）。默认路径：
  `/root/.local/bin/lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js`
  （可用 `PI_MEM0_CLI` 覆盖）。

---

## 4. 第 1 步：安装 pi CLI（必须先做）

`pi-mem0` 包装脚本调用的是**全局安装的 pi CLI**——它不是本 kit 的一部分，所以这是**使用引导的第一步**，务必先装。

官方安装：

```bash
npm install -g @earendil-works/pi-coding-agent
```

若本机无 bun/tsgo（官方 bundle 由 bun 打包、依赖各 workspace 包的 `tsgo` unbundled 产物），改用自定义 prefix 安装，避免与系统 `/usr/bin/pi` 冲突：

```bash
npm install -g @earendil-works/pi-coding-agent --prefix ~/.local/bin
```

装完即可用 `pi` / `pi-mem0`。默认调用路径（可用 `PI_MEM0_CLI` 覆盖）：
`~/.local/bin/lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js`

---

## 5. 搭建 Python 环境（一次）

```bash
cd pi_mem0_project/mem0_server
./setup_venv.sh        # 创建 ./venv → 安装 requirements.txt → 自动跑 step0 自检
```

若本地有 mem0 clone（`../mem0/mem0`），step0/step1 会自动把它加进 `sys.path`；否则直接用 pip 安装的 `mem0ai==2.0.20`。

---

## 6. 把扩展注册进一个 pi 项目

本 kit 是「源码」，要真正唤醒 agent，需把扩展装进某个 **目标 pi 项目的 `.pi/extensions/`**：

```bash
# 在目标 pi 项目根目录下（例如 /path/to/pi-project）：
mkdir -p .pi/extensions
cp -r "$PI_MEM0_PROJECT_ROOT/../extensions/memory" .pi/extensions/memory   # 或指向本 kit 路径
```

**关键坑（务必避免）**：`.pi/extensions/` 文件系统自动发现 + `settings.json` `packages` 注册会**双加载同一条扩展**，导致工具冲突报错。
→ **只保留其一**。推荐纯自动发现：**不要**在 `.pi/settings.json` 的 `packages` 里再写 `extensions/memory`。

示例 `.pi/settings.json`（最小可用）：

```json
{ "httpIdleTimeoutMs": 300000 }
```

> mem0 本地推理较慢（`memory_add` ~49s），已放宽 MCP 请求超时至 300s（`index.ts` 中 `REQUEST_TIMEOUT_MSEC`，可用 `MEM0_REQUEST_TIMEOUT_MS` 覆盖）。

---

## 7. 唤醒 agent

```bash
# 默认用当前目录作为目标 pi 项目根：
cd /path/to/pi-project
pi-mem0 "你好"

# 或显式指定项目根：
PI_MEM0_PROJECT_ROOT=/path/to/pi-project pi-mem0 "帮我记住：我的偏好是..."
```

`-p` 选用 lmstudio provider；`--approve` 信任本地文件（本次运行）。验证输出应显示 MCP server connected、工具列出、agent 正常回复。

### 持久化项目信任（免 `--approve`）

`pi-mem0` 默认带 `--approve` 以便开箱即用。若希望**不带 `--approve` 也能唤醒**，需持久化该项目信任决策
（trustStore 为本 cwd 写入 true / 或设置 `defaultProjectTrust`）。详见 `docs/结合分析报告.md` 中「项目信任」一节。

---

## 8. 模型同步：不写死 + mem0 跟随 pi 选中的模型

本集成**不把模型写死**。扩展从本地 LM Studio `/v1/models` 动态拉取当前已加载的全部模型，pi 可在交互界面自由选择任意一个；mem0 会**自动同步到 pi 当前选中的那个模型**（LLM 与 embedding 仍共用同一后端）。

机制：
- pi 在 `session_start` 时把当前选中模型的 id 注入扩展（`ctx.getModel()` → `{ provider, id }`）；
- 扩展记为 `syncedModelId`，每次启动 mem0 server 时用
  `LLM_MODEL = process.env.LLM_MODEL ?? syncedModelId ?? DEFAULT_LLM_MODEL`；
- 因此你在 pi 里换模型，mem0 的 LLM 立即用同一个。

环境变量覆盖（可选）：

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `LM_URL` | 本地后端地址（mem0 server 用） | `http://localhost:1234/v1` |
| `LLM_MODEL` | mem0 推理模型；不设置则跟随 pi 选中模型 | `ornith-1.5-35b-a3b-apex-mtp-i-compact` |
| `EMBED_MODEL` | mem0 embedding 模型（**独立配置**，可不同于 LLM） | `text-embedding-nomic-embed-text-v1.5` |

Embedder 的入口就是 `EMBED_MODEL`：它与 LLM 解耦，可在同一后端选不同的 embedding 模型。两者共用同一个本地 LM Studio 后端。

已验证（真实 mem0 服务端到端）：
- pi 默认选中 `ornith-1.5-35b-a3b-apex-mtp-i-compact` → mem0 的 chat/embedding 均用该模型；
- pi 手动换成 `qwen3.6-35b-a3b` → mem0 的 `/v1/chat/completions` **自动同步为 `qwen3.6-35b-a3b`**，embedding 仍为 `text-embedding-nomic-embed-text-v1.5`。

实现位置：`.pi/extensions/memory/index.ts`（`buildServerEnv()`、`session_start`、动态 `registerProvider`）；覆盖链在 `mem0_server/mem0_mcp_server.py`。

---

## 9. 调试与验证

- `mem0_server/step0_env_setup.py` — 环境可达性自检（venv / mem0ai / LM Studio LLM+embedder）
- `mem0_server/step1_local_test.py` — 纯离线 add→search→get 闭环
- `mem0_server/step2_mcp_end_to_end.py` — 标准 MCP stdio 端到端（reset→add→search→get→delete）
- `extensions/memory/debug/*` — MCP stdio client/server 调试辅助

---

## 10. 关键经验（踩坑备忘）

1. **vLLM/LM Studio 不接受 mem0 默认的 `{"type":"json_object"}`**（报 400）→ 设 `"lmstudio_response_format": {"type":"text"}`，让模型返回纯文本 JSON，mem0 parser 自带 `extract_json` fallback。
2. **nomic-embed-text-v1.5 实测 768 维** → `embedding_dims: 768` + qdrant `embedding_model_dims: 768`（默认 1536 会维度不匹配报错）。
3. **fastmcp 4.x 读 `params.arguments`，非 `parameters`** — 桥接已据此适配。
4. **双加载冲突**：`.pi/extensions/` 自动发现 + `settings.json` packages 注册 → 重复 registerTool → "Tool 'X' conflicts"。**只保留其一**。

---

## 参考文档

- `docs/结合分析报告.md` — 融合分析（现状、已验证事实、架构切入）
- `docs/INTEGRATION_SUMMARY.md` — 集成实现总结
- `docs/CHANGE.log` — 实现步骤与踩坑日志

# mem0 ↔ pi-agent 结合方案说明

## 一、切入方式（How to integrate）

**通过 MCP Extension 接入**，而非改 pi 内核。依据 `pi/pi-项目架构分析.md`：

- pi 的 Agent 运行时在 `pi/packages/coding-agent/src/core/agent.ts`，工具来源是
  `AgentSession.tools()` → `extensionsRunner.getTools()`（扩展注册的工具）。
- 扩展通过 `.pi/extensions/<name>/index.ts` 暴露默认导出 `(pi) => void`，
  调用 `pi.registerTool(...)` 注册工具、`pi.on("session_start"/"session_shutdown")`
  挂生命周期钩子。加载器见 `loader.ts`（registerTool 仅在加载期有效）。

因此结合点 = **写一个 MCP Extension**，把 mem0 的 6 个记忆工具注册进 pi，
让 pi 的 LLM 像调用 native tool 一样调用它们。已实现并端到端验证通过：
`.pi/extensions/memory/index.ts`。

## 二、从哪几方面结合（Aspects）

| 维度 | 结合方式 | 状态 |
|------|----------|------|
| **1. 模型共享** | pi 与 mem0 均指向同一本地 LM Studio 端点，同一条 LLM/Embedding 链路 | ✅ 已验证 |
| **2. 记忆层工具** | 6 个 MCP 工具（add/search/update/delete/get/reset）注册进 pi | ✅ 已验证 |
| **3. 生命周期钩子** | session_start → 自动 load；session_shutdown → 可选 reset | ✅ 已接线 |
| **4. 工具编排** | mem0 记忆工具与 pi native tool（bash/read/write/edit…）在同一轮共存、可并行/串行执行 | ✅ 架构支持 |
| **5. 结果呈现** | mem0 JSON 文本 → pi AgentToolResult，带 ok/summary 细节 | ✅ 已验证 |

## 三、两者用同一本地模型（Shared local model）

关键：mem0 的 LLM 与 Embedding **复用 pi 正在用的同一个 LM Studio**，不引入新模型。

配置（`mem0_server/mem0_mcp_server.py` env）：
```
OPENAI_API_KEY=lmstudio
LM_URL=http://localhost:1234/v1          # 本地 LM Studio，可按机器覆盖
LLM_MODEL=ornith-1.5-35b-a3b-apex-mtp-i-compact   # pi 与 mem0 共用
EMBED_MODEL=text-embedding-nomic-embed-text-v1.5
MEM0_TELEMETRY=false                      # 关闭遥测，纯本地
```

验证（端到端）：memory_add / memory_search 均返回 `ok:true`，
成功写入并检索到 `"the pi and mem0 projects share the same local LM Studio model"`。

## 四、实现要点与坑

1. **TypeBox API**：pi-coding-agent 用的 typebox@1.3.27（git 版）方法为 **PascalCase**
   （`Type.Object/String/Record/Union/Optional`），非小写。扩展已装 `typebox@1.3.27`。
2. **工具参数**：必须用 MCP `arguments`（非 positional args），并传 `{timeout:300000}`。
3. **结果解析**：mem0 返回 JSON 文本在 `content[0].text`，需再 `JSON.parse` 读 `ok/results`。
4. **可选依赖**：spaCy / fastembed 未装（BM25/lemma 降级），不影响核心 add/search。

## 五、后续可扩展方向

- 把 load/reset 钩子做成可配置（默认 load，reset 需显式）。
- 记忆工具加 `executionMode: "parallel"` 与 native tool 并行。
- 按用户/会话隔离 `user_id`（memory_add 已支持）。
- 如需 pi 侧也直接调用同一模型做推理，复用 `LM_URL + LLM_MODEL` 即可，无需额外配置。

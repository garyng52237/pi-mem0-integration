/**
 * pi + mem0 记忆桥接扩展（Step4）
 *
 * 结合方式（path A + path C）：
 *   - Step2 已把 mem0 封装为标准 MCP server（mem0_mcp_server.py），LLM 与 embedding
 *     共用同一本地 LM Studio 后端，满足"两者用同一个模型"。
 *   - 本扩展以 stdio transport 启动该 MCP server，通过 @modelcontextprotocol/sdk
 *     建立 MCP client session，把 mem0 的记忆工具注册为 pi 自定义工具。
 *   - LLM 在对话中按需调用 memory_add / memory_search，实现"记忆即工具"的接入。
 *
 * 加载位置：项目根 `.pi/extensions/memory/index.ts`（jiti 加载，无需编译）。
 * 环境变量覆盖（可选）：
 *   MEM0_MCP_SERVER_PY   mem0 MCP server python 脚本路径
 *   VENV_PYTHON          用于启动该脚本的 python 解释器（venv/bin/python）
 *   LM_URL / LLM_MODEL / EMBED_MODEL  本地模型后端（默认跟随 mem0_mcp_server.py）
 *
 * 注意事项：
 *   - fastmcp 4.0.3（spec 2025-06-18）读取 tools/call 的 `arguments` 字段，故 callTool
 *     必须用 `{ name, arguments }`（非旧版 `parameters`）。
 *   - 本地大模型推理较慢（实测 memory_add ~49s），故每个请求 timeout 设为 300s。
 */

import type { ExtensionAPI, AgentToolResult } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

// 推导本 kit 的项目根（jiti 下 import.meta.url 已实测可正常解析，见 docs）。
// 本扩展位于 <项目根>/extensions/memory/index.ts，故向上两级即项目根。
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// 配置（可用环境变量覆盖；默认指向本 kit 的 mem0_server/）
// ---------------------------------------------------------------------------
const __EXT_DIR = dirname(fileURLToPath(import.meta.url)); // .../extensions/memory
const PROJECT_ROOT = dirname(dirname(__EXT_DIR));           // .../<项目根>

const MEM0_MCP_SERVER_PY =
  process.env.MEM0_MCP_SERVER_PY || join(PROJECT_ROOT, "mem0_server", "mem0_mcp_server.py");
const VENV_PYTHON =
  process.env.MEM0_VENV_PYTHON || join(PROJECT_ROOT, "mem0_server", "venv", "bin", "python");

// 传给 mem0 MCP server 的环境（复用 step1/step2 实测可达的本地模型）
const SERVER_ENV: Record<string, string> = {
  ...process.env,
  OPENAI_API_KEY: process.env.OPENAI_API_KEY || "lmstudio",
  MEM0_TELEMETRY: process.env.MEM0_TELEMETRY || "false",
  LM_URL: process.env.LM_URL || process.env.PI_MEM0_PROVIDER_URL || "http://localhost:1234/v1",
  LLM_MODEL: process.env.LLM_MODEL || process.env.PI_MEM0_LLM_MODEL || "ornith-1.5-35b-a3b-apex-mtp-i-compact",
  EMBED_MODEL: process.env.EMBED_MODEL || "text-embedding-nomic-embed-text-v1.5",
};

// mem0 本地推理较慢（memory_add ~49s），每个 MCP 请求放宽超时
const REQUEST_TIMEOUT_MSEC = Number(process.env.MEM0_REQUEST_TIMEOUT_MS || 300000);

// ---------------------------------------------------------------------------
// MCP client 单例（跨工具调用复用同一进程/会话）
// ---------------------------------------------------------------------------
let client: Client | null = null;
let transport: StdioClientTransport | null = null;
let connected = false;

interface MemoryDetails {
  tool: string;
  ok: boolean;
  summary: string;
}

/** 幂等：确保 MCP session 已连接；进程死亡后自动重连。 */
async function ensureConnected(): Promise<Client> {
  if (client && connected) return client;

  // 旧 transport 若已关闭，丢弃并重建
  const prevClient = client;
  client = new Client({ name: "pi-mem0", version: "0.1.0" });
  transport = new StdioClientTransport({
    command: VENV_PYTHON,
    args: [MEM0_MCP_SERVER_PY],
    env: SERVER_ENV,
    stderr: "inherit",
  });

  // 进程异常退出时标记断开，下次调用自动重连
  transport.onclose = () => {
    connected = false;
  };
  transport.onerror = (err) => {
    connected = false;
  };

  await client.connect(transport);
  connected = true;

  // 列出 server 暴露的工具，便于日志确认
  const tools = await client.listTools();
  console.log(`[pi-mem0] MCP server connected. Tools: ${(tools.tools ?? []).map((t) => t.name).join(", ")}`);

  return client;
}

/** 把 mem0 MCP tool 结果转换为 pi AgentToolResult。 */
function toPiResult(toolName: string, raw: unknown): AgentToolResult<MemoryDetails> {
  const r = (raw ?? {}) as Record<string, unknown>;
  // mem0_mcp_server.py 返回 JSON 文本（content[0].text），解析之；否则原样序列化
  let body = typeof r.content?.[0]?.text === "string" ? r.content[0].text : "";
  if (!body) {
    try {
      body = JSON.stringify(r, null, 2);
    } catch {
      body = String(raw ?? "");
    }
  }
  // ok/results 位于内部 JSON 字符串中，需解析后再读
  let parsed: Record<string, unknown> | null = null;
  if (body) {
    try {
      parsed = JSON.parse(body);
    } catch {
      /* ignore */
    }
  }
  const ok = !Boolean(r.isError) && (Boolean(parsed?.ok ?? parsed?.success ?? true));
  let summary = "完成";
  try {
    if (parsed?.results?.message || parsed?.message) summary = String(parsed.message ?? parsed.results?.message);
  } catch {
    /* ignore */
  }
  return {
    content: [{ type: "text", text: body }],
    details: { tool: toolName, ok, summary },
  };
}

/** 调用 mem0 MCP 工具（统一用 arguments 字段 + 放宽超时）。 */
async function callMem0(toolName: string, args: Record<string, unknown>): Promise<AgentToolResult<MemoryDetails>> {
  const client = await ensureConnected();
  const raw = await client.callTool({ name: toolName, arguments: args }, undefined, { timeout: REQUEST_TIMEOUT_MSEC });
  return toPiResult(toolName, raw);
}

// ---------------------------------------------------------------------------
// 工具参数 schema（与 mem0_mcp_server.py 的 Python 签名一致）
// ---------------------------------------------------------------------------
const MetadataSchema = Type.Optional(
  Type.Record(Type.String(), Type.Union([Type.String(), Type.Number(), Type.Boolean(), Type.Array(Type.String()), Type.Null()])),
);

const memoryAddTool = {
  name: "memory_add",
  label: "Add Memory",
  description:
    "把值得长期记住的信息写入记忆库。当用户陈述一个事实、偏好、决定、日程或背景，且希望在未来的对话中被回忆时使用。" +
    "适合：'我更喜欢...'、'请记住...'、'下次...'、项目关键决策等。不适合纯本次任务内的临时中间结果。",
  promptSnippet: "Persist durable facts/preferences/decisions to long-term memory",
  promptGuidelines: [
    "Call memory_add when the user shares something worth recalling in later conversations (preferences, decisions, facts, context).",
    "Pass the raw user statement as `messages`; add useful key/value pairs via `metadata`.",
  ],
  parameters: Type.Object({
    messages: Type.Union([Type.String(), Type.Array(Type.String())], { description: "要记忆的用户原文/对话文本" }),
    user_id: Type.Optional(Type.String({ description: "所属用户，默认 you" })),
    agent_id: Type.Optional(Type.String({ description: "所属 agent，默认 pi" })),
    metadata: MetadataSchema,
  }),
  async execute(_toolCallId, params) {
    return callMem0("memory_add", params);
  },
};

const memorySearchTool = {
  name: "memory_search",
  label: "Search Memory",
  description:
    "从记忆库检索与当前问题最相关的历史记忆。当用户的提问依赖过去的对话、偏好或已存储的知识时使用——" +
    "在回答涉及'之前'、'还记得吗'、基于历史建议等问题前，先调用它召回相关记忆。",
  promptSnippet: "Recall stored memories relevant to the current question",
  promptGuidelines: [
    "Call memory_search before answering questions that depend on past conversation or stored preferences.",
    "Use a concise natural-language query; raise `limit` for broad recall.",
  ],
  parameters: Type.Object({
    query: Type.String({ description: "检索关键词/自然语言查询" }),
    user_id: Type.Optional(Type.String({ description: "所属用户，默认 you" })),
    agent_id: Type.Optional(Type.String({ description: "所属 agent" })),
    limit: Type.Optional(Type.Number({ description: "返回条数上限，默认 5" })),
  }),
  async execute(_toolCallId, params) {
    return callMem0("memory_search", params);
  },
};

const memoryUpdateTool = {
  name: "memory_update",
  label: "Update Memory",
  description: "按 memory_id 更新已有记忆（当用户修正或补充一条已存储的信息时）。",
  promptSnippet: "Update an existing stored memory by id",
  parameters: Type.Object({
    memory_id: Type.String({ description: "要更新的记忆 ID" }),
    new_message: Type.String({ description: "更新后的内容" }),
  }),
  async execute(_toolCallId, params) {
    return callMem0("memory_update", params);
  },
};

const memoryDeleteTool = {
  name: "memory_delete",
  label: "Delete Memory",
  description: "按 memory_id 删除一条记忆（当用户要求遗忘/移除某条信息时）。",
  promptSnippet: "Delete a stored memory by id",
  parameters: Type.Object({
    memory_id: Type.String({ description: "要删除的记忆 ID" }),
  }),
  async execute(_toolCallId, params) {
    return callMem0("memory_delete", params);
  },
};

const memoryGetTool = {
  name: "memory_get",
  label: "Get Memory Detail",
  description: "按 memory_id 获取单条记忆的完整详情。",
  promptSnippet: "Fetch a single stored memory by id",
  parameters: Type.Object({
    memory_id: Type.String({ description: "记忆 ID" }),
  }),
  async execute(_toolCallId, params) {
    return callMem0("memory_get", params);
  },
};

const memoryResetTool = {
  name: "memory_reset",
  label: "Reset Memory",
  description: "清空全部记忆与索引。仅用于可重复演示/重置，正常对话不要调用。",
  promptSnippet: "Clear all memories and index (demo/reset only)",
  promptGuidelines: ["Only call memory_reset to wipe the store for a fresh demo; never during normal conversation."],
  parameters: Type.Object({}),
  async execute(_toolCallId) {
    return callMem0("memory_reset", {});
  },
};

// ---------------------------------------------------------------------------
// 扩展入口
// ---------------------------------------------------------------------------
export default function (pi: ExtensionAPI) {
  // 注册本地 LM Studio provider（openai-completions，指向 /v1/chat/completions）。
  // 官方 llama.cpp 扩展同款模式：extension 通过 registerProvider 注入 provider，
  // pi 在 --provider lmstudio 时选用。默认后端跟随本项目实测可达的 LM Studio；
  // 可用 OPENAI_BASE_URL / OPENAI_API_KEY 覆盖（与 mem0 MCP server 共用同一后端）。
  pi.registerProvider("lmstudio", {
    name: "LM Studio (local)",
    baseUrl: process.env.OPENAI_BASE_URL || process.env.PI_MEM0_PROVIDER_URL || "http://localhost:1234/v1",
    apiKey: process.env.OPENAI_API_KEY || "lmstudio",
    api: "openai-completions",
    models: [
      {
        id: process.env.PI_MEM0_LLM_MODEL || "ornith-1.5-35b-a3b-apex-mtp-i-compact",
        name: "Ornith 1.5 35B (LM Studio)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 200000,
        maxTokens: 8192,
      },
    ],
  });

  // 注册记忆工具
  pi.registerTool(memoryAddTool);
  pi.registerTool(memorySearchTool);
  pi.registerTool(memoryUpdateTool);
  pi.registerTool(memoryDeleteTool);
  pi.registerTool(memoryGetTool);
  pi.registerTool(memoryResetTool);

  // 会话启动时预热（尽早建立 MCP session，便于 LLM 首轮即可调用）
  pi.on("session_start", async (_event, ctx) => {
    try {
      await ensureConnected();
      ctx.ui.notify("mem0 memory bridge initialized (local LM Studio model)", "info");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      ctx.ui.notify(`Failed to init mem0 bridge: ${msg}`, "warning");
    }
  });

  // 会话结束时关闭 MCP server 进程
  pi.on("session_shutdown", async (_event, _ctx) => {
    try {
      await client?.close();
    } catch {
      /* ignore */
    }
    client = null;
    transport = null;
    connected = false;
  });
}

import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const python = process.env.MEM0_VENV_PYTHON || join(projectRoot, "mem0_server", "venv", "bin", "python");
const wrapper = join(projectRoot, "extensions", "memory", "debug", "dbg_wrapper.py");
const transport = new StdioClientTransport({
  command: python,
  args: [wrapper],
  env: { ...process.env, LM_URL: process.env.LM_URL || "http://localhost:1234/v1" },
});
const client = new Client({ name: "tester", version: "1.0" });
await client.connect(transport);
try { const r = await client.callTool({ name: "memory_add", arguments: { messages: "DBG-ARGS" } }); console.log("RESULT:", JSON.stringify(r).slice(0,120)); } catch(e){ console.log("ERR:", String(e?.message||e).slice(0,140)); }
process.exit(0);

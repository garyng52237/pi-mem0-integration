# pi-mem0-integration

<p align="center">
  <a href="README_CN.md">中文</a> ·
  <a href="README.md">English</a>
</p>

A **mem0** memory backend for local LLMs (UnSloth / LM Studio), exposed as a standard **MCP (Model Context Protocol)** server so [pi](https://github.com/anthropics/pi) — or any MCP client — can read and write memories.

---

## Table of contents

- [Overview](#overview)
- [Why](#why)
- [Architecture](#architecture)
- [MCP tools](#mcp-tools)
- [Prerequisites](#prerequisites) ⚠️
- [Installation](#installation)
- [Usage](#usage)
- [Environment variables](#environment-variables)
- [Deployment](#deployment)
- [Local verification](#local-verification)
- [Implementation notes](#implementation-notes)
- [Repository layout](#repository-layout)
- [Dependencies](#dependencies)
- [License](#license)

---

## Overview

`mem0_mcp_server.py` wraps the [mem0](https://github.com/mem0ai/mem0) SDK and exposes six memory tools over the MCP protocol. The LLM and embedder share one local backend (UnSloth replacing the old LM Studio), so both run on the same model.

## Why

pi ships without long-term memory. This project wires [mem0](https://github.com/mem0ai/mem0) into pi to add it:

- Facts, preferences, and context generated in a conversation are extracted and persisted automatically.
- Related memories are recalled later via vector search.
- Memories are exposed as MCP tools, callable by any MCP client (including pi).

## Architecture

```
pi / pi-forge  (MCP client)          ← install your own pi-agent (see below)
   │  MCP stdio
   ▼
mem0_mcp_server.py  ── mem0 SDK ──►  Local backend (UnSloth / LM Studio)
                                      ├─ LLM: ornith-1.5-35b-a3b-apex-mtp-i-compact
                                      └─ Embedder: text-embedding-nomic-embed-text-v1.5
   ▼
Qdrant vector store (local, data/)
```

## MCP tools

`mem0_mcp_server.py` exposes six tools via FastMCP:

| Tool | Purpose |
| --- | --- |
| `memory_add` | Write / extract new memories |
| `memory_search` | Search the most relevant memories by query |
| `memory_update` | Update an existing memory |
| `memory_delete` | Delete a memory by id |
| `memory_get` | Fetch a single memory by id |
| `memory_reset` | Wipe all memories and the index |

## Prerequisites ⚠️

> **This repo is only the "memory backend." You must install pi-agent yourself.**
>
> This project only exposes mem0's memory capability over MCP. To actually run a
> memory-enabled pi, you need your own **pi-agent (the pi framework itself)** first,
> and then connect pi to this MCP server. This repo does **not** include pi-agent,
> and does not install or initialize pi for you.

See [Deployment](#deployment) for the full steps.

## Installation

```bash
cd pi_with_mem0
python -m venv venv
source venv/bin/activate
pip install mem0ai fastmcp
```

## Usage

### As an MCP server (stdio)

```bash
./pi_with_mem0/venv/bin/python mem0_mcp_server.py            # stdio
```

### As an HTTP server (optional)

```bash
OPENAI_API_KEY=sk-unsloth-xxxxxxxx ./pi_with_mem0/venv/bin/python mem0_mcp_server.py --http-port 8123
```

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `LM_URL` | `http://192.168.3.58:1234/v1` | UnSloth / LM Studio backend URL |
| `LM_API_KEY` | `sk-unsloth-xxxxxxxx` | Backend API key |
| `LLM_MODEL` | `ornith-1.5-35b-a3b-apex-mtp-i-compact` | Model used to extract memories |
| `EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | Embedder model |

## Deployment

1. **Install pi-agent first** (not provided by this repo).
   - Download and install your own pi-agent.
   - Make sure you have a working local backend (UnSloth or LM Studio);
     this repo defaults to `http://192.168.3.58:1234/v1`.

2. **Install this repo's dependencies** (see [Installation](#installation)).

3. **Connect the MCP service.**
   - Start the mem0 MCP server in stdio mode:
     ```bash
     ./pi_with_mem0/venv/bin/python mem0_mcp_server.py
     ```
   - Register the server in pi-agent's config (e.g. `mcp.json`) and inject
     `LM_URL` / `LM_API_KEY` as environment variables. pi can then use the memory tools.

4. **Verify.**
   - Run `./pi_with_mem0/venv/bin/python step2_mcp_end_to_end.py` to confirm end-to-end MCP works.

> Local inference is slow — connection and memory operations take tens of seconds each. Give the client a generous timeout.

## Local verification

```bash
# Step0 — environment / reachability self-check (venv / SDK / fastmcp / backend)
./pi_with_mem0/venv/bin/python step0_env_setup.py

# Step1 — run the local backend end to end (add → search → get)
OPENAI_API_KEY=lmstudio MEM0_TELEMETRY=false ./pi_with_mem0/venv/bin/python step1_local_test.py

# Step2 — end-to-end MCP verification
./pi_with_mem0/venv/bin/python step2_mcp_end_to_end.py
```

## Implementation notes

- **One shared model:** the LLM and embedder point at the same local backend; both must return results.
- **Response format:** UnSloth rejects mem0's default `{"type":"json_object"}` (400). Set the response format to `text` so the model returns plain-text JSON, parsed by mem0's built-in `extract_json` fallback.
- **Vector dimensions:** nomic embedder returns 384 dims — keep Qdrant's configured dimension in sync, or the dot product fails with a dimension mismatch.
- **Query robustness:** `memory_search` coerces `query` to a non-empty string and always attaches a `user_id` filter, so it won't fail on wrapped inputs (e.g. `{"query": "..."}`) or a missing filter.

## Repository layout

| File | Description |
| --- | --- |
| `step0_env_setup.py` | Environment setup & reachability self-check |
| `step1_local_test.py` | Run the local backend end to end (add → search → get) |
| `step2_mcp_end_to_end.py` | End-to-end MCP verification |
| `mem0_mcp_server.py` | Production MCP server exposing the memory tools |
| `CHANGE.log` | Development changelog |

## Dependencies

- `mem0ai` (local SDK at `../mem0/mem0`)
- `fastmcp` / `mcp` (MCP protocol)
- `uvicorn` (optional, HTTP mode)
- Local backend: UnSloth or LM Studio

## License

Personal project. All rights reserved.

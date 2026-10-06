#!/usr/bin/env bash
# 在独立 venv 中安装 mem0 MCP server 的 Python 依赖（见 requirements.txt）。
# 生成的 venv 位于本脚本所在目录： <项目根>/mem0_server/venv
#   （与 pi-mem0 wrapper 默认 VENV_PYTHON = <项目根>/mem0_server/venv/bin/python 一致）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/venv"
REQS="$HERE/requirements.txt"

echo "[setup] venv -> $VENV"
python3 -m venv "$VENV"

# 升级 pip 后安装依赖（本地无网时用已缓存 wheel；有网则正常拉取）
"$VENV/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/pip" install -r "$REQS"

echo "[setup] 安装完成。自检:"
"$VENV/bin/python" "$HERE/step0_env_setup.py"

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
server = PROJECT_ROOT / "mem0_server" / "mem0_mcp_server.py"
LM_URL = os.environ.get("LM_URL", "http://localhost:1234/v1")
p = subprocess.Popen([sys.executable, server], stdin=subprocess.PIPE, env={**os.environ, "LM_URL": LM_URL})
for line in sys.stdin:
    sys.stderr.write(f"[RAW-IN] {line.rstrip()}\n"); sys.stderr.flush()
    p.stdin.write(line.encode()); p.stdin.flush()
p.wait()

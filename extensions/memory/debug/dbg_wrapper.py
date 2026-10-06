import logging
import os
import subprocess as sp
import sys
from pathlib import Path

logging.getLogger("fastmcp").setLevel(logging.DEBUG)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
server = PROJECT_ROOT / "mem0_server" / "mem0_mcp_server.py"
LM_URL = os.environ.get("LM_URL", "http://localhost:1234/v1")
p = sp.Popen([sys.executable, server], stdin=sp.PIPE, env={**os.environ, "LM_URL": LM_URL})
for line in sys.stdin:
    p.stdin.write(line.encode()); p.stdin.flush()
p.wait()

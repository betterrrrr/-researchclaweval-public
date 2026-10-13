"""Give ACP session creation a realistic timeout.

Problem
-------
`ACPClient._ensure_session()` runs

    acpx --ttl 0 --cwd <cwd> codex sessions ensure --name <name>

with a hard-coded `timeout=30` (and the same again on the `sessions new`
fallback).  That 30 s budget is far tighter than every other timeout in this
client -- the per-prompt budget is `ACP_TIMEOUT_SEC`, defaulting to 7200 s --
yet it gates the whole run.

On this host the call is regularly slower than 30 s (codex cold start while
other codex sessions are active), and when it trips it is fatal for the stage:

    subprocess.TimeoutExpired: Command '['/opt/node/bin/acpx', '--ttl', '0',
      '--cwd', '/workspace', 'codex', 'sessions', 'ensure', '--name',
      'rc-...']' timed out after 30 seconds
    Stage 11/23 RESOURCE_PLANNING — FAILED (30.0s)

Observed twice in one evening: it killed the preflight of the first relaunch,
and later killed a whole run at Stage 11.

Fix
---
Read the budget from `ACP_SESSION_TIMEOUT_SEC`, defaulting to 180 s, in both
places.  Behaviour is unchanged when the variable is unset except for the
larger default; set `ACP_SESSION_TIMEOUT_SEC=<n>` to tune it.
"""
import ast
import sys
from pathlib import Path

TARGET = Path(
    sys.argv[1] if len(sys.argv) > 1
    else "/workspace/researchclaw/llm/acp_client.py"
)

MARKER = "ACP_SESSION_TIMEOUT_SEC"

OLD = """            errors="replace", timeout=30,
"""
NEW = """            errors="replace",
            # patched: was a hard-coded 30 s, which is far below the
            # per-prompt budget (ACP_TIMEOUT_SEC) and trips regularly on a
            # cold codex start, killing the stage.
            timeout=int(os.environ.get("ACP_SESSION_TIMEOUT_SEC") or 180),
"""

if not TARGET.exists():
    raise SystemExit(f"[acp-session-timeout] target not found: {TARGET}")

text = TARGET.read_text(encoding="utf-8")

if MARKER in text:
    print(f"[acp-session-timeout] already patched: {TARGET}")
    raise SystemExit(0)

count = text.count(OLD)
if count == 0:
    raise SystemExit("[acp-session-timeout] anchor not matched - source changed?")

text = text.replace(OLD, NEW)
TARGET.write_text(text, encoding="utf-8")

final = TARGET.read_text(encoding="utf-8")
ast.parse(final)
assert MARKER in final
assert 'timeout=30,' not in final, "a 30 s session timeout survived"
print(f"[acp-session-timeout] patched {TARGET}: {count} site(s), default 180 s")

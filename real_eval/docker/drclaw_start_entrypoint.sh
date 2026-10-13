#!/usr/bin/env bash
set -euo pipefail

SERVER_PORT="${PORT:-3001}"
PROJECT_NAME="${DRCLAW_PROJECT_NAME:-default-project}"
DRCLAW_MODEL="${DRCLAW_MODEL:-deepseek-v4-flash}"
DRCLAW_PROVIDER="${DRCLAW_PROVIDER:-openrouter}"
OUTPUT_DIR="${DRCLAW_OUTPUT_DIR:-/workspace/output}"
POLL_TIMEOUT="${DRCLAW_POLL_TIMEOUT:-7200}"
POLL_INTERVAL=30

cd /workspace/dr-claw

echo "[ENTRYPOINT] Patching openrouter.js MAX_AGENT_TURNS -> 300..."
python3 << 'PYEOF'
path = '/workspace/dr-claw/server/openrouter.js'
with open(path) as f:
    content = f.read()
content = content.replace('const MAX_AGENT_TURNS = 30;', 'const MAX_AGENT_TURNS = 300;')
with open(path, 'w') as f:
    f.write(content)
print('[ENTRYPOINT] Patched: MAX_AGENT_TURNS=300')
PYEOF

echo "[ENTRYPOINT] Patching openrouter.js fetch timeout -> 3600s (1h, covers long training)..."
python3 << 'PYEOF'
path = '/workspace/dr-claw/server/openrouter.js'
with open(path) as f:
    content = f.read()
old = '    signal,\n  });\n}'
new = '    signal: AbortSignal.any([signal, AbortSignal.timeout(3600000)]),\n  });\n}'
if old in content:
    content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print('[ENTRYPOINT] openrouter.js patched with 3600s fetch timeout')
else:
    print('[ENTRYPOINT] openrouter.js already patched or pattern not found')
PYEOF

echo "[ENTRYPOINT] Starting Dr. Claw server on port $SERVER_PORT..."
node server/cli.js start --port "$SERVER_PORT" &
SERVER_PID=$!

echo "[ENTRYPOINT] Waiting for server to be ready..."
for i in $(seq 1 60); do
  if curl -sf "http://localhost:$SERVER_PORT/api/auth/status" > /dev/null 2>&1; then
    echo "[ENTRYPOINT] Server is ready (attempt $i)"
    break
  fi
  if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "[ENTRYPOINT] ERROR: Server process died"; exit 1
  fi
  sleep 2
done

echo "[ENTRYPOINT] Registering user..."
curl -sf -X POST "http://localhost:$SERVER_PORT/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"researcher","password":"password123","notificationEmail":"researcher@test.com"}' > /dev/null 2>&1 || true

echo "[ENTRYPOINT] Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:$SERVER_PORT/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"researcher","password":"password123"}')
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null) || TOKEN=""
echo "[ENTRYPOINT] Token obtained: ${TOKEN:0:20}..."

PROJECT_DIR="/workspace/.claude/projects/$PROJECT_NAME"
mkdir -p "$PROJECT_DIR/.pipeline/docs" "$PROJECT_DIR/.pipeline/tasks"
echo '{"cwd":"'"$PROJECT_DIR"'","timestamp":"2026-09-03T12:00:00Z"}' > "$PROJECT_DIR/session.jsonl"
[ -f "/workspace/input/research_brief.json" ] && cp /workspace/input/research_brief.json "$PROJECT_DIR/.pipeline/docs/research_brief.json"
[ -f "/workspace/input/tasks.json" ] && cp /workspace/input/tasks.json "$PROJECT_DIR/.pipeline/tasks/tasks.json"
echo "[ENTRYPOINT] Project ready at $PROJECT_DIR"

echo "[ENTRYPOINT] Starting auto-research. Model: $DRCLAW_MODEL, Provider: $DRCLAW_PROVIDER"
START_RESPONSE=$(curl -s -X POST "http://localhost:$SERVER_PORT/api/auto-research/$PROJECT_NAME/start" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d "{\"provider\":\"$DRCLAW_PROVIDER\",\"model\":\"$DRCLAW_MODEL\",\"permissionMode\":\"bypassPermissions\"}")
echo "[ENTRYPOINT] Start response: $START_RESPONSE"

echo "[ENTRYPOINT] Polling for completion (timeout=${POLL_TIMEOUT}s)..."
POLL_START=$(date +%s)
STATUS_API="http://localhost:$SERVER_PORT/api/auto-research/$PROJECT_NAME/status"

while true; do
  sleep $POLL_INTERVAL
  NOW=$(date +%s)
  ELAPSED=$((NOW - POLL_START))

  if [ $ELAPSED -gt $POLL_TIMEOUT ]; then
    echo "[ENTRYPOINT] TIMEOUT: auto-research not finished in ${POLL_TIMEOUT}s"
    break
  fi

  STATUS_RESPONSE=$(curl -s "$STATUS_API" -H "Authorization: Bearer $TOKEN") || true
  ACTIVE_STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "
import sys,json
try:
    d = json.load(sys.stdin)
    s = d.get('activeRun',{})
    print(s.get('status','missing') if s else 'no_active')
except:
    print('parse_error')
" 2>/dev/null) || ACTIVE_STATUS="http_error"

  LATEST_STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "
import sys,json
try:
    d = json.load(sys.stdin)
    s = d.get('latestRun',{})
    print(s.get('status','') if s else '')
except:
    print('')
" 2>/dev/null) || LATEST_STATUS=""

  NO_ACTIVE_STREAK=0
  case "$ACTIVE_STATUS" in
    completed)
      echo "[ENTRYPOINT] Completed (${ELAPSED}s)"; break ;;
    failed|cancelled)
      echo "[ENTRYPOINT] Status: $ACTIVE_STATUS (${ELAPSED}s)"
      if [ "$LATEST_STATUS" = "completed" ]; then
        echo "[ENTRYPOINT] latestRun completed -- treating as success"; break
      fi
      break ;;
    running|queued)
      [ $((ELAPSED % 60)) -lt $POLL_INTERVAL ] && echo "[ENTRYPOINT] Status: $ACTIVE_STATUS (${ELAPSED}s)" ;;
    no_active|missing)
      NO_ACTIVE_STREAK=$((NO_ACTIVE_STREAK + 1))
      if [ "$LATEST_STATUS" = "completed" ]; then
        echo "[ENTRYPOINT] Active run ended, latestRun completed (${ELAPSED}s)"; break
      elif [ "$LATEST_STATUS" = "failed" ] || [ "$LATEST_STATUS" = "cancelled" ]; then
        echo "[ENTRYPOINT] latestRun=$LATEST_STATUS (${ELAPSED}s)"; break
      fi
      if [ $NO_ACTIVE_STREAK -ge 10 ]; then
        echo "[ENTRYPOINT] no_active for 5min, stopping (${ELAPSED}s)"; break
      fi
      [ $((ELAPSED % 60)) -lt $POLL_INTERVAL ] && echo "[ENTRYPOINT] Status: no_active (streak=${NO_ACTIVE_STREAK}, ${ELAPSED}s)" ;;
    *)
      [ $((ELAPSED % 120)) -lt $POLL_INTERVAL ] && echo "[ENTRYPOINT] Status: $ACTIVE_STATUS (${ELAPSED}s)" ;;
  esac

  if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "[ENTRYPOINT] Server died (${ELAPSED}s)"; break
  fi
done

echo "[ENTRYPOINT] Collecting artifacts..."
mkdir -p "$OUTPUT_DIR"

# Find all possible artifact locations
for src in \
  "$PROJECT_DIR/Ideation/ideas/research_idea.json" \
  "$PROJECT_DIR/Experiment/analysis/experiment_trace.json" \
  "$PROJECT_DIR/Experiment/core_code/research_idea.json" \
  "$PROJECT_DIR/Publication/paper/final_report.md" \
  "$PROJECT_DIR/.pipeline/docs/research_brief.json"; do
  if [ -f "$src" ]; then
    cp "$src" "$OUTPUT_DIR/$(basename "$src")" 2>/dev/null || true
    echo "  artifact: $src"
  fi
done

# Check common writable locations
for f in research_idea.json experiment_trace.json final_report.md; do
  for d in "/workspace/$f" "$PROJECT_DIR/$f" "$PROJECT_DIR/Experiment/$f" \
           "$PROJECT_DIR/Ideation/$f" "$PROJECT_DIR/Publication/$f"; do
    if [ -f "$d" ] && [ ! -f "$OUTPUT_DIR/$f" ]; then
      cp "$d" "$OUTPUT_DIR/$f" 2>/dev/null || true
      echo "  artifact: $d"
    fi
  done
done

echo "[ENTRYPOINT] Stopping server..."
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true
echo "[ENTRYPOINT] Done. Artifacts in $OUTPUT_DIR"
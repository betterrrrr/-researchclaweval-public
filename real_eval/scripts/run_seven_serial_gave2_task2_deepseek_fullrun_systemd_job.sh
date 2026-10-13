#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
SERIAL_RUNNER="$ROOT/real_eval/scripts/run_seven_serial_gave2_task2_deepseek_fullrun.sh"
LOG_FILE="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$RUN_ROOT/logs}/systemd-job.log"
STATE_FILE="$RUN_ROOT/state.json"

write_state() {
    local status="$1"
    python3 - "$STATE_FILE" "$RUN_ID" "$status" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
state = {
    "run_id": sys.argv[2],
    "project_id": "gave2_task2",
    "phase": "fullrun",
    "status": sys.argv[3],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
}
Path(sys.argv[1]).write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

on_exit() {
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        write_state "finished"
    else
        write_state "failed"
    fi
}
trap on_exit EXIT

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$STATE_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

export REAL_EVAL_CONTINUE_ON_FAILURE=1
write_state "running"
echo "[systemd-job] Starting GAVE2 Task 2 DeepSeek fullrun: RUN_ID=$RUN_ID"
bash "$SERIAL_RUNNER"
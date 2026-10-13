#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$RUN_ROOT/systemd}"
LOG_FILE="$LOG_ROOT/run.log"
STATE_FILE="$LOG_ROOT/state.json"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_arc_wbe_2026_gpt_fullrun.sh}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_arc_wbe_2026_method_free_gpt_20260809_frameworks.json}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_arc_wbe_2026.sh}"

mkdir -p "$RUN_ROOT" "$LOG_ROOT"
write_state() {
  local status="$1"
  local exit_code="$2"
  python3 - "$STATE_FILE" "$status" "$exit_code" "$RUN_ID" "$RUN_ROOT" "$LOG_FILE" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

Path(sys.argv[1]).write_text(json.dumps({
    "project_id": "arc_wbe_2026",
    "phase": "fullrun",
    "status": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "run_id": sys.argv[4],
    "run_root": sys.argv[5],
    "log": sys.argv[6],
    "summary": "Seven-framework native GPT ARC-WBE-2026 fullrun",
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
}, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}
on_exit() {
  local rc="$?"
  if [[ "$rc" -eq 0 ]]; then
    write_state finished "$rc"
  else
    write_state failed "$rc"
  fi
}
trap on_exit EXIT
exec > >(tee -a "$LOG_FILE") 2>&1

export RESEARCHCLAWEVAL_ROOT="$ROOT"
export REAL_EVAL_RUN_ID="$RUN_ID"
export REAL_EVAL_RUN_ROOT="$RUN_ROOT"
export REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG"
export REAL_EVAL_PREFLIGHT_SCRIPT="$PREFLIGHT_SCRIPT"
export REAL_EVAL_CONTINUE_ON_FAILURE=1

write_state running 0
printf 'SYSTEMD_JOB_START run_id=%s topic=arc_wbe_2026 mode=native_framework_orchestration time=%s\n' "$RUN_ID" "$(date -Is)"
bash "$SERIAL_RUNNER"

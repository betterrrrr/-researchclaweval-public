#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:?REAL_EVAL_SYSTEMD_LOG_ROOT is required}"
LOG_FILE="$LOG_ROOT/run.log"
STATE_FILE="$LOG_ROOT/state.json"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_fullrun.sh}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_tdc_admet_tox_gpt_fullrun_frameworks.json}"

mkdir -p "$BASE_RUN_ROOT" "$LOG_ROOT"
write_state() {
  local status="$1"
  local exit_code="$2"
  python3 - "$STATE_FILE" "$RUN_ID" "$status" "$exit_code" "$BASE_RUN_ROOT" "$LOG_FILE" "$SERIAL_RUNNER" "$FRAMEWORK_CONFIG" <<'PY'
from datetime import datetime, timezone
import json, sys
payload = {
    "project_id": "tdc_admet_tox",
    "run_id": sys.argv[2],
    "phase": "e2e",
    "status": sys.argv[3],
    "summary": "Topic 5 GPT native seven-framework systemd campaign",
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": int(sys.argv[4]),
    "run_root": sys.argv[5],
    "log": sys.argv[6],
    "serial_runner": sys.argv[7],
    "framework_config": sys.argv[8],
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=True, indent=2)
    handle.write("\n")
PY
}
on_exit() {
  local rc="$?"
  trap - EXIT
  if [[ "$rc" -eq 0 ]]; then
    write_state "finished" "$rc"
  else
    write_state "failed" "$rc"
  fi
  exit "$rc"
}
trap on_exit EXIT
exec > >(tee -a "$LOG_FILE") 2>&1

export RESEARCHCLAWEVAL_ROOT="$ROOT"
export REAL_EVAL_RUN_ID="$RUN_ID"
export REAL_EVAL_RUN_ROOT="$BASE_RUN_ROOT"
export REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG"
export REAL_EVAL_CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-1}"
write_state "running" 0
printf 'SYSTEMD_TOPIC5_GPT_NATIVE_START run_id=%s time=%s\n' "$RUN_ID" "$(date -Is)"
bash "$SERIAL_RUNNER"

#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-systemd-seven-gave2-task2-$(date +%Y%m%d-%H%M%S)}"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/$RUN_ID}"
LOG_FILE="$LOG_ROOT/run.log"
SUMMARY_FILE="$LOG_ROOT/summary.txt"
STATE_FILE="$LOG_ROOT/state.json"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_gave2_task2.sh}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_gave2_frameworks.json}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_gave2_task2.sh}"

mkdir -p "$BASE_RUN_ROOT" "$LOG_ROOT"

write_state() {
  local status="$1"
  local exit_code="$2"
  cat > "$STATE_FILE" <<EOF
{"run_id":"$RUN_ID","topic":"GAVE2 Task 2","status":"$status","exit_code":$exit_code,"run_root":"$BASE_RUN_ROOT","log":"$LOG_FILE","summary":"$SUMMARY_FILE","serial_runner":"$SERIAL_RUNNER","framework_config":"$FRAMEWORK_CONFIG"}
EOF
}

on_exit() {
  local rc="$?"
  if [[ "$rc" -eq 0 ]]; then
    write_state "finished" "$rc"
    printf 'SYSTEMD_JOB_FINISH run_id=%s rc=%s time=%s\n' "$RUN_ID" "$rc" "$(date -Is)" | tee -a "$SUMMARY_FILE"
  else
    write_state "failed" "$rc"
    printf 'SYSTEMD_JOB_FAIL run_id=%s rc=%s time=%s\n' "$RUN_ID" "$rc" "$(date -Is)" | tee -a "$SUMMARY_FILE"
  fi
}
trap on_exit EXIT

exec > >(tee -a "$LOG_FILE") 2>&1

export RESEARCHCLAWEVAL_ROOT="$ROOT"
export REAL_EVAL_RUN_ID="$RUN_ID"
export REAL_EVAL_RUN_ROOT="$BASE_RUN_ROOT"
export REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG"
export REAL_EVAL_PREFLIGHT_SCRIPT="$PREFLIGHT_SCRIPT"

write_state "running" 0
{
  printf 'SYSTEMD_JOB_START run_id=%s time=%s\n' "$RUN_ID" "$(date -Is)"
  printf 'TOPIC=%s\n' "GAVE2 Task 2"
  printf 'ROOT=%s\n' "$ROOT"
  printf 'RUN_ROOT=%s\n' "$BASE_RUN_ROOT"
  printf 'LOG_ROOT=%s\n' "$LOG_ROOT"
  printf 'SERIAL_RUNNER=%s\n' "$SERIAL_RUNNER"
  printf 'FRAMEWORK_CONFIG=%s\n' "$FRAMEWORK_CONFIG"
  printf 'PREFLIGHT_SCRIPT=%s\n' "$PREFLIGHT_SCRIPT"
  printf 'UNIT=%s\n' "${INVOCATION_ID:-unknown}"
} | tee -a "$SUMMARY_FILE"

if [[ "${REAL_EVAL_SYSTEMD_DRY_RUN:-0}" == "1" ]]; then
  test -x "$SERIAL_RUNNER"
  test -f "$FRAMEWORK_CONFIG"
  test -x "$PREFLIGHT_SCRIPT"
  printf 'DRY_RUN_WOULD_START %s\n' "$SERIAL_RUNNER" | tee -a "$SUMMARY_FILE"
  exit 0
fi

bash "$SERIAL_RUNNER"

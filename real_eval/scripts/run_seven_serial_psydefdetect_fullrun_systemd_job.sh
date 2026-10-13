#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-systemd-seven-psydefdetect-fullrun-$(date +%Y%m%d-%H%M%S)}"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/$RUN_ID}"
LOG_FILE="$LOG_ROOT/run.log"
SUMMARY_FILE="$LOG_ROOT/summary.txt"
STATE_FILE="$LOG_ROOT/state.json"
CHILD_SUMMARY="$LOG_ROOT/child_summary.md"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_fullrun.sh}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_gpt_fullrun_frameworks.json}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_psydefdetect.sh}"

mkdir -p "$BASE_RUN_ROOT" "$LOG_ROOT"
write_state() {
  local status="$1"; local exit_code="$2"
  cat > "$STATE_FILE" <<EOF
{"run_id":"$RUN_ID","topic":"PsyDefDetect full-run","status":"$status","exit_code":$exit_code,"run_root":"$BASE_RUN_ROOT","log":"$LOG_FILE","summary":"$SUMMARY_FILE","child_summary":"$CHILD_SUMMARY","serial_runner":"$SERIAL_RUNNER","framework_config":"$FRAMEWORK_CONFIG"}
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
  trap - EXIT
  exit "$rc"
}
trap on_exit EXIT
exec > >(tee -a "$LOG_FILE") 2>&1

export RESEARCHCLAWEVAL_ROOT="$ROOT"
export REAL_EVAL_RUN_ID="$RUN_ID"
export REAL_EVAL_RUN_ROOT="$BASE_RUN_ROOT"
export REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG"
export REAL_EVAL_PREFLIGHT_SCRIPT="$PREFLIGHT_SCRIPT"
export REAL_EVAL_CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-1}"

write_state "running" 0
{
  printf 'SYSTEMD_JOB_START run_id=%s time=%s\n' "$RUN_ID" "$(date -Is)"
  printf 'TOPIC=%s\n' 'PsyDefDetect full-run'
  printf 'RUN_ROOT=%s\n' "$BASE_RUN_ROOT"
  printf 'LOG_ROOT=%s\n' "$LOG_ROOT"
  printf 'SERIAL_RUNNER=%s\n' "$SERIAL_RUNNER"
  printf 'FRAMEWORK_CONFIG=%s\n' "$FRAMEWORK_CONFIG"
  printf 'PREFLIGHT_SCRIPT=%s\n' "$PREFLIGHT_SCRIPT"
} | tee -a "$SUMMARY_FILE"

cat > "$CHILD_SUMMARY" <<EOF
# PsyDefDetect full-run child summary

- what was submitted: seven-framework PsyDefDetect full-run serial pipeline.
- where run workspaces are: $BASE_RUN_ROOT
- where systemd logs are: $LOG_ROOT
- isolation model: fixed framework source copied into fresh per-framework run workspaces; Docker writable mount is the run workspace only.
- remaining runtime risk: success depends on PsyDefDetect dataset availability, Docker images, systemd --user, Codex/provider connectivity, and each framework's native execution path.
EOF

bash "$SERIAL_RUNNER"

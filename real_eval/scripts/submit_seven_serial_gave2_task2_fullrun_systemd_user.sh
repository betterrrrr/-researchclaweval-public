#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-systemd-seven-gave2-fullrun-$(date +%Y%m%d-%H%M%S)}"
UNIT_SAFE_RUN_ID="$(printf '%s' "$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-seven-gave2-fullrun-$UNIT_SAFE_RUN_ID}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/$RUN_ID}"
JOB="$ROOT/real_eval/scripts/run_seven_serial_gave2_task2_fullrun_systemd_job.sh"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_gave2_task2_fullrun.sh}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_gave2_fullrun_frameworks.json}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_gave2_task2_fullrun.sh}"
USER_UID="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

if [[ "$RUN_ID" == *babylm* ]] || [[ "$RUN_ROOT" == *babylm* ]] || [[ "$LOG_ROOT" == *babylm* ]]; then
  echo "refusing BabyLM-overlapping run identifiers or paths" >&2
  exit 9
fi
[[ -S "$XDG_RUNTIME_DIR/bus" ]] || { echo "systemd user bus missing: $XDG_RUNTIME_DIR/bus" >&2; exit 2; }
systemctl --user list-units >/dev/null 2>&1 || { echo "systemd --user is not running or not reachable" >&2; exit 3; }
[[ -x "$JOB" ]] || { echo "Job wrapper is not executable: $JOB" >&2; exit 4; }
[[ -x "$SERIAL_RUNNER" ]] || { echo "Serial runner is not executable: $SERIAL_RUNNER" >&2; exit 5; }
[[ -f "$FRAMEWORK_CONFIG" ]] || { echo "Framework config missing: $FRAMEWORK_CONFIG" >&2; exit 6; }
[[ -x "$PREFLIGHT_SCRIPT" ]] || { echo "Preflight script is not executable: $PREFLIGHT_SCRIPT" >&2; exit 7; }

mkdir -p "$RUN_ROOT" "$LOG_ROOT"
cat > "$LOG_ROOT/submission.json" <<EOF
{"run_id":"$RUN_ID","unit":"$UNIT.service","topic":"GAVE2 Task 2 full-run","run_root":"$RUN_ROOT","log_root":"$LOG_ROOT","serial_runner":"$SERIAL_RUNNER","framework_config":"$FRAMEWORK_CONFIG","submitted_at":"$(date -Is)"}
EOF

systemd-run --user \
  --unit "$UNIT" \
  --collect \
  --description "ResearchClawEval seven GAVE2 Task2 full-run $RUN_ID" \
  --property=WorkingDirectory="$ROOT" \
  --property=KillMode=control-group \
  --property=TimeoutStopSec=120 \
  --setenv=RESEARCHCLAWEVAL_ROOT="$ROOT" \
  --setenv=REAL_EVAL_RUN_ID="$RUN_ID" \
  --setenv=REAL_EVAL_RUN_ROOT="$RUN_ROOT" \
  --setenv=REAL_EVAL_SYSTEMD_LOG_ROOT="$LOG_ROOT" \
  --setenv=REAL_EVAL_SERIAL_RUNNER="$SERIAL_RUNNER" \
  --setenv=REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG" \
  --setenv=REAL_EVAL_PREFLIGHT_SCRIPT="$PREFLIGHT_SCRIPT" \
  --setenv=REAL_EVAL_CONTINUE_ON_FAILURE="1" \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  --setenv=DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  "$JOB"

cat <<EOF
UNIT=$UNIT.service
RUN_ID=$RUN_ID
RUN_ROOT=$RUN_ROOT
LOG_ROOT=$LOG_ROOT
LOG_FILE=$LOG_ROOT/run.log
STATE_FILE=$LOG_ROOT/state.json
CHILD_SUMMARY=$LOG_ROOT/child_summary.md
EOF

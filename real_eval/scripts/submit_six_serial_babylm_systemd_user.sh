#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-systemd-six-$(date +%Y%m%d-%H%M%S)}"
UNIT_SAFE_RUN_ID="$(printf '%s' "$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-six-babylm-$UNIT_SAFE_RUN_ID}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/$RUN_ID}"
JOB="$ROOT/real_eval/scripts/run_six_serial_babylm_systemd_job.sh"

if ! systemctl --user list-units >/dev/null 2>&1; then
  echo "systemd --user is not running or not reachable" >&2
  exit 2
fi

if [[ ! -x "$JOB" ]]; then
  echo "Job wrapper is not executable: $JOB" >&2
  exit 3
fi

mkdir -p "$RUN_ROOT" "$LOG_ROOT"

cat > "$LOG_ROOT/submission.json" <<EOF
{"run_id":"$RUN_ID","unit":"$UNIT.service","run_root":"$RUN_ROOT","log_root":"$LOG_ROOT","submitted_at":"$(date -Is)"}
EOF

systemd-run --user \
  --unit "$UNIT" \
  --collect \
  --description "ResearchClawEval six real BabyLM scripts serial run $RUN_ID" \
  --property=WorkingDirectory="$ROOT" \
  --property=KillMode=control-group \
  --property=TimeoutStopSec=120 \
  --setenv=RESEARCHCLAWEVAL_ROOT="$ROOT" \
  --setenv=REAL_EVAL_RUN_ID="$RUN_ID" \
  --setenv=REAL_EVAL_RUN_ROOT="$RUN_ROOT" \
  --setenv=REAL_EVAL_SYSTEMD_LOG_ROOT="$LOG_ROOT" \
  "$JOB"

cat <<EOF
UNIT=$UNIT.service
RUN_ID=$RUN_ID
RUN_ROOT=$RUN_ROOT
LOG_ROOT=$LOG_ROOT
LOG_FILE=$LOG_ROOT/run.log
STATE_FILE=$LOG_ROOT/state.json

Status:
  systemctl --user status $UNIT.service --no-pager

Journal:
  journalctl --user -u $UNIT.service -f

File log:
  tail -f $LOG_ROOT/run.log
EOF

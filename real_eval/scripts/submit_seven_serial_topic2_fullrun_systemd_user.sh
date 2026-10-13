#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-seven-mountaincar-continuous-fullrun-$(date +%Y%m%d-%H%M%S)}"
UNIT_SAFE_RUN_ID="$(printf '%s' "$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-seven-mountaincar-continuous-fullrun-$UNIT_SAFE_RUN_ID}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/$RUN_ID}"
JOB="$ROOT/real_eval/scripts/run_seven_serial_topic2_fullrun.sh"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_topic2_gpt_fullrun_frameworks.json}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_topic2.sh}"
TOPIC2_GPU_POLICY="${TOPIC2_GPU_POLICY:-require}"
TOPIC2_GPUS="${TOPIC2_GPUS:-all}"
REAL_EVAL_REQUIRE_GPU="${REAL_EVAL_REQUIRE_GPU:-0}"
TOPIC2_FRAMEWORK_TIMEOUT="${TOPIC2_FRAMEWORK_TIMEOUT:-7200}"
AI_RESEARCHER_MC_TIMEOUT_SECONDS="${AI_RESEARCHER_MC_TIMEOUT_SECONDS:-7200}"
TOPIC2_DATASET_ROOT="${TOPIC2_DATASET_ROOT:-$ROOT/data/topic2}"
TOPIC2_CONTRACT_FILE="${TOPIC2_CONTRACT_FILE:-$ROOT/automation/topic2_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
REAL_EVAL_FRAMEWORK_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-gpt-5.4}"
REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-gpt-5.4}"
TOPIC2_MODEL="${TOPIC2_MODEL:-gpt-5.4}"
USER_UID="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

for marker in babylm gave2 psydefdetect tdc_admet_tox arc_wbe; do
  [[ "${RUN_ID,,}" != *"$marker"* ]] || { echo "refusing cross-topic run id: $marker" >&2; exit 9; }
done
[[ -S "$XDG_RUNTIME_DIR/bus" ]] || { echo "systemd user bus missing" >&2; exit 2; }
systemctl --user list-units >/dev/null 2>&1 || { echo "systemd --user unavailable" >&2; exit 3; }
[[ -x "$JOB" ]] || { echo "serial runner not executable: $JOB" >&2; exit 4; }
[[ -f "$FRAMEWORK_CONFIG" ]] || { echo "framework config missing: $FRAMEWORK_CONFIG" >&2; exit 6; }

mkdir -p "$RUN_ROOT" "$LOG_ROOT"
cat > "$LOG_ROOT/submission.json" <<EOF
{"run_id":"$RUN_ID","unit":"$UNIT.service","topic":"MountainCar-Continuous full-run","run_root":"$RUN_ROOT","log_root":"$LOG_ROOT","serial_runner":"$JOB","framework_config":"$FRAMEWORK_CONFIG","submitted_at":"$(date -Is)"}
EOF

systemd-run --user \
  --unit "$UNIT" \
  --collect \
  --description "ResearchClawEval seven MountainCar-Continuous full-run $RUN_ID" \
  --property=WorkingDirectory="$ROOT" \
  --property=KillMode=control-group \
  --property=TimeoutStopSec=120 \
  --setenv=RESEARCHCLAWEVAL_ROOT="$ROOT" \
  --setenv=REAL_EVAL_RUN_ID="$RUN_ID" \
  --setenv=REAL_EVAL_RUN_ROOT="$RUN_ROOT" \
  --setenv=REAL_EVAL_SYSTEMD_LOG_ROOT="$LOG_ROOT" \
  --setenv=REAL_EVAL_SERIAL_RUNNER="$JOB" \
  --setenv=REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG" \
  --setenv=REAL_EVAL_PREFLIGHT_SCRIPT="$PREFLIGHT_SCRIPT" \
  --setenv=REAL_EVAL_CONTINUE_ON_FAILURE="1" \
  --setenv=TOPIC2_GPU_POLICY="$TOPIC2_GPU_POLICY" \
  --setenv=TOPIC2_GPUS="$TOPIC2_GPUS" \
  --setenv=REAL_EVAL_REQUIRE_GPU="$REAL_EVAL_REQUIRE_GPU" \
  --setenv=TOPIC2_FRAMEWORK_TIMEOUT="$TOPIC2_FRAMEWORK_TIMEOUT" \
  --setenv=AI_RESEARCHER_MC_TIMEOUT_SECONDS="$AI_RESEARCHER_MC_TIMEOUT_SECONDS" \
  --setenv=TOPIC2_DATASET_ROOT="$TOPIC2_DATASET_ROOT" \
  --setenv=TOPIC2_CONTRACT_FILE="$TOPIC2_CONTRACT_FILE" \
  --setenv=PROVIDER_CONFIG="$PROVIDER_CONFIG" \
  --setenv=REAL_EVAL_FRAMEWORK_MODEL="$REAL_EVAL_FRAMEWORK_MODEL" \
  --setenv=REAL_EVAL_MODEL="$REAL_EVAL_MODEL" \
  --setenv=TOPIC2_MODEL="$TOPIC2_MODEL" \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  --setenv=DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  "$JOB"

cat <<EOF
UNIT=$UNIT.service
RUN_ID=$RUN_ID
RUN_ROOT=$RUN_ROOT
LOG_ROOT=$LOG_ROOT
STATE_FILE=$LOG_ROOT/state.json
EOF

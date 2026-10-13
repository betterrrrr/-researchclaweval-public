#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-systemd-seven-psydefdetect-fullrun-$(date +%Y%m%d-%H%M%S)}"
UNIT_SAFE_RUN_ID="$(printf '%s' "$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-seven-psydefdetect-fullrun-$UNIT_SAFE_RUN_ID}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/$RUN_ID}"
JOB="$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_fullrun_systemd_job.sh"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_fullrun.sh}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_gpt_fullrun_frameworks.json}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_psydefdetect.sh}"
HOST_NODE_ROOT="${REAL_EVAL_HOST_NODE_ROOT:-$(dirname "$(dirname "$(command -v node)")")}" 
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
DATASET_ROOT="${PSYDEFDETECT_DATASET_ROOT:-$ROOT/data/psydefdetect}"
EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-$(sed -n 's/^[[:space:]]*model[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)}"
CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-0}"
USER_UID="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

[[ -S "$XDG_RUNTIME_DIR/bus" ]] || { echo "systemd user bus missing: $XDG_RUNTIME_DIR/bus" >&2; exit 2; }
systemctl --user list-units >/dev/null 2>&1 || { echo "systemd --user is not running or not reachable" >&2; exit 3; }
[[ -x "$JOB" ]] || { echo "Job wrapper is not executable: $JOB" >&2; exit 4; }
[[ -x "$SERIAL_RUNNER" ]] || { echo "Serial runner is not executable: $SERIAL_RUNNER" >&2; exit 5; }
[[ -f "$FRAMEWORK_CONFIG" ]] || { echo "Framework config missing: $FRAMEWORK_CONFIG" >&2; exit 6; }
[[ -f "$PROVIDER_CONFIG" && -f "$SEMANTIC_SOURCE" && -d "$DATASET_ROOT" ]] || { echo "PsyDefDetect provider, Semantic Scholar source, or dataset is missing" >&2; exit 6; }
[[ -x "$PREFLIGHT_SCRIPT" ]] || { echo "Preflight script is not executable: $PREFLIGHT_SCRIPT" >&2; exit 7; }
[[ -x "$HOST_NODE_ROOT/bin/codex" ]] || { echo "Host Codex CLI missing: $HOST_NODE_ROOT/bin/codex" >&2; exit 8; }

OPTIONAL_ENV_NAMES=(
  REAL_EVAL_FRAMEWORK_IDS
  REAL_EVAL_SKIP_PREFLIGHT
  RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT
  RESEARCHCLAWEVAL_ARIS_ROOT
  RESEARCHCLAWEVAL_AUTORESEARCHCLAW_ROOT
  RESEARCHCLAWEVAL_DRCLAW_ROOT
  RESEARCHCLAWEVAL_EVOSCIENTIST_ROOT
  AI_RESEARCHER_RUNTIME_IMAGE
  AI_RESEARCHER_EXEC_RUNTIME_IMAGE
  ARIS_RUNTIME_IMAGE
  AUTORESEARCHCLAW_RUNTIME_IMAGE
  DRCLAW_RUNTIME_IMAGE
  EVOSCIENTIST_RUNTIME_IMAGE
)
OPTIONAL_SETENV_ARGS=()
for env_name in "${OPTIONAL_ENV_NAMES[@]}"; do
  if [[ -v "$env_name" && -n "${!env_name}" ]]; then
    OPTIONAL_SETENV_ARGS+=(--setenv="$env_name=${!env_name}")
  fi
done

mkdir -p "$RUN_ROOT" "$LOG_ROOT"
cat > "$LOG_ROOT/submission.json" <<EOF
{"run_id":"$RUN_ID","unit":"$UNIT.service","topic":"PsyDefDetect full-run","run_root":"$RUN_ROOT","log_root":"$LOG_ROOT","serial_runner":"$SERIAL_RUNNER","framework_config":"$FRAMEWORK_CONFIG","submitted_at":"$(date -Is)"}
EOF

systemd-run --user \
  --unit "$UNIT" \
  --collect \
  --description "ResearchClawEval seven PsyDefDetect full-run $RUN_ID" \
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
  --setenv=REAL_EVAL_HOST_NODE_ROOT="$HOST_NODE_ROOT" \
  --setenv=PROVIDER_CONFIG="$PROVIDER_CONFIG" \
  --setenv=SEMANTIC_SOURCE="$SEMANTIC_SOURCE" \
  --setenv=PSYDEFDETECT_DATASET_ROOT="$DATASET_ROOT" \
  --setenv=PSYDEFDETECT_EVAL_MODEL="$EVAL_MODEL" \
  --setenv=REAL_EVAL_MODEL="$EVAL_MODEL" \
  --setenv=REAL_EVAL_CONTINUE_ON_FAILURE="$CONTINUE_ON_FAILURE" \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  --setenv=DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  "${OPTIONAL_SETENV_ARGS[@]}" \
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

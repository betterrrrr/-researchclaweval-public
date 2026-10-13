#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_tdc_admet_tox_gpt_fullrun_frameworks.json}"
EVAL_VARIANT="$(python3 - "$FRAMEWORK_CONFIG" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("evaluation_variant", "gpt"))
PY
)"
EVAL_MODEL="$(python3 - "$FRAMEWORK_CONFIG" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("model", "gpt-5.4"))
PY
)"
RUN_ID="${REAL_EVAL_RUN_ID:-topic5-tdc-admet-tox-${EVAL_VARIANT}-native-$(date +%Y%m%d-%H%M%S)}"
UNIT_SAFE_RUN_ID="$(printf '%s' "$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-topic5-${EVAL_VARIANT}-native-$UNIT_SAFE_RUN_ID}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/$RUN_ID}"
JOB="$ROOT/real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_fullrun_systemd_job.sh"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_fullrun.sh}"
DATASET_ROOT="${TDC_ADMET_TOX_DATASET_ROOT:-$ROOT/data/tdc_admet_tox/public}"
HIDDEN_LABELS_ROOT="${TDC_ADMET_TOX_HIDDEN_LABELS_ROOT:?TDC_ADMET_TOX_HIDDEN_LABELS_ROOT is required}"
SMOKE_GATE_ROOT="${TDC_ADMET_TOX_SMOKE_GATE_ROOT:?TDC_ADMET_TOX_SMOKE_GATE_ROOT is required}"
if [[ "$EVAL_VARIANT" == "ds" ]]; then
  PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_host.toml}"
else
  PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
fi
HOST_NODE_ROOT="${REAL_EVAL_HOST_NODE_ROOT:-$(dirname "$(dirname "$(command -v node)")")}" 
CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-1}"
USER_UID="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

[[ -S "$XDG_RUNTIME_DIR/bus" ]] || { echo "systemd user bus is unavailable" >&2; exit 2; }
systemctl --user list-units >/dev/null 2>&1 || { echo "systemd --user is unavailable" >&2; exit 3; }
for required in "$JOB" "$SERIAL_RUNNER"; do
  [[ -x "$required" ]] || { echo "required Topic 5 runner is not executable: $required" >&2; exit 4; }
done
[[ -f "$FRAMEWORK_CONFIG" && -f "$PROVIDER_CONFIG" && -d "$DATASET_ROOT" ]] || {
  echo "Topic 5 config, provider, or public dataset is missing" >&2
  exit 5
}
[[ -x "$HOST_NODE_ROOT/bin/codex" ]] || { echo "host Codex CLI is unavailable" >&2; exit 6; }

python3 "$ROOT/real_eval/scripts/preflight_seven_serial_tdc_admet_tox.py" \
  --root "$ROOT" \
  --config "$FRAMEWORK_CONFIG" \
  --mode fullrun \
  --dataset-root "$DATASET_ROOT" \
  --provider-config "$PROVIDER_CONFIG" \
  --hidden-labels-root "$HIDDEN_LABELS_ROOT" \
  --smoke-gate-root "$SMOKE_GATE_ROOT" >/dev/null

OPTIONAL_ENV_NAMES=(
  RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT
  RESEARCHCLAWEVAL_AI_SCIENTIST_V2_ROOT
  RESEARCHCLAWEVAL_ARIS_ROOT
  RESEARCHCLAWEVAL_AUTORESEARCHCLAW_ROOT
  RESEARCHCLAWEVAL_DEEPSCIENTIST_ROOT
  RESEARCHCLAWEVAL_DR_CLAW_ROOT
  RESEARCHCLAWEVAL_EVOSCIENTIST_ROOT
  AI_RESEARCHER_RUNTIME_IMAGE
  AI_SCIENTIST_V2_RUNTIME_IMAGE
  AUTORESEARCHCLAW_RUNTIME_IMAGE
  DEEPSCIENTIST_RUNTIME_IMAGE
  EVOSCIENTIST_RUNTIME_IMAGE
  TDC_ADMET_TOX_GPT_RELAY_IMAGE
  TDC_ADMET_TOX_FRAMEWORK_COOLDOWN_SECONDS
  TDC_ADMET_TOX_RUN_NOTE
)
OPTIONAL_SETENV_ARGS=()
for env_name in "${OPTIONAL_ENV_NAMES[@]}"; do
  if [[ -v "$env_name" && -n "${!env_name}" ]]; then
    OPTIONAL_SETENV_ARGS+=(--setenv="$env_name=${!env_name}")
  fi
done

mkdir -p "$RUN_ROOT" "$LOG_ROOT"
python3 - "$LOG_ROOT/submission.json" "$RUN_ID" "$UNIT.service" "$RUN_ROOT" "$LOG_ROOT" "$SERIAL_RUNNER" "$FRAMEWORK_CONFIG" "$EVAL_VARIANT" "$EVAL_MODEL" <<'PY'
from datetime import datetime, timezone
import json, sys
payload = {
    "project_id": "tdc_admet_tox",
    "evaluation_variant": sys.argv[8],
    "evaluation_model": sys.argv[9],
    "run_id": sys.argv[2],
    "unit": sys.argv[3],
    "run_root": sys.argv[4],
    "log_root": sys.argv[5],
    "serial_runner": sys.argv[6],
    "framework_config": sys.argv[7],
    "submitted_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "hidden_labels_projected": False,
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=True, indent=2)
    handle.write("\n")
PY

systemd-run --user \
  --unit "$UNIT" \
  --collect \
  --description "ResearchClawEval Topic 5 ${EVAL_VARIANT^^} native $RUN_ID" \
  --property=WorkingDirectory="$ROOT" \
  --property=KillMode=control-group \
  --property=TimeoutStopSec=120 \
  --setenv=RESEARCHCLAWEVAL_ROOT="$ROOT" \
  --setenv=REAL_EVAL_RUN_ID="$RUN_ID" \
  --setenv=REAL_EVAL_RUN_ROOT="$RUN_ROOT" \
  --setenv=REAL_EVAL_SYSTEMD_LOG_ROOT="$LOG_ROOT" \
  --setenv=REAL_EVAL_SERIAL_RUNNER="$SERIAL_RUNNER" \
  --setenv=REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG" \
  --setenv=REAL_EVAL_HOST_NODE_ROOT="$HOST_NODE_ROOT" \
  --setenv=PROVIDER_CONFIG="$PROVIDER_CONFIG" \
  --setenv=TDC_ADMET_TOX_DATASET_ROOT="$DATASET_ROOT" \
  --setenv=TDC_ADMET_TOX_HIDDEN_LABELS_ROOT="$HIDDEN_LABELS_ROOT" \
  --setenv=TDC_ADMET_TOX_SMOKE_GATE_ROOT="$SMOKE_GATE_ROOT" \
  --setenv=TDC_ADMET_TOX_EVAL_MODEL="$EVAL_MODEL" \
  --setenv=TDC_ADMET_TOX_EVAL_VARIANT="$EVAL_VARIANT" \
  --setenv=REAL_EVAL_CONTINUE_ON_FAILURE="$CONTINUE_ON_FAILURE" \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  --setenv=DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  "${OPTIONAL_SETENV_ARGS[@]}" \
  "$JOB"

printf 'UNIT=%s.service\nRUN_ID=%s\nRUN_ROOT=%s\nLOG_ROOT=%s\n' \
  "$UNIT" "$RUN_ID" "$RUN_ROOT" "$LOG_ROOT"

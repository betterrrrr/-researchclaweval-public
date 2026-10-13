#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:?REAL_EVAL_FRAMEWORK_CONFIG is required}"
CAMPAIGN_SPEC="${REAL_EVAL_CAMPAIGN_SPEC:?REAL_EVAL_CAMPAIGN_SPEC is required}"
UNIT_SAFE_RUN_ID="$(printf '%s' "$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-seven-gave2-deepseek-$UNIT_SAFE_RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$RUN_ROOT/systemd}"
JOB="$ROOT/real_eval/scripts/run_seven_serial_gave2_task2_deepseek_fullrun_systemd_job.sh"
SERIAL_RUNNER="$ROOT/real_eval/scripts/run_seven_serial_gave2_task2_deepseek_fullrun.sh"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
DATASET_ROOT="${GAVE2_DATASET_ROOT:-$ROOT/data/gave2/task2}"
CONTRACT_FILE="${GAVE2_CONTRACT_FILE:-$ROOT/automation/gave2_task2_contract.md}"
USER_UID="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

for marker in babylm arc_wbe psydefdetect tdc_admet_tox; do
  [[ "${RUN_ID,,}" != *"$marker"* && "${RUN_ROOT,,}" != *"$marker"* ]] || { echo "refusing cross-topic marker: $marker" >&2; exit 9; }
done
[[ "$RUN_ID" == *gave2* && "$RUN_ID" == *deepseek* ]] || { echo "run id must identify GAVE2 and DeepSeek" >&2; exit 10; }
[[ "$RUN_ROOT" == "$ROOT/real_eval/runs/"* ]] || { echo "run root must be under real_eval/runs" >&2; exit 11; }
[[ ! -e "$RUN_ROOT" ]] || { echo "fresh run root already exists: $RUN_ROOT" >&2; exit 12; }
[[ -S "$XDG_RUNTIME_DIR/bus" ]] || { echo "systemd user bus missing" >&2; exit 13; }
[[ -x "$JOB" && -x "$SERIAL_RUNNER" ]] || { echo "missing executable runtime helper" >&2; exit 14; }
[[ -f "$FRAMEWORK_CONFIG" && -f "$CAMPAIGN_SPEC" && -f "$PROVIDER_CONFIG" && -f "$SEMANTIC_SOURCE" && -f "$CONTRACT_FILE" && -d "$DATASET_ROOT" ]] || { echo "missing Topic 2 dispatch input" >&2; exit 15; }

mkdir -p "$RUN_ROOT" "$LOG_ROOT"
python3 "$ROOT/real_eval/scripts/validate_native_evaluation_spec.py" \
  --spec "$CAMPAIGN_SPEC" \
  --stage dispatch \
  --output "$RUN_ROOT/admission_report.json"
curl -fsS http://172.17.0.1:8788/healthz > "$RUN_ROOT/deepseek_relay_health.json"

python3 - "$LOG_ROOT/submission.json" "$RUN_ID" "$UNIT" "$RUN_ROOT" "$FRAMEWORK_CONFIG" "$CAMPAIGN_SPEC" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

Path(sys.argv[1]).write_text(json.dumps({
    "run_id": sys.argv[2],
    "unit": sys.argv[3] + ".service",
    "topic_id": "gave2_task2",
    "model": "deepseek-v4-flash",
    "mode": "native_framework_orchestration",
    "run_root": sys.argv[4],
    "framework_config": sys.argv[5],
    "campaign_spec": sys.argv[6],
    "submitted_at": datetime.now(timezone.utc).astimezone().isoformat(),
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

systemd-run --user \
  --unit "$UNIT" \
  --collect \
  --description "ResearchClawEval seven native GAVE2 DeepSeek fullrun $RUN_ID" \
  --property=WorkingDirectory="$ROOT" \
  --property=KillMode=control-group \
  --property=TimeoutStopSec=120 \
  --setenv=RESEARCHCLAWEVAL_ROOT="$ROOT" \
  --setenv=REAL_EVAL_RUN_ID="$RUN_ID" \
  --setenv=REAL_EVAL_RUN_ROOT="$RUN_ROOT" \
  --setenv=REAL_EVAL_SYSTEMD_LOG_ROOT="$LOG_ROOT" \
  --setenv=REAL_EVAL_SERIAL_RUNNER="$SERIAL_RUNNER" \
  --setenv=REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG" \
  --setenv=PROVIDER_CONFIG="$PROVIDER_CONFIG" \
  --setenv=SEMANTIC_SOURCE="$SEMANTIC_SOURCE" \
  --setenv=GAVE2_DATASET_ROOT="$DATASET_ROOT" \
  --setenv=GAVE2_CONTRACT_FILE="$CONTRACT_FILE" \
  --setenv=GAVE2_MODEL=deepseek-v4-flash \
  --setenv=REAL_EVAL_MODEL=deepseek-v4-flash \
  --setenv=REAL_EVAL_FRAMEWORK_MODEL=deepseek-v4-flash \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  --setenv=DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  "$JOB"

printf 'UNIT=%s.service\nRUN_ID=%s\nRUN_ROOT=%s\n' "$UNIT" "$RUN_ID" "$RUN_ROOT"
#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export RESEARCHCLAWEVAL_ROOT="$ROOT"
RUN_ID="${REAL_EVAL_RUN_ID:-topic3-arc-wbe-kimi-native-$(date +%Y%m%d-%H%M%S)}"
UNIT_SAFE_RUN_ID="$(printf '%s' "$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-seven-arc-wbe-native-$UNIT_SAFE_RUN_ID}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$RUN_ROOT/systemd}"
JOB="$ROOT/real_eval/scripts/run_seven_serial_arc_wbe_2026_kimi_fullrun_systemd_job.sh"
SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_arc_wbe_2026_kimi_fullrun.sh}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/arc_wbe_2026_kimi_fullrun_frameworks.json}"
CAMPAIGN_SPEC="${REAL_EVAL_CAMPAIGN_SPEC:?REAL_EVAL_CAMPAIGN_SPEC is required}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_arc_wbe_2026.sh}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
DATASET_ROOT="${ARC_WBE_2026_DATASET_ROOT:-$ROOT/data/arc_white_box_estimation_2026/baked/mini}"
WHEST_PYTHON="${ARC_WBE_2026_WHEST_PYTHON:-/tmp/whest-starterkit/.venv/bin/python}"
USER_UID="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_UID}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

[[ "$RUN_ID" != *gave2* && "$RUN_ID" != *psydefdetect* && "$RUN_ID" != *babylm* ]] || { echo "refusing cross-topic run id: $RUN_ID" >&2; exit 9; }
[[ "$RUN_ROOT" == "$ROOT/real_eval/runs/"* ]] || { echo "run root must be under real_eval/runs: $RUN_ROOT" >&2; exit 10; }
[[ -S "$XDG_RUNTIME_DIR/bus" ]] || { echo "systemd user bus missing: $XDG_RUNTIME_DIR/bus" >&2; exit 2; }
systemctl --user list-units >/dev/null 2>&1 || { echo "systemd --user is not reachable" >&2; exit 3; }
[[ -x "$JOB" && -x "$SERIAL_RUNNER" && -x "$PREFLIGHT_SCRIPT" ]] || { echo "ARC systemd helper is not executable" >&2; exit 4; }
[[ -f "$FRAMEWORK_CONFIG" && -f "$PROVIDER_CONFIG" && -f "$SEMANTIC_SOURCE" ]] || { echo "ARC runtime configuration is missing" >&2; exit 5; }
[[ -d "$DATASET_ROOT" && -x "$WHEST_PYTHON" ]] || { echo "ARC dataset or scorer Python is missing" >&2; exit 6; }
[[ -f "$CAMPAIGN_SPEC" ]] || { echo "Kimi campaign spec is missing: $CAMPAIGN_SPEC" >&2; exit 7; }

mkdir -p "$RUN_ROOT" "$LOG_ROOT"
python3 "$ROOT/real_eval/scripts/validate_native_evaluation_spec.py" \
  --spec "$CAMPAIGN_SPEC" \
  --stage dispatch \
  --output "$RUN_ROOT/admission_report.json"

python3 - "$LOG_ROOT/submission.json" "$RUN_ID" "$UNIT" "$RUN_ROOT" "$LOG_ROOT" "$FRAMEWORK_CONFIG" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

Path(sys.argv[1]).write_text(json.dumps({
    "run_id": sys.argv[2],
    "unit": sys.argv[3] + ".service",
    "topic": "ARC-WBE-2026",
    "mode": "native_framework_orchestration",
    "run_root": sys.argv[4],
    "log_root": sys.argv[5],
    "framework_config": sys.argv[6],
    "submitted_at": datetime.now(timezone.utc).astimezone().isoformat(),
}, ensure_ascii=False) + "\n", encoding="utf-8")
PY

systemd-run --user \
  --unit "$UNIT" \
  --collect \
  --description "ResearchClawEval seven native ARC-WBE Kimi fullrun $RUN_ID" \
  --property=WorkingDirectory="$ROOT" \
  --property=KillMode=control-group \
  --property=TimeoutStopSec=120 \
  --setenv=RESEARCHCLAWEVAL_ROOT="$ROOT" \
  --setenv=RESEARCHCLAWEVAL_FRAMEWORKS_ROOT="$ROOT" \
  --setenv=RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT="$ROOT/AI-Researcher" \
  --setenv=RESEARCHCLAWEVAL_AI_SCIENTIST_V2_ROOT="$ROOT/AI-Scientist-v2" \
  --setenv=RESEARCHCLAWEVAL_ARIS_ROOT="$ROOT/Auto-claude-code-research-in-sleep" \
  --setenv=RESEARCHCLAWEVAL_AUTORESEARCHCLAW_ROOT="$ROOT/AutoResearchClaw" \
  --setenv=RESEARCHCLAWEVAL_DEEPSCIENTIST_ROOT="$ROOT/DeepScientist" \
  --setenv=RESEARCHCLAWEVAL_DR_CLAW_ROOT="$ROOT/dr-claw" \
  --setenv=RESEARCHCLAWEVAL_EVOSCIENTIST_ROOT="$ROOT/EvoScientist" \
  --setenv=REAL_EVAL_RUN_ID="$RUN_ID" \
  --setenv=REAL_EVAL_RUN_ROOT="$RUN_ROOT" \
  --setenv=REAL_EVAL_SYSTEMD_LOG_ROOT="$LOG_ROOT" \
  --setenv=REAL_EVAL_SERIAL_RUNNER="$SERIAL_RUNNER" \
  --setenv=REAL_EVAL_FRAMEWORK_CONFIG="$FRAMEWORK_CONFIG" \
  --setenv=REAL_EVAL_CAMPAIGN_SPEC="$CAMPAIGN_SPEC" \
  --setenv=REAL_EVAL_PREFLIGHT_SCRIPT="$PREFLIGHT_SCRIPT" \
  --setenv=PROVIDER_CONFIG="$PROVIDER_CONFIG" \
  --setenv=SEMANTIC_SOURCE="$SEMANTIC_SOURCE" \
  --setenv=ARC_WBE_2026_DATASET_ROOT="$DATASET_ROOT" \
  --setenv=ARC_WBE_2026_WHEST_PYTHON="$WHEST_PYTHON" \
  --setenv=ARC_WBE_2026_MODEL=kimi-k2.6 \
  --setenv=REAL_EVAL_MODEL=kimi-k2.6 \
  --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  --setenv=DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  "$JOB"

printf 'UNIT=%s.service\nRUN_ID=%s\nRUN_ROOT=%s\nLOG_ROOT=%s\n' "$UNIT" "$RUN_ID" "$RUN_ROOT" "$LOG_ROOT"

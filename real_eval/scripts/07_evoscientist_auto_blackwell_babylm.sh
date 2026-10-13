#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/07_evoscientist_real_babylm}"
PHASE1_ROOT="$BASE/phase1"
PHASE2_ROOT="$BASE/phase2"
LOG_DIR="$BASE/logs"
PHASE1_SCRIPT="$ROOT/real_eval/scripts/07_evoscientist_real_babylm.sh"
PHASE2_SCRIPT="$ROOT/real_eval/scripts/07_evoscientist_continue_current_ngc_babylm.sh"

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$LOG_DIR"
cat > "$BASE/state.json" <<EOF
{"project_id":"07","name":"EvoScientist","run_id":"$RUN_ID","status":"starting_auto_blackwell","phase1_root":"$PHASE1_ROOT","phase2_root":"$PHASE2_ROOT"}
EOF

set +e
RESEARCHCLAWEVAL_ROOT="$ROOT" REAL_EVAL_RUN_ID="$RUN_ID" REAL_EVAL_RUN_ROOT="$PHASE1_ROOT" \
  bash "$PHASE1_SCRIPT" 2>&1 | tee "$LOG_DIR/phase1.log"
phase1_rc=${PIPESTATUS[0]}
set -e

if [[ ! -f "$PHASE1_ROOT/workspace/scripts/train_babylm.py" || ! -f "$PHASE1_ROOT/workspace/scripts/evaluate_babylm.py" ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_phase1_no_generated_scripts\",\"phase1_root\":\"$PHASE1_ROOT\",\"phase1_rc\":$phase1_rc,\"log\":\"$LOG_DIR/phase1.log\"}"
  exit 24
fi

set +e
RESEARCHCLAWEVAL_ROOT="$ROOT" REAL_EVAL_RUN_ID="$RUN_ID" REAL_EVAL_RUN_ROOT="$PHASE2_ROOT" EVOSCIENTIST_CURRENT_SOURCE_BASE="$PHASE1_ROOT" \
  bash "$PHASE2_SCRIPT" 2>&1 | tee "$LOG_DIR/phase2.log"
phase2_rc=${PIPESTATUS[0]}
set -e

real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"phase2_completed_candidate\",\"phase1_root\":\"$PHASE1_ROOT\",\"phase2_root\":\"$PHASE2_ROOT\",\"phase1_rc\":$phase1_rc,\"phase2_rc\":$phase2_rc,\"log\":\"$LOG_DIR/phase2.log\"}"

python3 "$ROOT/real_eval/scripts/validate_framework_run.py" \
  --framework evoscientist_auto \
  --run-root "$BASE" \
  --state-file "$BASE/state.json" \
  > "$LOG_DIR/validator.json"
validator_rc=$?

if [[ "$validator_rc" -eq 0 ]]; then
  exit 0
fi
if [[ "$phase2_rc" -ne 0 ]]; then
  exit "$phase2_rc"
fi
exit "$validator_rc"

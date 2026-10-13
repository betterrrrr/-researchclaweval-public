#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID must point at the existing run}"
export RESEARCHCLAWEVAL_ROOT="$ROOT"
export REAL_EVAL_RUN_ID="$RUN_ID"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"

scripts=(
  "$ROOT/real_eval/scripts/04_autoresearchclaw_resume_current_babylm.sh"
  "$ROOT/real_eval/scripts/05_deepscientist_real_babylm.sh"
  "$ROOT/real_eval/scripts/06_drclaw_real_babylm.sh"
  "$ROOT/real_eval/scripts/07_evoscientist_real_babylm.sh"
)

run_roots=(
  "$BASE_RUN_ROOT/04_autoresearchclaw_real_babylm"
  "$BASE_RUN_ROOT/05_deepscientist_real_babylm"
  "$BASE_RUN_ROOT/06_drclaw_real_babylm"
  "$BASE_RUN_ROOT/07_evoscientist_real_babylm"
)

mkdir -p "$BASE_RUN_ROOT"
for idx in "${!scripts[@]}"; do
  script="${scripts[$idx]}"
  export REAL_EVAL_RUN_ROOT="${run_roots[$idx]}"
  echo "=== START $(basename "$script") RUN_ID=$RUN_ID RUN_ROOT=$REAL_EVAL_RUN_ROOT ==="
  bash "$script"
  echo "=== FINISH $(basename "$script") RUN_ID=$RUN_ID RUN_ROOT=$REAL_EVAL_RUN_ROOT ==="
done

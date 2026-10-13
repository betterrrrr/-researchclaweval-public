#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID must point at the existing run}"
export RESEARCHCLAWEVAL_ROOT="$ROOT"
export REAL_EVAL_RUN_ID="$RUN_ID"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"

script="$ROOT/real_eval/scripts/07_evoscientist_continue_current_ngc_babylm.sh"
target_name="${EVOSCIENTIST_NGC_CONTINUE_TARGET:-07_evoscientist_real_babylm_ngc_current_acceleratefix}"
export REAL_EVAL_RUN_ROOT="$BASE_RUN_ROOT/$target_name"
echo "=== START $(basename "$script") RUN_ID=$RUN_ID RUN_ROOT=$REAL_EVAL_RUN_ROOT ==="
bash "$script"
echo "=== FINISH $(basename "$script") RUN_ID=$RUN_ID RUN_ROOT=$REAL_EVAL_RUN_ROOT ==="

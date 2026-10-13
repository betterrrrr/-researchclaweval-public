#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-systemd-six-resume-repair4-20260604-125723}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/${RUN_ID}-from07-ngc-current-${STAMP}}"
UNIT="researchclaweval-six-babylm-from07-ngc-current-${STAMP}"

mkdir -p "$LOG_ROOT"

systemd-run --user \
  --unit "$UNIT" \
  --description "ResearchClawEval continue existing BabyLM serial run from EvoScientist current NGC runtime" \
  --setenv "RESEARCHCLAWEVAL_ROOT=$ROOT" \
  --setenv "REAL_EVAL_RUN_ID=$RUN_ID" \
  --setenv "REAL_EVAL_RUN_ROOT=$RUN_ROOT" \
  --setenv "REAL_EVAL_SYSTEMD_LOG_ROOT=$LOG_ROOT" \
  --setenv "EVOSCIENTIST_NGC_CONTINUE_TARGET=${EVOSCIENTIST_NGC_CONTINUE_TARGET:-07_evoscientist_real_babylm_ngc_current_acceleratefix}" \
  --setenv "REAL_EVAL_SERIAL_RUNNER=$ROOT/real_eval/scripts/run_six_serial_babylm_resume_from_07_ngc_current.sh" \
  "$ROOT/real_eval/scripts/run_six_serial_babylm_systemd_job.sh"

echo "UNIT=$UNIT"
echo "RUN_ID=$RUN_ID"
echo "RUN_ROOT=$RUN_ROOT"
echo "LOG_ROOT=$LOG_ROOT"

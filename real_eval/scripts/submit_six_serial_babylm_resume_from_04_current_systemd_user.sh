#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${REAL_EVAL_RUN_ID:-systemd-six-resume-repair4-20260604-125723}"
RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_ROOT="${REAL_EVAL_SYSTEMD_LOG_ROOT:-$ROOT/real_eval/systemd_runs/${RUN_ID}-stage13-resume-${STAMP}}"
UNIT="researchclaweval-six-babylm-stage13-resume-${STAMP}"

mkdir -p "$LOG_ROOT"

systemd-run --user \
  --unit "$UNIT" \
  --description "ResearchClawEval resume existing BabyLM serial run from AutoResearchClaw Stage 13" \
  --setenv "RESEARCHCLAWEVAL_ROOT=$ROOT" \
  --setenv "REAL_EVAL_RUN_ID=$RUN_ID" \
  --setenv "REAL_EVAL_RUN_ROOT=$RUN_ROOT" \
  --setenv "REAL_EVAL_SYSTEMD_LOG_ROOT=$LOG_ROOT" \
  --setenv "REAL_EVAL_SERIAL_RUNNER=$ROOT/real_eval/scripts/run_six_serial_babylm_resume_from_04_current.sh" \
  "$ROOT/real_eval/scripts/run_six_serial_babylm_systemd_job.sh"

echo "UNIT=$UNIT"
echo "RUN_ID=$RUN_ID"
echo "RUN_ROOT=$RUN_ROOT"
echo "LOG_ROOT=$LOG_ROOT"

#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export REAL_EVAL_RUN_ID="${REAL_EVAL_RUN_ID:-topic4-psydefdetect-gpt56luna-native-$(date +%Y%m%d-%H%M%S)}"
export REAL_EVAL_SYSTEMD_UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-seven-psydefdetect-gpt56luna-native-$REAL_EVAL_RUN_ID}"
export REAL_EVAL_SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_gpt56luna_fullrun.sh}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_gpt56luna_fullrun_frameworks.json}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt56_luna_bianxie.toml}"
export PSYDEFDETECT_EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-gpt-5.6-luna}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$PSYDEFDETECT_EVAL_MODEL}"
exec "$ROOT/real_eval/scripts/submit_seven_serial_psydefdetect_fullrun_systemd_user.sh"
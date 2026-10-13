#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export REAL_EVAL_RUN_ID="${REAL_EVAL_RUN_ID:-topic4-psydefdetect-kimi-native-$(date +%Y%m%d-%H%M%S)}"
export REAL_EVAL_SYSTEMD_UNIT="${REAL_EVAL_SYSTEMD_UNIT:-researchclaweval-seven-psydefdetect-kimi-native-$REAL_EVAL_RUN_ID}"
export REAL_EVAL_SERIAL_RUNNER="${REAL_EVAL_SERIAL_RUNNER:-$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_kimi_fullrun.sh}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_method_free_kimi_20260805_frameworks.json}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
export PSYDEFDETECT_EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-kimi-k2.6}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$PSYDEFDETECT_EVAL_MODEL}"
exec "$ROOT/real_eval/scripts/submit_seven_serial_psydefdetect_fullrun_systemd_user.sh"

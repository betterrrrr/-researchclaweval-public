#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export DEEPSEEK_RELAY_PORT="${DEEPSEEK_RELAY_PORT:-8788}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
export PSYDEFDETECT_EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-deepseek-v4-flash}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$PSYDEFDETECT_EVAL_MODEL}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/psydefdetect_deepseek_recovery_0104_compile_freeze_20260804.json}"
exec "$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_deepseek_fullrun.sh"

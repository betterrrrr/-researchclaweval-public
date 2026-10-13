#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export DEEPSEEK_RELAY_PORT="${DEEPSEEK_RELAY_PORT:-8788}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_host.toml}"
export PSYDEFDETECT_EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-deepseek-v4-flash}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$PSYDEFDETECT_EVAL_MODEL}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/psydefdetect_deepseek_recovery_0104_contract_validation_20260804.json}"
export REAL_EVAL_SKIP_DEEPSEEK_RELAY_PREFLIGHT="${REAL_EVAL_SKIP_DEEPSEEK_RELAY_PREFLIGHT:-1}"
exec "$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_deepseek_fullrun.sh"

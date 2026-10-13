#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
export PSYDEFDETECT_EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-deepseek-v4-flash}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$PSYDEFDETECT_EVAL_MODEL}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_deepseek_smoke_frameworks.json}"
if [[ "${REAL_EVAL_DRY_RUN:-0}" != "1" && "${REAL_EVAL_SKIP_DEEPSEEK_RELAY_PREFLIGHT:-0}" != "1" ]]; then
  bash "$ROOT/real_eval/scripts/preflight_psydefdetect_deepseek_relay.sh"
fi
exec "$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_smoke.sh"

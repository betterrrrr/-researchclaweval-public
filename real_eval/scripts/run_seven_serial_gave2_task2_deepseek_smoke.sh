#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
export GAVE2_CONTRACT_FILE="${GAVE2_CONTRACT_FILE:-$ROOT/automation/gave2_task2_contract.md}"
export GAVE2_MODEL="${GAVE2_MODEL:-deepseek-v4-flash}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$GAVE2_MODEL}"
export REAL_EVAL_FRAMEWORK_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-$GAVE2_MODEL}"
exec "$ROOT/real_eval/scripts/run_seven_serial_gave2_smoke.sh"
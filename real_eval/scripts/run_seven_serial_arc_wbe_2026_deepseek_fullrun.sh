#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
export ARC_WBE_2026_CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_wbe_2026_contract.md}"
export ARC_WBE_2026_MODEL="${ARC_WBE_2026_MODEL:-deepseek-v4-flash}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$ARC_WBE_2026_MODEL}"
export REAL_EVAL_FRAMEWORK_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-$ARC_WBE_2026_MODEL}"
exec "$ROOT/real_eval/scripts/run_seven_serial_arc_wbe_2026_fullrun.sh"

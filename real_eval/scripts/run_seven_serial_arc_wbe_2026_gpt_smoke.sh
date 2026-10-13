#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
export ARC_WBE_2026_CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_white_box_estimation_2026_contract.md}"
export ARC_WBE_2026_MODEL="${ARC_WBE_2026_MODEL:-gpt-5.4}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$ARC_WBE_2026_MODEL}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_arc_wbe_2026_method_free_gpt_20260809_smoke_frameworks.json}"
exec "$ROOT/real_eval/scripts/run_seven_serial_arc_wbe_2026_smoke.sh"

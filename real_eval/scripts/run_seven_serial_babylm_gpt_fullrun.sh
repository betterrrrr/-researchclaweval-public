#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
export BABYLM_CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/automation/babylm_method_free_contract.md}"
export BABYLM_MODEL="${BABYLM_MODEL:-gpt-5.4}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$BABYLM_MODEL}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_babylm_gpt_method_free_20260810_frameworks.json}"
exec "$ROOT/real_eval/scripts/run_seven_serial_babylm.sh"
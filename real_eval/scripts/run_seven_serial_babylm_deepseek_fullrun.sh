#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
export BABYLM_CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"
export BABYLM_MODEL="${BABYLM_MODEL:-deepseek-v4-flash}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$BABYLM_MODEL}"
export REAL_EVAL_FRAMEWORK_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-$BABYLM_MODEL}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_babylm_method_free_deepseek_20260809_frameworks.json}"
exec "$ROOT/real_eval/scripts/run_seven_serial_babylm.sh"
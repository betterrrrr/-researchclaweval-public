#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
export PSYDEFDETECT_CONTRACT_FILE="${PSYDEFDETECT_CONTRACT_FILE:-$ROOT/automation/psydefdetect_contract.md}"
export PSYDEFDETECT_EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-kimi-k2.6}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$PSYDEFDETECT_EVAL_MODEL}"
export REAL_EVAL_SKIP_KIMI_RELAY_PREFLIGHT="${REAL_EVAL_SKIP_KIMI_RELAY_PREFLIGHT:-1}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_method_free_kimi_20260805_frameworks.json}"
if [[ "${REAL_EVAL_DRY_RUN:-0}" != "1" && "${REAL_EVAL_SKIP_KIMI_RELAY_PREFLIGHT:-0}" != "1" ]]; then
  bash "$ROOT/real_eval/scripts/preflight_psydefdetect_kimi_relay.sh"
fi
exec "$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_fullrun.sh"

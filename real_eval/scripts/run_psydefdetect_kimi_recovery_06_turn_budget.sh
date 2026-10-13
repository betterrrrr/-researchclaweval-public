#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export KIMI_RELAY_PORT="${KIMI_RELAY_PORT:-8787}"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
export PSYDEFDETECT_EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-kimi-k2.6}"
export REAL_EVAL_MODEL="${REAL_EVAL_MODEL:-$PSYDEFDETECT_EVAL_MODEL}"
export DRCLAW_MAX_AGENT_TURNS="${DRCLAW_MAX_AGENT_TURNS:-60}"
export REAL_EVAL_FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/psydefdetect_kimi_recovery_06_turn_budget_20260805.json}"
exec "$ROOT/real_eval/scripts/run_seven_serial_psydefdetect_kimi_fullrun.sh"

#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export BABYLM_MODEL="deepseek-v4-flash"
export PROVIDER_CONFIG="$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml"
exec "$ROOT/real_eval/scripts/02_ai_scientist_v2_babylm_gpt_fullrun.sh" "$@"
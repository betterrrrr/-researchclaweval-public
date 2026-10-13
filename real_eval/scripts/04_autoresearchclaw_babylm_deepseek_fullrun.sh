#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export BABYLM_MODEL="deepseek-v4-flash"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
export FRAMEWORK_SLUG="04_autoresearchclaw_babylm_deepseek_fullrun"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_BABYLM_DS_NATIVE"
exec "$ROOT/real_eval/scripts/04_autoresearchclaw_babylm_gpt_fullrun.sh" "$@"
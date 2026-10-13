#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export ARC_WBE_2026_MODEL="deepseek-v4-flash"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie.toml}"
export FRAMEWORK_SLUG="04_autoresearchclaw_arc_wbe_2026_deepseek_fullrun"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_ARC_DS_NATIVE"
exec "$ROOT/real_eval/scripts/04_autoresearchclaw_arc_wbe_2026_fullrun.sh" "$@"
#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export BABYLM_MODEL="gpt-5.6-luna"
export PROVIDER_CONFIG="$ROOT/api/codex_gpt56_luna_bianxie.toml"
export FRAMEWORK_SLUG="04_autoresearchclaw_babylm_luna_fullrun"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_BABYLM_LUNA_NATIVE"
exec "$ROOT/real_eval/scripts/04_autoresearchclaw_babylm_gpt_fullrun.sh" "$@"
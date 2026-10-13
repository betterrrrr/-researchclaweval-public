#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export BABYLM_MODEL="kimi-k2.6"
export PROVIDER_CONFIG="$ROOT/api/codex_kimi_k27_code_relay_container_fixed.toml"
export FRAMEWORK_SLUG="04_autoresearchclaw_babylm_kimi_fullrun"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_BABYLM_KIMI_NATIVE"
exec "$ROOT/real_eval/scripts/04_autoresearchclaw_babylm_gpt_fullrun.sh" "$@"

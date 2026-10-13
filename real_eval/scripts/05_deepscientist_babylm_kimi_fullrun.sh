#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export BABYLM_MODEL="kimi-k2.6"
export PROVIDER_CONFIG="$ROOT/api/codex_kimi_k27_code_relay_container.toml"
exec "$ROOT/real_eval/scripts/05_deepscientist_babylm_gpt_fullrun.sh" "$@"
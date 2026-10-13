#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_tdc_admet_tox_smoke"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 04)"
export FRAMEWORK_RUNTIME_IMAGE="autoresearchclaw:runtime-opencode"
export FRAMEWORK_NATIVE_ENTRYPOINT="python -m researchclaw.cli run"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="researchclaw/cli.py"
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_smoke.sh"

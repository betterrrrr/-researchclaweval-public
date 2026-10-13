#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_tdc_admet_tox_smoke"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 06)"
export FRAMEWORK_RUNTIME_IMAGE="dr-claw:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="node server/cli.js chat"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="server/cli.js"
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_smoke.sh"

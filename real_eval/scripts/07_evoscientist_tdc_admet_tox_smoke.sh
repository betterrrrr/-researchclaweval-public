#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_tdc_admet_tox_smoke"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 07)"
export FRAMEWORK_RUNTIME_IMAGE="evoscientist:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="evoscientist --use-cwd --auto-mode"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="EvoScientist/cli/__init__.py"
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_smoke.sh"

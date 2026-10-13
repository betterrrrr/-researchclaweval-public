#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_tdc_admet_tox_smoke"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 05)"
export FRAMEWORK_RUNTIME_IMAGE="deepscientist:tdc-runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="ds run run-experiment"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="src/deepscientist/cli.py"
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_smoke.sh"

#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_psydefdetect_smoke"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_EVOSCIENTIST_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 07)}"
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${EVOSCIENTIST_RUNTIME_IMAGE:-evoscientist:runtime-ready}"
export FRAMEWORK_RUNTIME_COMMAND="python --version"
export FRAMEWORK_ENTRYPOINT="bash"
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_smoke.sh

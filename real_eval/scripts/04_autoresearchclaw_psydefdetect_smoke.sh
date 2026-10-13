#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_psydefdetect_smoke"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_AUTORESEARCHCLAW_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 04)}"
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${AUTORESEARCHCLAW_RUNTIME_IMAGE:-autoresearchclaw:runtime-opencode}"
export FRAMEWORK_RUNTIME_COMMAND="python --version"
export FRAMEWORK_ENTRYPOINT="bash"
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_smoke.sh

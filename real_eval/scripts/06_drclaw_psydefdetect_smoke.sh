#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_psydefdetect_smoke"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_DRCLAW_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 06)}"
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${DRCLAW_RUNTIME_IMAGE:-dr-claw:runtime-ready}"
export FRAMEWORK_RUNTIME_COMMAND="python --version"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
EOF
)
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_smoke.sh

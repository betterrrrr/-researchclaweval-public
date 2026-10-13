#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_tdc_admet_tox_smoke"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 01)"
export FRAMEWORK_RUNTIME_IMAGE="ai-researcher:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="research_agent/run_infer_idea.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="research_agent/run_infer_idea.py"
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_smoke.sh"

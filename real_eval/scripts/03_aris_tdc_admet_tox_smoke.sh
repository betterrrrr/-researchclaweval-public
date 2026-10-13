#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_tdc_admet_tox_smoke"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_RUNTIME_IMAGE="aris:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="ARIS Codex-native /research-pipeline skill"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="skills/skills-codex/research-pipeline/SKILL.md"
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_smoke.sh"

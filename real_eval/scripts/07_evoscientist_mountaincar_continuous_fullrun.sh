#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_mountaincar_continuous_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 07)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
EvoScientist/EVOSCIENTIST_BRIEF.md
EvoScientist/mountaincar_continuous_start_message.txt
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="evoscientist:runtime-ready"
export FRAMEWORK_DISABLE_GPU="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="evoscientist --use-cwd --auto-mode"
export FRAMEWORK_KIMI_INJECTION="OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated provider"
export FRAMEWORK_NATIVE_LOG_MARKER="EVOSCIENTIST_NATIVE_CLI"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="evoscientist --use-cwd --auto-mode"
# NOTE: refine this per-framework native launch command during smoke testing.
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "EVOSCIENTIST_NATIVE_CLI"
# Run EvoScientist onboard if not already configured
/opt/venv/bin/evoscientist --use-cwd onboard --non-interactive --model "$OPENAI_MODEL" 2>&1 || true
# Run EvoScientist in auto mode with the topic
/opt/venv/bin/evoscientist --use-cwd --auto-mode -p @mountaincar_continuous_start_message.txt 2>&1
EOF
)
exec "$ROOT/real_eval/scripts/mountaincar_framework_fullrun.sh"

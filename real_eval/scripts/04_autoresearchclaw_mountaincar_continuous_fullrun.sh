#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_mountaincar_continuous_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 04)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AutoResearchClaw/topic.txt
AutoResearchClaw/config.arc.yaml
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="autoresearchclaw:runtime-ready"
export FRAMEWORK_DISABLE_GPU="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="python -m researchclaw.cli run"
export FRAMEWORK_KIMI_INJECTION="OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated provider"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_NATIVE_RUN"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python -m researchclaw.cli run"
# NOTE: refine this per-framework native launch command during smoke testing.
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AUTORESEARCHCLAW_NATIVE_RUN"
# Run AutoResearchClaw with sandbox mode (no Docker-in-Docker)
# Pre-validate API config
if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: OPENAI_API_KEY not set" >&2
  exit 1
fi
echo "Starting AutoResearchClaw with config.arc.yaml..."
python3 -m researchclaw.cli run --config config.arc.yaml --skip-preflight 2>&1 || {
  rc=$?
  echo "AutoResearchClaw exited with code $rc"
  # Even if AutoResearchClaw fails, check if checkpoints were produced
  ckpt_count=$(ls /workspace/checkpoints/*.pkl 2>/dev/null | wc -l)
  echo "Checkpoints found: $ckpt_count"
  exit $rc
}
EOF
)
exec "$ROOT/real_eval/scripts/mountaincar_framework_fullrun.sh"

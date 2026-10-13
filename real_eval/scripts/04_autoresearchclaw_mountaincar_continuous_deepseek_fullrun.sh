#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_mountaincar_continuous_deepseek"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie.toml}"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 04)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AutoResearchClaw/topic.txt
AutoResearchClaw/config.arc.yaml
real_eval/scripts/patch_autoresearchclaw_literature_screen.py
real_eval/scripts/patch_autoresearchclaw_framework.py
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${AUTORESEARCHCLAW_RUNTIME_IMAGE:-autoresearchclaw:runtime-opencode}"
export FRAMEWORK_NATIVE_ENTRYPOINT="python -m researchclaw.cli run"
export FRAMEWORK_REQUIRE_CODEX_HOME="1"
export FRAMEWORK_PROVIDER_INJECTION="config.arc.yaml uses OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
export FRAMEWORK_KIMI_INJECTION="$FRAMEWORK_PROVIDER_INJECTION"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_NATIVE_RUN"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python3 -m researchclaw.cli run --config AutoResearchClaw/config.arc.yaml --auto-approve"
export FRAMEWORK_DISABLE_GPU="${FRAMEWORK_DISABLE_GPU:-1}"
# CRITICAL: Set entrypoint to bash to avoid double bash -lc nesting
# (the image default entrypoint is already bash -lc)
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
ROOT="${ROOT:-/workspace}"
echo "AUTORESEARCHCLAW_NATIVE_RUN"
python3 real_eval/scripts/patch_autoresearchclaw_literature_screen.py 2>/dev/null || true
python3 real_eval/scripts/patch_autoresearchclaw_framework.py 2>/dev/null || true
topic="$(tr '\n' ' ' < AutoResearchClaw/topic.txt 2>/dev/null || echo 'MountainCar Continuous')"
# CRITICAL: Single-file requirement — LLMs often split code across missing modules
topic="$topic GENERATE ALL EXPERIMENT CODE IN A SINGLE main.py FILE. Do NOT split into config.py, data.py, methods.py, or other modules. Everything in one self-contained main.py. USE GPU: call .to(device) on EVERY tensor and model - not just the model, but also input data, observations, states, and targets. Example: observations = torch.tensor(obs).to(device). A RuntimeError 'Expected all tensors to be on the same device' means you forgot .to(device) somewhere.
Gymnasium API: env.step(action) returns 5 values: obs, reward, terminated, truncated, info. Do NOT unpack into 4 variables (obs, reward, done, info) — that will cause 'too many values to unpack'."
echo "Starting pipeline..."
timeout 28800s python3 -m researchclaw.cli run \
  --config AutoResearchClaw/config.arc.yaml \
  --topic "$topic" \
  --output "/workspace/artifacts/mountaincar-${REAL_EVAL_RUN_ID}" \
  --auto-approve \
  --skip-noncritical-stage
echo "Pipeline exited with code $?"
EOF
)
exec "$ROOT/real_eval/scripts/mountaincar_framework_fullrun.sh"
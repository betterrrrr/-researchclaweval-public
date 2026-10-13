#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="${ARIS_W15MCGPU_SLUG:-03_aris_mountaincar_continuous_gpu_fullrun}"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/TOPIC2_BRIEF.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="aris:runtime-ready"
export FRAMEWORK_DISABLE_GPU="0"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
-e
CUDA_VISIBLE_DEVICES=4,5,6,7
-v
${REAL_EVAL_PIPCACHE_DIR:-/tmp/rceval-pipcache}:/pipcache
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="ARIS /experiment-bridge official skill"
export FRAMEWORK_KIMI_INJECTION="OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated provider"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_NATIVE_EXPERIMENT_BRIDGE"
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL="ARIS /experiment-bridge official skill"
# NOTE: refine this per-framework native launch command during smoke testing.
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'

# 主题运行时预置：镜像 aris:runtime-ready 里没有 jax/flax/gymnax/optax，
# 而 MountainCar 的冻结 starter（src/train.py / networks.py）是 flax 的。
# 成功格（2026-08-19 ARIS kimi mc = 23.78）当时容器内是 jax 0.6.2 + 8 张 CudaDevice，
# 因此这里按同样版本预置；CUDA 版失败则回落到 CPU 版，保证框架至少有 jax 可用。
if ! python3 -c "import jax" >/dev/null 2>&1; then
  echo "ARIS_MC_PROVISION start"
  PIP_CACHE_DIR=/pipcache python3 -m pip install --quiet --disable-pip-version-check "jax[cuda12]==0.6.2" -i https://pypi.tuna.tsinghua.edu.cn/simple "flax==0.10.7" gymnax optax >/dev/null 2>&1 || \
  PIP_CACHE_DIR=/pipcache python3 -m pip install --quiet --disable-pip-version-check "jax==0.6.2" -i https://pypi.tuna.tsinghua.edu.cn/simple "flax==0.10.7" gymnax optax >/dev/null 2>&1 || echo "ARIS_MC_PROVISION_FAILED"
fi
python3 -c "import jax;print('ARIS_MC_JAX',jax.__version__,jax.devices())" 2>&1 | tail -1 || true
set -euo pipefail
echo "ARIS_NATIVE_EXPERIMENT_BRIDGE"
# Run ARIS native experiment-bridge skill against the TOPIC2_BRIEF.md
# The experiment-bridge skill is loaded from the ARIS skills directory and
# handles the full workflow: idea, experiments, checkpoints, and handoff.
# MOUNTAINCAR_CONTINUOUS_TRAINING_TIMEOUT is set to 1800s by the host.
# IMPORTANT: Save checkpoints DIRECTLY to /workspace/checkpoints/ as
# config-42-0.pkl ... config-42-4.pkl. Do NOT use subdirectories.
echo "Starting ARIS experiment-bridge workflow..."
if command -v codex &>/dev/null; then
  codex exec --yolo -C /workspace "/experiment-bridge TOPIC2_BRIEF.md"
elif command -v claude &>/dev/null; then
  claude -p "$(cat /workspace/TOPIC2_BRIEF.md)" -f /workspace
else
  echo "ERROR: No agent CLI (codex or claude) found" >&2
  exit 1
fi
EOF
)
exec "$ROOT/real_eval/scripts/mountaincar_framework_fullrun.sh"

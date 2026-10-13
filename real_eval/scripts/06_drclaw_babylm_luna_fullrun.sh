#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_babylm_luna_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 06)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="dr-claw:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="node server/cli.js chat --model gpt-5.6-luna"
export FRAMEWORK_PROVIDER_INJECTION="native framework client reads OPENAI_API_KEY from environment"
export FRAMEWORK_NATIVE_LOG_MARKER="DRCLAW_BABYLM_LUNA_NATIVE"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="node server/cli.js chat --model gpt-5.6-luna (non-interactive)"
export BABYLM_MODEL="gpt-5.6-luna"
export PROVIDER_CONFIG="$ROOT/api/codex_gpt56_luna_bianxie.toml"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
-e
DRCLAW_MAX_AGENT_TURNS=100
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "DRCLAW_BABYLM_LUNA_NATIVE"
mkdir -p /workspace/input /workspace/data
cp /input/babylm_contract.md /workspace/input/contract.md
# Dr. Claw blocks access to paths outside /workspace, so copy dataset inside
cp -r /data/BabyLM-2026-Strict-Small /workspace/data/
cat > /workspace/prompt.txt <<'PROMPT'
Run a BabyLM-10M end-to-end experiment using the mounted task contract and dataset at /workspace/data/BabyLM-2026-Strict-Small (only .txt files, no separate validation set -- split train/val yourself, do not silently catch file errors, verify non-empty). The framework must own idea formation, method selection, experiment design, execution, comparison, selection, analysis, and final artifact delivery. Write and lock research_idea.json before the first experiment. Run 2-4 materially different experiments, select by best WORD-LEVEL validation perplexity (character-level or subword-level is not accepted), and deliver research_idea.json, experiment_trace.json (strict JSON, no NaN, use experiments array with idea_artifact/idea_locked_before_experiments), and final_report.md to /workspace.
PROMPT
cat /workspace/prompt.txt - <<'INPUT' | node server/cli.js chat --model gpt-5.6-luna 2>&1
exit
INPUT
echo "DRCLAW_BABYLM_LUNA_NATIVE: Chat session ended"
for f in research_idea.json experiment_trace.json final_report.md; do
  if [ -f "/workspace/$f" ]; then
    echo "Found artifact: $f"
  fi
done
EOF
)
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
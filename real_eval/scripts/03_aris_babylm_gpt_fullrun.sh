#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_babylm_gpt_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="aris:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="ARIS /experiment-bridge official skill"
export FRAMEWORK_PROVIDER_INJECTION="ARIS documented Codex-native skill reads the isolated /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_BABYLM_GPT_NATIVE"
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL="ARIS /experiment-bridge on BabyLM"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "ARIS_BABYLM_GPT_NATIVE"
export CODEX_HOME="${CODEX_HOME:-/codex-home}"
export HOME="${HOME:-/workspace}"
cat > /workspace/RESEARCH_BRIEF.md <<'BRIEF'
# BabyLM-10M Method-Free Research Brief

Run the ARIS research pipeline on the real BabyLM-10M task.

- Contract file: /input/babylm_contract.md
- Dataset root: /data/BabyLM-2026-Strict-Small
- DATASET: contains ONLY .txt files (train files, no separate validation set). Filter by extension .txt. Split train/val yourself. Do NOT silently catch file-reading exceptions. Verify loaded data is non-empty.
- The framework must own idea formation, method selection, experiment design, execution, comparison, selection, analysis, and final artifact delivery.
- The host does not prescribe an algorithm, model architecture, hyperparameter, baseline, or experiment order.
- Required output: research_idea.json (before first experiment), experiment_trace.json, final_report.md
- Forbidden: proxy scripts, n-gram-only evaluation, previous experiment results, placeholder outputs
- IMPORTANT: Generated experiment code MUST be kept under 4000 characters total. Long code strings with special characters break JSON tool calls. Use concise variable names, avoid deeply nested loops, and keep the overall script compact.
BRIEF
cat > /workspace/AGENTS.md <<'AGENTS'
# ARIS BabyLM method-free run rules

Execute the installed ARIS research workflow for the BabyLM-10M brief. Use the mounted contract and dataset. The framework must write and lock research_idea.json before the first experiment. Run 2-4 materially different experiments, select by best validation perplexity, and deliver the final artifacts.
AGENTS
timeout 7200 codex exec --yolo -C /workspace "/experiment-bridge /workspace/RESEARCH_BRIEF.md -- compact: true, rescue_on_failure: false"
echo "ARIS_BABYLM_GPT_NATIVE_COMPLETE"
EOF
)
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
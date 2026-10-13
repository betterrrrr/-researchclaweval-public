#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_mountaincar_continuous_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 06)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
dr-claw/research_brief.json
dr-claw/tasks.json
docs/topic2_summary.md
automation/topic2_contract.md
automation/topic2_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
# Topic-2 needs jax/gymnax/flax/optax/tensorflow_probability; resolved
# unpinned in the base image they blow up at import (jax.interpreters.xla
# has no attribute pytype_aval_mappings).  This derived image pins the
# known-good set.  See .../tmp/mc-build/Dockerfile.
export FRAMEWORK_RUNTIME_IMAGE="dr-claw:runtime-ready-mountaincar"
export FRAMEWORK_DISABLE_GPU="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="node server/cli.js chat"
export FRAMEWORK_KIMI_INJECTION="OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated provider"
export FRAMEWORK_NATIVE_LOG_MARKER="DRCLAW_NATIVE_CHAT"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL='node server/cli.js chat --model $OPENAI_MODEL'
# NOTE: refine this per-framework native launch command during smoke testing.
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "DRCLAW_NATIVE_CHAT"
# Run Dr. Claw with memory-efficient Node.js settings
export NODE_OPTIONS="--max-old-space-size=8192"
export DRCLAW_MAX_AGENT_TURNS="${DRCLAW_MAX_AGENT_TURNS:-100}"
export DRCLAW_MAX_NO_TOOL_STREAK="${DRCLAW_MAX_NO_TOOL_STREAK:-10}"
prompt='Read dr-claw/research_brief.json, dr-claw/tasks.json, docs/topic2_summary.md, automation/topic2_contract.md, and automation/topic2_execution_budget.md. Execute the complete MountainCar-Continuous task through the native Dr. Claw planning and tool loop using only the injected evaluation provider. Before the first experiment write and lock research_idea.json as a top-level JSON object with non-empty hypothesis, method_rationale, expected_failure_modes, and comparison_logic. The framework owns the hypothesis, method choice, experiment design, comparison, and final selection; the host prescribes no algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence. Meet the contract Required Outputs: exactly five trained checkpoints under checkpoints/ matching the config stem (config-*.pkl), plus the config and all code the evaluator needs to reconstruct the model (src/), plus root-level research_idea.json, experiment_trace.json, and final_report.md. The host scores the five checkpoints with a frozen evaluator; fewer or more than five checkpoints means no score at all. Run 2-4 materially different experiments and record them in experiment_trace.json with framework_native_execution true, consumed_topic_input true, workspace_trace_root "/workspace", framework_internal_model, framework_internal_api_base_url, experiments (2-4 entries with id, configuration, validation metrics, logs), selected_experiment_id, idea_artifact exactly "research_idea.json", and idea_locked_before_experiments true. Do not write score.json: the host is its sole owner.'
echo "DRCLAW_STDIN_EOF_AFTER_ACTIVE_TURN"
cd /workspace && printf '%s\n' "$prompt" | timeout "${MOUNTAINCAR_CONTINUOUS_FRAMEWORK_TIMEOUT_SECONDS:-7200}s" node server/cli.js chat --model "$OPENAI_MODEL"
EOF
)
exec "$ROOT/real_eval/scripts/mountaincar_framework_fullrun.sh"

#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_topic2_fullrun"
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
export FRAMEWORK_RUNTIME_IMAGE="dr-claw:runtime-ready"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
-e
NODE_PATH=/opt/dr-claw/node_modules
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="node server/cli.js chat"
export FRAMEWORK_KIMI_INJECTION="Dr. Claw OpenAI-compatible client reads OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="DRCLAW_NATIVE_CHAT"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL='node server/cli.js chat --model $OPENAI_MODEL'
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "DRCLAW_NATIVE_CHAT"
export DRCLAW_MAX_AGENT_TURNS="${DRCLAW_MAX_AGENT_TURNS:-200}"
	# Patch the hard-coded 25-turn limit to 150 for slower models (kimi, etc.)
	sed -i 's/const MAX_AGENT_TURNS = 25;/const MAX_AGENT_TURNS = 200;/; s/configuredMaxAgentTurns <= 100/configuredMaxAgentTurns <= 200/' /workspace/server/cli-chat.js 2>/dev/null || true
prompt='Read the root-level research_brief.json, tasks.json, docs/topic2_summary.md, automation/topic2_contract.md, and automation/topic2_execution_budget.md. Execute the complete task through the native Dr. Claw planning and tool loop using only the injected evaluation provider. The workspace contains frozen starter code (src/train.py, src/policy.py, src/networks.py, src/helpers.py, src/config.yaml) and a read-only evaluator (evaluate.py). You may modify the starter code, add new code under src/, and run training experiments. Use only /workspace/src/config.yaml for the selected experiment; do not create root-level config_expA.yaml or any other config filename. The evaluator loads exactly src/config.yaml and globs checkpoints/config-42-*.pkl, so every checkpoint must be named config-42-0.pkl ... config-42-4.pkl. Use the official training entrypoint with --config_fname src/config.yaml; never use -config or any other config name. Run training in the background with a generous timeout and poll its log. Do not use web search, fetch, or any network tool because outbound web access is unreliable in this environment. The available Python environment has JAX, gymnax, flax, optax, and tensorflow_probability installed. Your objective is to improve the official Average Reward (Reward Mean) of MountainCarContinuous-v0 as much as possible.

CRITICAL: You MUST run 2-3 materially different experimental configurations. Do not stop after one experiment. Compare at least two approaches before selecting the best one.

Before the first experiment, write and lock research_idea.json. research_idea.json must be a top-level JSON object with non-empty hypothesis, method_rationale, expected_failure_modes, and comparison_logic fields. The framework owns the hypothesis, method choice, experiment design, comparison, and final selection; the host prescribes no algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence. Continue training until exactly five checkpoints exist at /workspace/checkpoints/config-42-0.pkl ... config-42-4.pkl. Write root-level research_idea.json, experiment_trace.json, and final_report.md. Additionally, deliver exactly 5 valid trained checkpoints under checkpoints/ plus config.yaml and src/ with all code. The frozen evaluator requires: assert len(checkpoint_files) == 5. Do not modify evaluate.py or the Model class name in networks.py. experiment_trace.json must record framework_native_execution true, consumed_topic_input true, workspace_trace_root "/workspace", framework_internal_model, framework_internal_api_base_url, experiments, selected_experiment_id, idea_artifact exactly "research_idea.json", and idea_locked_before_experiments true. Use only the injected evaluation provider and record framework_internal_model as the value of OPENAI_MODEL and framework_internal_api_base_url as the value of OPENAI_BASE_URL (never write localhost or another URL). The host creates score.json only after a successful frozen evaluator run.'
echo "DRCLAW_STDIN_EOF_AFTER_ACTIVE_TURN"
printf '%s\n' "$prompt" | timeout "${TOPIC2_FRAMEWORK_TIMEOUT:-7200}s" node server/cli.js chat --model "$OPENAI_MODEL"
EOF
)
exec "$ROOT/real_eval/scripts/topic2_framework_fullrun.sh"
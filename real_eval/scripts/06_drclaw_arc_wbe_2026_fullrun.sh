#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_arc_wbe_2026_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 06)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
dr-claw/research_brief.json
dr-claw/tasks.json
docs/arc_wbe_2026_summary.md
automation/arc_wbe_2026_contract.md
automation/arc_wbe_2026_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="dr-claw:runtime-ready-arc3"
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
export DRCLAW_MAX_AGENT_TURNS="${DRCLAW_MAX_AGENT_TURNS:-100}"
	export DRCLAW_MAX_NO_TOOL_STREAK="${DRCLAW_MAX_NO_TOOL_STREAK:-10}"
prompt='Read dr-claw/research_brief.json, dr-claw/tasks.json, docs/arc_wbe_2026_summary.md, automation/arc_wbe_2026_contract.md, and automation/arc_wbe_2026_execution_budget.md. Execute the complete task through the native Dr. Claw planning and tool loop using only the injected evaluation provider. The runtime image provides pyarrow, pandas, numpy, and flopscope 0.8.0rc5 in the system Python (/usr/local/bin/python3); if dependency availability is uncertain, verify it with a minimal import probe and record the result. Before the first experiment, write and lock research_idea.json. research_idea.json must be a top-level JSON object with non-empty hypothesis, method_rationale, expected_failure_modes, and comparison_logic fields. The framework owns the hypothesis, method choice, experiment design, comparison, and final selection; the host prescribes no algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence. The mounted /data/arc_wbe_2026 contains real weights-only parquet records; read them to design and validate a genuine estimator (the workspace sandbox blocks LS outside /workspace, but Read and Glob work on /data/arc_wbe_2026). Target labels are host-only by design: the challenge never provides them, none are needed, and their absence is not a blocker. Run 2-4 materially different framework-chosen experiments and write root-level research_idea.json, estimator.py, submission.json, experiment_trace.json, and final_report.md. The estimator.py must define BOTH (a) a factory function build_estimator() that returns the estimator object, and (b) the class it returns, whose predict must use the OFFICIAL signature predict(self, mlp, budget) -- two arguments, mlp AND budget -- returning a real (32, 256) fnp.ndarray dependent on mlp.weights; a final-layer-only (256,) output is invalid. The host scorer imports estimator.py, calls build_estimator(), and then calls predict(mlp, budget=budget) on the result; if build_estimator is absent the scorer finds no usable estimator and no score is produced, and if predict does not accept budget it is called with a single argument instead. Do not zero-fill, broadcast, or return a placeholder. Do not zero-fill, broadcast, synthesize, or use a placeholder; validate the estimator locally against the visible records with structural and consistency checks on its fnp output. The scorer sandbox has only flopscope.numpy (import as fnp) — do not import numpy, scipy, or torch. The host creates score.json only after a successful official adapter scorer run; your estimator.py must import flopscope.numpy as fnp exactly as the scorer does. experiment_trace.json must be a complete contract object recording framework_native_execution, consumed_topic_input true as a boolean, workspace_trace_root, framework_internal_model, framework_internal_api_base_url, experiments (2-4 entries with id, configuration, validation metrics, and logs), selected_experiment_id, idea_artifact exactly "research_idea.json", and idea_locked_before_experiments true. Do not access data outside /data/arc_wbe_2026 or write outside /workspace.'
echo "DRCLAW_STDIN_EOF_AFTER_ACTIVE_TURN"
printf '%s\n' "$prompt" | timeout "${ARC_WBE_2026_FRAMEWORK_TIMEOUT_SECONDS:-1800}s" node server/cli.js chat --model "$OPENAI_MODEL"
EOF
)
exec "$ROOT/real_eval/scripts/arc_framework_fullrun.sh"

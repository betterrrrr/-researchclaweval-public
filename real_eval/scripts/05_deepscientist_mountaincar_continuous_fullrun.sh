#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_mountaincar_continuous_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 05)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
DeepScientist/DEEPSCIENTIST_BRIEF.md
docs/topic2_summary.md
automation/topic2_contract.md
automation/topic2_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="deepscientist:runtime-ready"
export FRAMEWORK_DISABLE_GPU="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="ds init; ds new; ds run baseline; ds run idea; ds run experiment; ds run write"
export FRAMEWORK_KIMI_INJECTION="OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated provider"
export FRAMEWORK_NATIVE_LOG_MARKER="DEEPSCIENTIST_NATIVE_CODEX_RUNNER"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="ds --home /workspace/.deepscientist run baseline -> idea -> experiment -> write"
# NOTE: refine this per-framework native launch command during smoke testing.
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "DEEPSCIENTIST_NATIVE_CODEX_RUNNER"
# Ensure ds CLI is available
export PATH="${PATH}:$(npm bin -g 2>/dev/null || echo /usr/local/bin)"
DS_HOME=/workspace/.deepscientist
QUEST_ID=mountaincar-continuous

# The DeepScientist codex runner defaults to `config_dir: ~/.codex`, i.e.
# /workspace/.codex, which does not exist in this container.  The harness
# mounts the real provider config at $CODEX_HOME (=/codex-home), so without
# this rewrite `ds` launches codex with a nonexistent CODEX_HOME and the
# startup hello probe fails -- the whole run dies in ~10s.  Same fix the
# arc / psydefdetect / tdc wrappers already carry.
ds --home "$DS_HOME" init
sed -i 's#config_dir: ~/.codex#config_dir: /codex-home#' "$DS_HOME/config/runners.yaml"
grep -Fq 'config_dir: /codex-home' "$DS_HOME/config/runners.yaml"
ds --home "$DS_HOME" new "Execute the MountainCar-Continuous contract in /workspace through DeepScientist and produce the complete framework-owned handoff." --quest-id "$QUEST_ID"

# Stage 1: baseline
echo "DEEPSCIENTIST_STAGE_BASELINE"
timeout "${MOUNTAINCAR_BASELINE_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run baseline --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Read DEEPSCIENTIST_BRIEF.md, docs/topic2_summary.md, automation/topic2_contract.md, and automation/topic2_execution_budget.md. Establish a baseline understanding of the task and record the contract's Required Outputs."

# Stage 2: idea
echo "DEEPSCIENTIST_STAGE_IDEA"
timeout "${MOUNTAINCAR_IDEA_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run idea --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Propose 2-4 materially different hypotheses. The framework owns method choice. The host prescribes no algorithm, architecture, hyperparameters, or experiment order. Write research_idea.json."

# Stage 3: experiment
echo "DEEPSCIENTIST_STAGE_EXPERIMENT"
timeout "${MOUNTAINCAR_EXPERIMENT_TIMEOUT:-7200}s" \
  ds --home "$DS_HOME" run experiment --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Run 2-4 materially different experiments for MountainCar-Continuous. The framework owns method choice. Meet the contract's Required Outputs: exactly five trained checkpoints under checkpoints/ matching the config stem (config-*.pkl), plus src/config.yaml and the code the evaluator needs. Write research_idea.json, experiment_trace.json, and final_report.md. experiment_trace.json must record 2-4 experiment records, each with a unique non-empty experiment_id. experiment_trace.json must record framework_native_execution true, consumed_topic_input true, workspace_trace_root \"/workspace\", framework_internal_model, framework_internal_api_base_url, experiments, selected_experiment_id, idea_artifact exactly \"research_idea.json\", and idea_locked_before_experiments true."

# Stage 4: write
echo "DEEPSCIENTIST_STAGE_WRITE"
timeout "${MOUNTAINCAR_WRITE_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run write --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Write the final report for MountainCar-Continuous. Cover the hypothesis, method, experiment comparison, and results."
EOF
)
exec "$ROOT/real_eval/scripts/mountaincar_framework_fullrun.sh"

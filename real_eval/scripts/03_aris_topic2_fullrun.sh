#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_topic2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/TOPIC2_BRIEF.md
docs/topic2_summary.md
automation/topic2_contract.md
automation/topic2_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="aris:runtime-ready"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="ARIS /experiment-bridge skill"
export FRAMEWORK_KIMI_INJECTION="ARIS Codex executor reads the injected provider configuration at /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_NATIVE_EXPERIMENT_BRIDGE"
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL='codex exec --yolo -C /workspace "/experiment-bridge TOPIC2_BRIEF.md"'
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
test -f skills/skills-codex/experiment-bridge/SKILL.md
echo "ARIS_NATIVE_EXPERIMENT_BRIDGE"
timeout "${TOPIC2_FRAMEWORK_TIMEOUT:-7200}s"   codex exec --yolo --skip-git-repo-check -C /workspace   "/experiment-bridge TOPIC2_BRIEF.md. This is the official ARIS native skill workflow. Follow the injected MountainCar-Continuous contract and execution budget, and use only the injected evaluation provider. The workspace contains frozen starter code (src/train.py, src/policy.py, src/networks.py, src/helpers.py, src/config.yaml) and a read-only evaluator (evaluate.py). You may modify the starter code, add new code under src/, and run training experiments. Your objective is to improve the official Average Reward (Reward Mean) of MountainCarContinuous-v0 as much as possible within the available resource budget. Before the first experiment, write and lock research_idea.json. research_idea.json must be a top-level JSON object with non-empty hypothesis, method_rationale, expected_failure_modes, and comparison_logic fields. The framework owns the hypothesis, method choice, experiment design, comparison, and final selection; the host prescribes no algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence. Run 2-3 materially different framework-chosen experiments and promote root-level research_idea.json, experiment_trace.json, and final_report.md. Additionally, deliver exactly 5 valid trained checkpoints under checkpoints/ plus config.yaml and src/ with all code required to reconstruct the model. The frozen evaluator requires: assert len(checkpoint_files) == 5. Do not modify evaluate.py or the Model class name in networks.py. experiment_trace.json must record framework_native_execution true, consumed_topic_input true as a boolean, workspace_trace_root \"/workspace\", framework_internal_model, framework_internal_api_base_url, experiments, selected_experiment_id, idea_artifact exactly \"research_idea.json\", and idea_locked_before_experiments true. CRITICAL Kimi trace rule: set framework_internal_model to the exact value of the injected environment variable OPENAI_MODEL (currently \$OPENAI_MODEL) and framework_internal_api_base_url to the exact value of OPENAI_BASE_URL (currently \$OPENAI_BASE_URL). Never write gpt-5.5 or https://api.openai.com/v1. The host creates score.json only after a successful frozen evaluator run."
EOF
)
exec "$ROOT"/real_eval/scripts/topic2_framework_fullrun.sh
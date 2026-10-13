#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_arc_wbe_2026_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/ARC_WBE_2026_BRIEF.md
docs/arc_wbe_2026_summary.md
automation/arc_wbe_2026_contract.md
automation/arc_wbe_2026_execution_budget.md
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
export FRAMEWORK_COMMAND_LABEL='codex exec --yolo -C /workspace "/experiment-bridge ARC_WBE_2026_BRIEF.md"'
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
test -f skills/skills-codex/experiment-bridge/SKILL.md
echo "ARIS_NATIVE_EXPERIMENT_BRIDGE"
timeout "${ARC_WBE_2026_FRAMEWORK_TIMEOUT_SECONDS:-1800}s" \
  codex exec --yolo --skip-git-repo-check -C /workspace \
  "/experiment-bridge ARC_WBE_2026_BRIEF.md. This is the official ARIS native skill workflow. Follow the injected ARC contract and execution budget, and use only the injected evaluation provider. The mounted dataset contains real weights-only parquet records; use them for genuine estimator design and validation, while target labels remain host-only. Before the first experiment, write and lock research_idea.json. research_idea.json must be a top-level JSON object with non-empty hypothesis, method_rationale, expected_failure_modes, and comparison_logic fields. The framework owns the hypothesis, method choice, experiment design, comparison, and final selection; the host prescribes no algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence. Run 2-4 materially different framework-chosen experiments and promote root-level research_idea.json, estimator.py, submission.json, experiment_trace.json, and final_report.md. experiment_trace.json must record framework_native_execution true, consumed_topic_input true as a boolean, workspace_trace_root \"/workspace\", framework_internal_model, framework_internal_api_base_url, experiments, selected_experiment_id, idea_artifact exactly \"research_idea.json\", and idea_locked_before_experiments true. The estimator.py must have a predict(self, mlp) method that returns a real fnp.ndarray of shape (32, 256) dependent on mlp.weights; a final-layer-only (256,) output is invalid. Do not zero-fill, broadcast, synthesize, or use a placeholder; stop with a concrete blocker rather than fabricating. The host creates score.json only after a successful official adapter scorer run."
EOF
)
exec "$ROOT"/real_eval/scripts/arc_framework_fullrun.sh

#!/usr/bin/env bash
# ARIS x ARC-WBE-2026 — FULL PIPELINE variant (/research-pipeline).
#
# Counterpart of 03_aris_arc_wbe_2026_fullrun.sh, which invokes
# "ARIS /experiment-bridge skill" (workflow W1.5 only).  ARIS's main chain is
# /research-pipeline = W1 -> W1.5 -> W2 -> W3, so the W1.5-only runs are not
# comparable with frameworks invoked through their whole pipeline.
# New file: the W1.5 runs and their scores stay untouched.
#
# Identical to the W1.5 wrapper apart from the entrypoint, plus an explicit
# CUDA_VISIBLE_DEVICES pin (the W1.5 wrapper requested --gpus all, which would
# have reached GPUs 0-3).
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="${ARIS_ARCRETRY_SLUG:-03_aris_arc_wbe_2026_fullpipe_balanced_retry_fullrun}"
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
-e
CUDA_VISIBLE_DEVICES=4,5,6,7
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="install_aris_codex.sh -> /research-pipeline"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="tools/install_aris_codex.sh"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="skills/skills-codex/README.md"
export FRAMEWORK_KIMI_INJECTION="ARIS Codex executor reads the injected provider configuration at /codex-home/config.toml"
export FRAMEWORK_PROVIDER_INJECTION="ARIS's documented Codex-native skill host reads the minimal isolated /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_ARC_WBE"
export FRAMEWORK_NATIVE_PROCESS_MARKERS=$(cat <<'EOF'
NATIVE_CMD> bash tools/install_aris_codex.sh /workspace --quiet --no-doc
NATIVE_CMD> timeout 7000s codex exec --yolo --ephemeral --skip-git-repo-check
EOF
)
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL="bash tools/install_aris_codex.sh /workspace --quiet --no-doc; codex exec /research-pipeline"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_ARC_WBE"
test -f skills/skills-codex/research-pipeline/SKILL.md
rm -rf .aris .agents
PS4='NATIVE_CMD> '
set -x
bash tools/install_aris_codex.sh /workspace --quiet --no-doc
test -L .agents/skills/research-pipeline
grep -Fq $'skill\tresearch-pipeline\tskills/skills-codex/research-pipeline' .aris/installed-skills-codex.txt
cat > /workspace/arc_request.txt <<'PROMPT'
Invoke the installed official ARIS /research-pipeline skill as the research owner for the ARC White-Box Estimation Challenge 2026 topic. Run your own W1 -> W1.5 -> W2 -> W3 chain; do not stop after experiment bridging. Execute the ARC-WBE-2026 topic directly instead of falling back to another benchmark.

Follow the injected ARC contract and execution budget, and use only the injected evaluation provider. The mounted dataset contains real weights-only parquet records (mlp_id, mlp_name, mlp_seed, weights); use them for genuine estimator design and validation, while target labels remain host-only. The framework owns the hypothesis, method choice, experiment design, comparison, and final selection; the host prescribes no algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence.

DELIVERABLE CONTRACT (mandatory):
- Write and lock research_idea.json before the first experiment, as a top-level JSON object with non-empty hypothesis, method_rationale, expected_failure_modes and comparison_logic.
- Run 2-4 materially different framework-chosen experiments and promote root-level research_idea.json, estimator.py, submission.json, experiment_trace.json and final_report.md.
- estimator.py must be directly runnable by the supplied official scorer and must define a class named EXACTLY Estimator, exposing a predict(self, mlp) method that returns a real numpy array of shape (32, 256) of predicted per-layer activations, dependent on mlp.weights. Interface fact: the scorer's MLP object exposes .depth, .width and .weights, where .weights is a LIST of .depth matrices (each a (width, width) ndarray) - NOT a single 3-D array. Normalise it yourself (np.asarray on the list, or index it as a list) and take the output shape from mlp.depth/mlp.width instead of assuming a shape; an estimator that calls .shape directly on mlp.weights raises on every MLP and scores nothing. Runtime constraint: the official scorer executes estimator.py inside a minimal runtime that provides numpy and math (plus a compatibility shim for scipy.special). Do not import sklearn, torch, pandas, scipy (other than scipy.special through that shim), or any other heavy package at estimator.py import time - an estimator that does fails with ESTIMATOR_MISSING_MODULE before it can score at all. Keep estimator.py self-contained and bake any learned parameters into it as plain literals or embedded arrays at authoring time. The official adapter matches the literal class name Estimator; a class named anything else (e.g. MyEstimator, TreeBoostEstimator) is rejected by the adapter and yields no score, so do not rename it. A final-layer-only (256,) output is invalid. Do not predict a scalar score or class label.
- Do not zero-fill, broadcast, synthesize or use placeholder predictions; if a real estimator cannot be produced, stop with a concrete blocker rather than fabricating.
- experiment_trace.json must record framework_native_execution true, consumed_topic_input true as a boolean, workspace_trace_root "/workspace", framework_internal_model, framework_internal_api_base_url, experiments, selected_experiment_id, idea_artifact exactly "research_idea.json", and idea_locked_before_experiments true.
- The host creates score.json only after a successful official adapter scorer run; do not create it yourself.

The effective model and API base URL are injected as OPENAI_MODEL and OPENAI_BASE_URL; record their actual values in experiment_trace.json. CRITICAL Kimi trace rule: set framework_internal_model to the exact value of the injected environment variable OPENAI_MODEL and framework_internal_api_base_url to the exact value of OPENAI_BASE_URL. Never write gpt-5.5 or https://api.openai.com/v1.

Use effort: balanced, AUTO_PROCEED: true, CODE_REVIEW: false, AUTO_WRITE: false, RENDER_HTML: false, ARXIV_DOWNLOAD: false, HUMAN_CHECKPOINT: false. Keep ARIS state and trace evidence under .aris/.
PROMPT
run_codex_with_capacity_retry() {
  local max_attempts=8
  local attempt=1
  local sleep_seconds=180
  while :; do
    if timeout "${ARIS_FULLPIPE_CODEX_TIMEOUT_SECONDS:-7000}s" codex exec --yolo --ephemeral --skip-git-repo-check \
      -C /workspace \
      -o /workspace/arc_last_message.txt \
      - < /workspace/arc_request.txt 2>&1 | tee /tmp/aris_codex_attempt.log; then
      return 0
    fi
    # 429 是真实故障模式（kimi × paratera 多次因此死在 86 分钟处）：
    # 原逻辑只认 "at capacity"，429 一来直接判死。这里把它也纳入可重试集合。
    if ! grep -qiE "at capacity|exceeded retry limit|Too Many Requests|status: 429|429 Too Many|BadGatewayError|UPSTREAM_PROVIDER_ERROR" /tmp/aris_codex_attempt.log 2>/dev/null; then
      return 1
    fi
    echo "ARIS_CAPACITY_RETRY attempt ${attempt}/${max_attempts}, sleeping ${sleep_seconds}s"
    if [ "$attempt" -ge "$max_attempts" ]; then
      return 1
    fi
    sleep "$sleep_seconds"
    attempt=$((attempt + 1))
  done
}
run_codex_with_capacity_retry
test -s research_idea.json
test -s estimator.py
test -s experiment_trace.json
test -s final_report.md
EOF
)
exec "$ROOT"/real_eval/scripts/arc_framework_fullrun.sh

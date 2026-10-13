#!/usr/bin/env bash
# ARIS x MountainCarContinuous — FULL PIPELINE variant (/research-pipeline).
#
# Why this exists: the original 03_aris_mountaincar_continuous_fullrun.sh invokes
# the framework's native entrypoint "ARIS /experiment-bridge official skill",
# i.e. workflow W1.5 only.  ARIS's documented main chain is
#     /research-pipeline = W1 (idea) -> W1.5 (experiment bridge) -> W2 (auto
#     review) -> W3 (paper)
# so those runs are not comparable with frameworks that were invoked through
# their whole pipeline.  This wrapper is the full-pipeline counterpart; it is a
# new file so the W1.5 runs and their scores stay untouched.
#
# Everything except the entrypoint is deliberately identical to the W1.5
# wrapper: same entry paths, same brief, same deliverable contract, same
# GPU-disabled setting — so the only variable is pipeline granularity.
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="${ARIS_BALANCED_SLUG:-03_aris_mountaincar_continuous_fullpipe_balanced_fullrun}"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/TOPIC2_BRIEF.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="aris:runtime-ready"
# Same as the W1.5 run: this topic ran CPU-only (JAX/gymnax on CPU) and scored.
export FRAMEWORK_DISABLE_GPU="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="install_aris_codex.sh -> /research-pipeline"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="tools/install_aris_codex.sh"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="skills/skills-codex/README.md"
export FRAMEWORK_KIMI_INJECTION="OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated provider"
export FRAMEWORK_PROVIDER_INJECTION="ARIS's documented Codex-native skill host reads the minimal isolated /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_MOUNTAINCAR"
export FRAMEWORK_NATIVE_PROCESS_MARKERS=$(cat <<'EOF'
NATIVE_CMD> bash tools/install_aris_codex.sh /workspace --quiet --no-doc
NATIVE_CMD> timeout 7000s codex exec --yolo --ephemeral --skip-git-repo-check
EOF
)
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL="bash tools/install_aris_codex.sh /workspace --quiet --no-doc; codex exec /research-pipeline"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_MOUNTAINCAR"
test -f skills/skills-codex/research-pipeline/SKILL.md
rm -rf .aris .agents
PS4='NATIVE_CMD> '
set -x
bash tools/install_aris_codex.sh /workspace --quiet --no-doc
test -L .agents/skills/research-pipeline
grep -Fq $'skill\tresearch-pipeline\tskills/skills-codex/research-pipeline' .aris/installed-skills-codex.txt
cat > /workspace/mountaincar_request.txt <<'PROMPT'
Invoke the installed official ARIS /research-pipeline skill as the research owner for the MountainCarContinuous topic. Run your own W1 -> W1.5 -> W2 -> W3 chain; do not stop after experiment bridging.

The task contract is the mounted TOPIC2_BRIEF.md and automation/topic2_contract.md. The framework owns idea formation, method selection, experiment design, execution, comparison, selection, analysis, and final artifact delivery. The host prescribes no algorithm, architecture, hyperparameter, baseline, or experiment order.

MountainCarContinuous: run 2-4 materially different reinforcement-learning experiments on MountainCarContinuous-v0 and compare by validation reward.

DELIVERABLE CONTRACT (frozen evaluator — mandatory):
- The frozen evaluator loads EXACTLY five files named config-42-0.pkl ... config-42-4.pkl from /workspace/checkpoints/ and nothing else. Save them DIRECTLY there with exactly those names and the .pkl extension; no subdirectories; any other name or extension (e.g. SomeCondition_seed0.pt) is never read.
- config-42 means the single configuration in src/config.yaml: those five checkpoints must be that same configuration trained under seeds 0, 1, 2, 3, 4.
- Build the policy network with the frozen src/networks.py get_model_ready(rng, config) and train the Model it returns; do not define a substitute network. It returns (model, params) where model is a Flax linen module: forward is model.apply(params, observations, rng=rng). It is not a PyTorch module.
- Keep src/config.yaml in the starter nested schema, with train_config.network_config holding num_hidden_units and num_hidden_layers. Never replace it with a flat layout.
- Each checkpoint must be a pickle of a dict whose network key holds the trained parameter pytree, exactly as the starter src/train.py writes it.
- Do not modify evaluate.py or the Model class name.
- src/train.py already trains this Model with PPO and saves that dict; reusing or adapting it is the shortest correct route. Note src/train.py calls it with mle_log=None.

Also write root-level research_idea.json (locked before the first experiment), experiment_trace.json and final_report.md. experiment_trace.json must record framework_native_execution=true, consumed_topic_input=true, workspace_trace_root="/workspace", framework_internal_model, framework_internal_api_base_url, experiments (2-4 entries with unique experiment_id), selected_experiment_id, idea_artifact="research_idea.json", idea_locked_before_experiments=true. Do not create score.json.

The effective model and API base URL are injected as OPENAI_MODEL and OPENAI_BASE_URL; record their actual values in experiment_trace.json. CRITICAL Kimi trace rule: set framework_internal_model to the exact value of the injected environment variable OPENAI_MODEL and framework_internal_api_base_url to the exact value of OPENAI_BASE_URL. Never write gpt-5.5 or https://api.openai.com/v1.

Use effort: balanced, AUTO_PROCEED: true, CODE_REVIEW: false, AUTO_WRITE: false, RENDER_HTML: false, ARXIV_DOWNLOAD: false, HUMAN_CHECKPOINT: false. Keep ARIS state and trace evidence under .aris/.
PROMPT
run_codex_with_capacity_retry() {
  local max_attempts=6
  local attempt=1
  local sleep_seconds=90
  while :; do
    if timeout "${ARIS_FULLPIPE_CODEX_TIMEOUT_SECONDS:-7000}s" codex exec --yolo --ephemeral --skip-git-repo-check \
      -C /workspace \
      -o /workspace/mountaincar_last_message.txt \
      - < /workspace/mountaincar_request.txt; then
      return 0
    fi
    if ! grep -qi "at capacity" mountaincar_last_message.txt 2>/dev/null; then
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
test -s experiment_trace.json
test -s final_report.md
EOF
)
exec "$ROOT/real_eval/scripts/mountaincar_framework_fullrun.sh"

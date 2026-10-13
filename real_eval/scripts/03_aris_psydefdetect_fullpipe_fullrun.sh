#!/usr/bin/env bash
# ARIS x PsyDefDetect — FULL PIPELINE variant (/research-pipeline).
#
# Counterpart of 03_aris_psydefdetect_fullrun.sh, which invokes
# "ARIS /experiment-bridge skill" (workflow W1.5 only).  ARIS's main chain is
# /research-pipeline = W1 -> W1.5 -> W2 -> W3, so the W1.5-only runs are not
# comparable with frameworks invoked through their whole pipeline.
# New file: the W1.5 runs and their scores stay untouched.
#
# The W1.5 prompt's operational constraints (exactly two experiments, >=25
# evaluation records per request, <=40 remote requests, etc.) are reproduced
# verbatim on purpose, so the ONLY variable against the W1.5 run is pipeline
# granularity.
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="${ARIS_FULLPIPE_SLUG:-03_aris_psydefdetect_fullpipe_fullrun}"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_ARIS_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 03)}"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/PSYDEFDETECT_BRIEF.md
automation/psydefdetect_contract.md
automation/psydefdetect_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${ARIS_RUNTIME_IMAGE:-aris:runtime-ready}"
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
export FRAMEWORK_PROVIDER_INJECTION="ARIS's documented Codex-native skill host reads the minimal isolated /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_PSYDEFDETECT"
export FRAMEWORK_NATIVE_PROCESS_MARKERS=$(cat <<'EOF'
NATIVE_CMD> bash tools/install_aris_codex.sh /workspace --quiet --no-doc
NATIVE_CMD> timeout 7000s codex exec --yolo --ephemeral --skip-git-repo-check
EOF
)
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL="bash tools/install_aris_codex.sh /workspace --quiet --no-doc; codex exec /research-pipeline"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_PSYDEFDETECT"
test -f skills/skills-codex/research-pipeline/SKILL.md
rm -rf .aris .agents
PS4='NATIVE_CMD> '
set -x
bash tools/install_aris_codex.sh /workspace --quiet --no-doc
test -L .agents/skills/research-pipeline
grep -Fq $'skill\tresearch-pipeline\tskills/skills-codex/research-pipeline' .aris/installed-skills-codex.txt
cat > /workspace/psydef_request.txt <<'PROMPT'
Invoke the installed official ARIS /research-pipeline skill as the research owner for the PsyDefDetect topic. Run your own W1 -> W1.5 -> W2 -> W3 chain; do not stop after experiment bridging.

RESCUE_ON_FAILURE: false, AUTO_DEPLOY: true, BACKENDS: local, SANITY_FIRST: true, MAX_PARALLEL_RUNS: 1. This is the FULL pipeline, so /research-pipeline's own cross-model review stage (W2) is authorized and expected: do not disable it. Plan and execute exactly 2 materially different experiments, compare the fixed-split local scores, then immediately select and promote one result. Any API classification must batch at least 25 evaluation records per request and use no more than 40 remote requests total. Do not issue one request per record, run background jobs, use sleep/poll loops, install packages, or call any public provider. The injected evaluation provider IS authorized for the classification path and for the pipeline's review stage; the runtime brief's 'no remote experiment calls' line refers to public/third-party services, not to the injected provider. Keep only a compact experiment ledger in context. Never print or paste the full PsyDefConv dataset, prediction files, or generated source into the conversation; inspect schema and aggregate summaries only.

The framework itself must write root-level predictions.jsonl or submission.csv, score.json, experiment_trace.json, and final_report.md. experiment_trace.json must be one JSON object with exactly these fields: framework_native_execution set to true, consumed_topic_input set to true, workspace_trace_root set to /workspace, framework_internal_model set to the OPENAI_MODEL environment variable value, framework_internal_api_base_url set to the OPENAI_BASE_URL environment variable value, experiments as exactly 2 records, selected_experiment_id, prediction_artifact, and score_artifact. Write research_idea.json before experiment_trace.json so the idea file timestamp is earlier. Use only the injected evaluation provider configuration and the PsyDefDetect inputs.

Use effort: lite, AUTO_PROCEED: true, AUTO_WRITE: false, RENDER_HTML: false, ARXIV_DOWNLOAD: false, HUMAN_CHECKPOINT: false. Keep ARIS state and trace evidence under .aris/. CRITICAL Kimi trace rule: set framework_internal_model to the exact value of the injected environment variable OPENAI_MODEL and framework_internal_api_base_url to the exact value of OPENAI_BASE_URL. Never write gpt-5.5 or https://api.openai.com/v1.
PROMPT
run_codex_with_capacity_retry() {
  local max_attempts=6
  local attempt=1
  local sleep_seconds=90
  while :; do
    if timeout "${ARIS_FULLPIPE_CODEX_TIMEOUT_SECONDS:-7000}s" codex exec --yolo --ephemeral --skip-git-repo-check \
      -C /workspace \
      -o /workspace/psydef_last_message.txt \
      - < /workspace/psydef_request.txt; then
      return 0
    fi
    if ! grep -qi "at capacity" psydef_last_message.txt 2>/dev/null; then
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
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_fullrun.sh

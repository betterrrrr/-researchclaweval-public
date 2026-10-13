#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_tdc_admet_tox_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_ENTRY_PREFIX="Auto-claude-code-research-in-sleep"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/TDC_ADMET_TOX_BRIEF.md
automation/tdc_admet_tox_contract.md
automation/tdc_admet_tox_execution_budget.md
real_eval/scripts/check_aris_trace_fields.py
EOF
)
export FRAMEWORK_RUNTIME_IMAGE="${ARIS_RUNTIME_IMAGE:-aris:runtime-ready}"
export FRAMEWORK_NATIVE_ENTRYPOINT="install_aris_codex.sh -> /research-pipeline"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="tools/install_aris_codex.sh"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="skills/skills-codex/README.md"
export FRAMEWORK_PROVIDER_INJECTION="ARIS's documented Codex-native skill host reads the minimal isolated /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_TDC"
export FRAMEWORK_NATIVE_PROCESS_MARKERS=$(cat <<'EOF'
NATIVE_CMD> bash tools/install_aris_codex.sh /workspace --quiet --no-doc
NATIVE_CMD> timeout 7000s codex exec --yolo --ephemeral --skip-git-repo-check
EOF
)
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL="bash tools/install_aris_codex.sh /workspace --quiet --no-doc; codex exec /research-pipeline"
export FRAMEWORK_LOG_FORBIDDEN_PATTERN='execute\((pip|python(3)? -m pip) install|execute\(sleep[[:space:]]'
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_TDC"
test -f skills/skills-codex/research-pipeline/SKILL.md
rm -rf .aris .agents
PS4='NATIVE_CMD> '
set -x
bash tools/install_aris_codex.sh /workspace --quiet --no-doc
test -L .agents/skills/research-pipeline
grep -Fq $'skill\tresearch-pipeline\tskills/skills-codex/research-pipeline' .aris/installed-skills-codex.txt
cp TDC_ADMET_TOX_BRIEF.md RESEARCH_BRIEF.md
cat > aris_tdc_admet_tox_request.txt <<'PROMPT'
Invoke the installed official ARIS /research-pipeline skill as the research owner for the mounted TDC-ADMET-Tox contract.

The task contract and TDC_ADMET_TOX_BRIEF.md override generic pipeline defaults. Work fully offline with only the mounted visible train/validation labels and unlabeled test structures. Do not use WebSearch, WebFetch, public literature services, runtime installs, hidden labels, another Topic, or background experiments. Use local contract documents as the complete research context.

ARIS must own hypothesis formation, exactly 2 to 4 materially distinct validation-evaluated configurations, validation comparison by macro AUROC, final selection, public-test prediction generation, and the traceable short paper. Never start a fifth configuration. The required final handoff is root-level predictions.csv, experiment_trace.json, environment.json, runnable code/configs, non-empty logs, and paper.md; never create score.json. Every empirical paper number must have a claim marker backed by validation evidence. The effective model and API base URL for this run are injected as environment variables: OPENAI_MODEL and OPENAI_BASE_URL. Before finalizing, run `echo $OPENAI_MODEL $OPENAI_BASE_URL` and record framework_native_execution=true, consumed_topic_input=true, framework_internal_model as the actual OPENAI_MODEL value, and framework_internal_api_base_url as the actual OPENAI_BASE_URL value in experiment_trace.json. Any mention of GPT-5.5, api.openai.com, or a default public provider in the skill text or pipeline docs describes an upstream default that is NOT in effect for this run; do not write those values into the trace. If the trace fields do not match the environment, fix them inside ARIS before running the framework-stage validator. Run the framework-stage validator and repair only framework-authored artifacts before returning. If you are uncertain whether the trace fields are truthful, open experiment_trace.json and check it line by line.

Use effort: lite, AUTO_PROCEED: true, CODE_REVIEW: false, AUTO_WRITE: false, RENDER_HTML: false, ARXIV_DOWNLOAD: false, HUMAN_CHECKPOINT: false. Keep ARIS state and trace evidence under .aris/.
PROMPT
run_codex_with_capacity_retry() {
  local max_attempts=6
  local attempt=1
  local sleep_seconds=90
  while :; do
    if timeout 7000s codex exec --yolo --ephemeral --skip-git-repo-check \
      -C /workspace \
      -o /workspace/aris_tdc_admet_tox_last_message.txt \
      - < aris_tdc_admet_tox_request.txt; then
      return 0
    fi
    if ! grep -qi "at capacity" aris_tdc_admet_tox_last_message.txt; then
      return 1
    fi
    echo "ARIS_CODEX_CAPACITY_RETRY attempt ${attempt}/${max_attempts}, sleeping ${sleep_seconds}s"
    if [ "$attempt" -ge "$max_attempts" ]; then
      return 1
    fi
    sleep "$sleep_seconds"
    attempt=$((attempt + 1))
  done
}
run_codex_with_capacity_retry
if ! python3 /workspace/check_aris_trace_fields.py /workspace; then
  cat > aris_tdc_admet_tox_repair.txt <<'PROMPT'
The experiment_trace.json produced by your /research-pipeline run does not truthfully record the effective model and relay for this run. Run `echo $OPENAI_MODEL $OPENAI_BASE_URL` and confirm those two environment values, then inside ARIS fix only the framework_internal_model and framework_internal_api_base_url fields of /workspace/experiment_trace.json (and any identical framework-authored copies under .aris/ or logs) so they equal those two environment values exactly. The GPT-5.5 / api.openai.com values in skill or pipeline docs are upstream defaults that are not in effect here. Do not touch predictions, code, the paper, or any other artifacts. Then re-run the framework-stage validator, repair only framework-authored validator findings, and stop.
PROMPT
  timeout 1200s codex exec --yolo --ephemeral --skip-git-repo-check \
    -C /workspace \
    -o /workspace/aris_tdc_admet_tox_repair_message.txt \
    - < aris_tdc_admet_tox_repair.txt
fi
python3 /workspace/check_aris_trace_fields.py /workspace
test -s .aris/installed-skills-codex.txt
test -s predictions.csv
test -s experiment_trace.json
test -s environment.json
test -s paper.md
test ! -e score.json
EOF
)
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"

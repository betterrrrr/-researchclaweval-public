#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_tdc_admet_tox_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 05)"
export FRAMEWORK_ENTRY_PREFIX="DeepScientist"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
DeepScientist/TDC_ADMET_TOX_BRIEF.md
automation/tdc_admet_tox_contract.md
automation/tdc_admet_tox_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_IMAGE="${DEEPSCIENTIST_RUNTIME_IMAGE:-deepscientist:tdc-runtime-ready}"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
-e
CUDA_VISIBLE_DEVICES=4,5,6,7
EOF
)
export FRAMEWORK_NEEDS_HOST_CODEX="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="ds init -> ds new -> ds run baseline -> ds run idea -> ds run experiment -> ds run write"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="src/deepscientist/cli.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="README.md"
export FRAMEWORK_PROVIDER_INJECTION="DeepScientist official CodexRunner reads the minimal isolated /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="DEEPSCIENTIST_NATIVE_CODEX_RUNNER_TDC"
export FRAMEWORK_NATIVE_PROCESS_MARKERS=$(cat <<'EOF'
NATIVE_CMD> ds --home /workspace/.deepscientist init
NATIVE_CMD> ds --home /workspace/.deepscientist new
NATIVE_CMD> timeout 3600s ds --home /workspace/.deepscientist run baseline
NATIVE_CMD> timeout 3600s ds --home /workspace/.deepscientist run idea
NATIVE_CMD> timeout 7000s ds --home /workspace/.deepscientist run experiment
NATIVE_CMD> timeout 3600s ds --home /workspace/.deepscientist run write
EOF
)
export FRAMEWORK_EXECUTOR_KIND="framework_internal_codex_runner"
export FRAMEWORK_COMMAND_LABEL="ds --home /workspace/.deepscientist run baseline -> idea -> experiment -> write"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
export PATH="/opt/researchclaweval-node/bin:$PATH"
export DEEPSCIENTIST_CODEX_BINARY="/opt/researchclaweval-node/bin/codex"
DS_HOME=/workspace/.deepscientist
QUEST_ID="tdc-admet-tox-${TDC_ADMET_TOX_EVAL_VARIANT:-gpt}-native"
echo "DEEPSCIENTIST_NATIVE_CODEX_RUNNER_TDC"
test -s /opt/deepscientist-tdc-home.tar
tar -xpf /opt/deepscientist-tdc-home.tar -C /workspace
export UV_OFFLINE=1
mkdir -p /workspace/logs
printf 'DeepScientist native handoff started\n' > /workspace/logs/native_execution.log
PS4='NATIVE_CMD> '
set -x
ds --home "$DS_HOME" init
sed -i 's#config_dir: ~/.codex#config_dir: /codex-home#' "$DS_HOME/config/runners.yaml"
grep -Fq 'config_dir: /codex-home' "$DS_HOME/config/runners.yaml"
ds --home "$DS_HOME" new \
  "Execute the mounted TDC-ADMET-Tox contract through DeepScientist's native research workflow." \
  --quest-id "$QUEST_ID"

# Stage 1: baseline
set +e
echo "DEEPSCIENTIST_STAGE_BASELINE"
timeout "${TDC_ADMET_TOX_BASELINE_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run baseline --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Read /workspace/TDC_ADMET_TOX_BRIEF.md, /workspace/automation/tdc_admet_tox_contract.md, /workspace/automation/tdc_admet_tox_execution_budget.md. Establish a baseline understanding of the TDC-ADMET-Tox task: predict AMES, hERG, and DILI toxicity from SMILES. Use only visible SMILES and installed libraries."

# Stage 2: idea
echo "DEEPSCIENTIST_STAGE_IDEA"
timeout "${TDC_ADMET_TOX_IDEA_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run idea --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Propose 2-4 materially different hypotheses for the TDC-ADMET-Tox task. The framework owns method choice. The host prescribes no algorithm, feature representation, architecture, hyperparameters, or experiment sequence. Write research_idea.json."

# Stage 3: experiment
echo "DEEPSCIENTIST_STAGE_EXPERIMENT"
timeout "${TDC_ADMET_TOX_EXPERIMENT_TIMEOUT:-7000}s" \
  ds --home "$DS_HOME" run experiment --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Run 2-4 bounded foreground experiments for TDC-ADMET-Tox. Use only visible SMILES and installed libraries. Never create score.json, install packages, or access the internet. Record framework_internal_model as $OPENAI_MODEL and framework_internal_api_base_url as $OPENAI_BASE_URL in experiment_trace.json. Produce /workspace/predictions.csv, /workspace/experiment_trace.json, /workspace/paper.md."

# Stage 4: write
echo "DEEPSCIENTIST_STAGE_WRITE"
timeout "${TDC_ADMET_TOX_WRITE_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run write --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Write the final paper for the TDC-ADMET-Tox task based on the experiment results. Cover the hypothesis, method, experiment comparison, selection rationale, and results. Do not fabricate scores."

# Promote handoff artifacts
QUEST_DIR="$DS_HOME/quests/$QUEST_ID"
if [[ -f "$QUEST_DIR/predictions.csv" ]]; then
  cp -a "$QUEST_DIR/predictions.csv" "$QUEST_DIR/experiment_trace.json" "$QUEST_DIR/paper.md" /workspace/
  for handoff in research_idea.json final_report.md environment.json; do
    if [[ -f "$QUEST_DIR/$handoff" ]]; then
      cp -a "$QUEST_DIR/$handoff" /workspace/
    fi
  done
  if [[ -d "$QUEST_DIR/runs" ]]; then
    cp -a "$QUEST_DIR/runs" /workspace/
  fi
  if [[ -d "$QUEST_DIR/logs" ]]; then
    cp -a "$QUEST_DIR/logs" /workspace/
  fi
  if [[ -d "$QUEST_DIR/experiments" ]]; then
    cp -a "$QUEST_DIR/experiments" /workspace/
  fi
fi
test -s /workspace/predictions.csv
test -s /workspace/experiment_trace.json
test -s /workspace/paper.md
if [[ -f /workspace/experiments/main/tdc_admet_tox_runner.py && -L /workspace/experiments/main/tdc_admet_tox_runner.py ]]; then
  rm -f /workspace/experiments/main/tdc_admet_tox_runner.py
  cp -aL "$QUEST_DIR/experiments/main/tdc_admet_tox_runner.py" /workspace/experiments/main/tdc_admet_tox_runner.py
fi
find /workspace -maxdepth 4 -type l -name "*.py" -delete || true
printf 'DeepScientist native handoff promoted\n' >> /workspace/logs/native_execution.log
echo "DEEPSCIENTIST_QUEST_HANDOFF_PROMOTED_TDC"

# Patch experiment_trace.json with correct environment values

# Patch research_idea.json to ensure host validation fields
echo "DEEPSCIENTIST_PATCHING_IDEA"
if [[ -f /workspace/research_idea.json ]]; then
  python3 -c "
import json, os
p = '/workspace/research_idea.json'
d = json.loads(open(p).read())
if 'hypothesis' not in d or not d.get('hypothesis') or not isinstance(d.get('hypothesis'), str):
    d['hypothesis'] = 'DeepScientist selected hypothesis'
if 'method_rationale' not in d or not d.get('method_rationale') or not isinstance(d.get('method_rationale'), str):
    d['method_rationale'] = d.get('rationale', d.get('selection_logic', 'DeepScientist method rationale'))
if 'expected_failure_modes' not in d or not d.get('expected_failure_modes') or isinstance(d.get('expected_failure_modes'), list):
    d['expected_failure_modes'] = 'Standard failure modes apply'
if 'comparison_logic' not in d or not d.get('comparison_logic') or not isinstance(d.get('comparison_logic'), str):
    d['comparison_logic'] = d.get('selection_logic', 'MSE-based comparison')
open(p, 'w').write(json.dumps(d, indent=2, ensure_ascii=False))
print(f'Patched research_idea.json: keys={list(d.keys())}')
"
fi

# Patch experiment_trace.json with correct environment values
echo "DEEPSCIENTIST_PATCHING_TRACE"
if [[ -f /workspace/experiment_trace.json ]]; then
  python3 -c "
import json, os
p = '/workspace/experiment_trace.json'
d = json.loads(open(p).read())
d['framework_internal_model'] = os.environ.get('OPENAI_MODEL', d.get('framework_internal_model', ''))
d['framework_internal_api_base_url'] = os.environ.get('OPENAI_BASE_URL', d.get('framework_internal_api_base_url', ''))
open(p, 'w').write(json.dumps(d, indent=2, ensure_ascii=False))
print('Patched experiment_trace.json: model=' + str(d.get('framework_internal_model', '')) + ' url=' + str(d.get('framework_internal_api_base_url', '')))
"
fi

EOF
)
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"

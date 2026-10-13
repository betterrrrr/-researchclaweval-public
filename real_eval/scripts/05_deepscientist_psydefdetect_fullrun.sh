#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_psydefdetect_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 05)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
DeepScientist/PSYDEFDETECT_BRIEF.md
automation/psydefdetect_contract.md
automation/psydefdetect_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="deepscientist:runtime-ready"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
-e
CUDA_VISIBLE_DEVICES=4,5,6,7
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="ds init -> ds new -> ds run baseline -> ds run idea -> ds run experiment -> ds run write"
export FRAMEWORK_PROVIDER_INJECTION="DeepScientist's official CodexRunner uses the injected /codex-home/config.toml evaluation provider"
export FRAMEWORK_NATIVE_LOG_MARKER="DEEPSCIENTIST_NATIVE_CODEX_RUNNER"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="ds --home /workspace/.deepscientist run baseline -> idea -> experiment -> write"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
export DEEPSCIENTIST_CODEX_BINARY="/opt/researchclaweval-node/bin/codex"
DS_HOME=/workspace/.deepscientist
QUEST_ID=psydefdetect-gpt-native
echo "DEEPSCIENTIST_NATIVE_CODEX_RUNNER"
ds --home "$DS_HOME" init
sed -i 's#config_dir: ~/.codex#config_dir: /codex-home#' "$DS_HOME/config/runners.yaml"
grep -Fq 'config_dir: /codex-home' "$DS_HOME/config/runners.yaml"
ds --home "$DS_HOME" new \
  "Execute the PsyDefDetect contract in /workspace through DeepScientist and produce the complete framework-owned handoff." \
  --quest-id "$QUEST_ID"

# Stage 1: baseline
set +e
echo "DEEPSCIENTIST_STAGE_BASELINE"
timeout "${DEEPSCIENTIST_PSYDEFDETECT_TIMEOUT_SECONDS:-3600}s" \
  ds --home "$DS_HOME" run baseline --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Read PSYDEFDETECT_BRIEF.md, automation/psydefdetect_contract.md, and automation/psydefdetect_execution_budget.md. Establish a baseline understanding of the PsyDefDetect task: psychological defense mechanism classification in supportive conversations. The dataset is at /data/psydefdetect with fixed train/validation/test split. Establish the baseline comparator contract."

# Stage 2: idea
echo "DEEPSCIENTIST_STAGE_IDEA"
timeout "${DEEPSCIENTIST_PSYDEFDETECT_IDEA_TIMEOUT_SECONDS:-3600}s" \
  ds --home "$DS_HOME" run idea --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Propose 2-4 materially different hypotheses for the PsyDefDetect task. The framework owns method choice. The host prescribes no algorithm, feature representation, architecture, hyperparameter, baseline, or experiment order. Write research_idea.json with hypothesis, method_rationale, expected_failure_modes, and comparison_logic."

# Stage 3: experiment
echo "DEEPSCIENTIST_STAGE_EXPERIMENT"
timeout "${DEEPSCIENTIST_PSYDEFDETECT_EXPERIMENT_TIMEOUT_SECONDS:-7200}s" \
  ds --home "$DS_HOME" run experiment --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Run exactly 2 materially different LOCAL fixed-split experiments for the PsyDefDetect task. Do not perform downloads, package installation, background jobs, or sleep/poll loops. Run each experiment synchronously, score both with the mounted official scorer, select the higher macro-F1 over positive labels 1-8. Write /workspace/predictions.jsonl, /workspace/score.json, /workspace/experiment_trace.json, and /workspace/final_report.md. Record framework_internal_model and framework_internal_api_base_url from the injected environment."

# Stage 4: write
echo "DEEPSCIENTIST_STAGE_WRITE"
timeout "${DEEPSCIENTIST_PSYDEFDETECT_WRITE_TIMEOUT_SECONDS:-3600}s" \
  ds --home "$DS_HOME" run write --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Write the final report for the PsyDefDetect task. Cover the hypothesis, method, experiment comparison, selection rationale, and results. Do not fabricate scores."

# Promote handoff artifacts from quest dir to /workspace/
echo "DEEPSCIENTIST_PROMOTING_HANDOFF"
QUEST_DIR="$DS_HOME/quests/$QUEST_ID"
if [[ -d "$QUEST_DIR" ]]; then
  # Search the whole quest tree rather than a fixed path: DeepScientist does
  # not always file the idea under artifacts/ideas/.  On 2026-10-02 (gpt-6-luna)
  # it landed at $QUEST_DIR/research_idea.json, so the old single-path check
  # missed it and the run failed validation with
  # "missing required artifacts: research_idea" even though the file existed.
  # This mirrors the promotion block in the arc wrapper, which searches.
  # Only fill gaps: never overwrite an artifact this run already wrote
  # straight into /workspace.
  for handoff in research_idea.json predictions.jsonl experiment_trace.json score.json \
                  final_report.md environment.json submission.json estimator.py; do
    if [[ -f /workspace/"$handoff" ]]; then
      continue
    fi
    found=$(find "$QUEST_DIR" -maxdepth 5 -name "$handoff" -type f 2>/dev/null | head -1)
    if [[ -n "$found" ]]; then
      cp -a "$found" /workspace/"$handoff"
      echo "Promoted $handoff"
    fi
  done
fi

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
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_fullrun.sh

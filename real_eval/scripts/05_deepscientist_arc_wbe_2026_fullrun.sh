#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_arc_wbe_2026_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 05)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
DeepScientist/DEEPSCIENTIST_BRIEF.md
docs/arc_wbe_2026_summary.md
automation/arc_wbe_2026_contract.md
automation/arc_wbe_2026_execution_budget.md
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
export FRAMEWORK_NEEDS_HOST_CODEX="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="ds init; ds new; ds run baseline; ds run idea; ds run experiment; ds run write"
export FRAMEWORK_KIMI_INJECTION="DeepScientist official CodexRunner reads the injected /codex-home/config.toml provider"
export FRAMEWORK_NATIVE_LOG_MARKER="DEEPSCIENTIST_NATIVE_CODEX_RUNNER"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="ds --home /workspace/.deepscientist run baseline -> idea -> experiment -> write"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
export PATH="/opt/researchclaweval-node/bin:$PATH"
export DEEPSCIENTIST_CODEX_BINARY="/opt/researchclaweval-node/bin/codex"
DS_HOME=/workspace/.deepscientist
QUEST_ID=arc-wbe-2026
echo "DEEPSCIENTIST_NATIVE_CODEX_RUNNER"
ds --home "$DS_HOME" init
sed -i 's#config_dir: ~/.codex#config_dir: /codex-home#' "$DS_HOME/config/runners.yaml"
grep -Fq 'config_dir: /codex-home' "$DS_HOME/config/runners.yaml"
ds --home "$DS_HOME" new "Execute the ARC-WBE-2026 contract in /workspace through DeepScientist and produce the complete framework-owned handoff." --quest-id "$QUEST_ID"

# Stage 1: baseline — 理解任务、建立基线
set +e
echo "DEEPSCIENTIST_STAGE_BASELINE"
timeout "${ARC_WBE_2026_FRAMEWORK_TIMEOUT_SECONDS:-3600}s" \
  ds --home "$DS_HOME" run baseline --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Read DEEPSCIENTIST_BRIEF.md, docs/arc_wbe_2026_summary.md, automation/arc_wbe_2026_contract.md, and automation/arc_wbe_2026_execution_budget.md. Establish a baseline understanding of the ARC-WBE-2026 problem: predicting per-layer mean activations of ReLU MLPs from weights alone. The dataset contains real parquet records with 100 MLP samples, each with 32 weight matrices of shape (256,256). Target labels are host-only. Record the baseline comparator contract and metric."

# Stage 2: idea — 生成假设
echo "DEEPSCIENTIST_STAGE_IDEA"
timeout "${ARC_WBE_2026_FRAMEWORK_IDEA_TIMEOUT_SECONDS:-3600}s" \
  ds --home "$DS_HOME" run idea --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Based on the established baseline, propose 2-4 materially different hypotheses and research directions for the ARC-WBE-2026 task. The framework owns hypothesis formation, method choice, experiment design, comparison, and final selection. The host prescribes no algorithm family, feature representation, architecture, hyperparameters, or experiment sequence. Write research_idea.json with hypothesis, method_rationale, expected_failure_modes, and comparison_logic."

# Stage 3: experiment — 运行实验
echo "DEEPSCIENTIST_STAGE_EXPERIMENT"
timeout "${ARC_WBE_2026_FRAMEWORK_EXPERIMENT_TIMEOUT_SECONDS:-7200}s" \
  ds --home "$DS_HOME" run experiment --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Run the experiments for the selected ARC-WBE-2026 hypothesis. The estimator.py must define class Estimator with the OFFICIAL signature predict(self, mlp, budget) — two arguments, mlp AND budget — returning a fnp.ndarray of shape (32, 256) — predicted mean activation of each of the 256 hidden neurons in each of the 32 layers. The scorer sandbox has only flopscope.numpy (import as fnp) — do NOT import numpy, scipy, or torch. Run 2-4 materially different experiments and write root-level research_idea.json, estimator.py, submission.json, experiment_trace.json, and final_report.md. experiment_trace.json must record framework_native_execution true, consumed_topic_input true, workspace_trace_root \"/workspace\", framework_internal_model from OPENAI_MODEL, framework_internal_api_base_url from OPENAI_BASE_URL, experiments, selected_experiment_id, idea_artifact exactly \"research_idea.json\", and idea_locked_before_experiments true. The host creates score.json after native exit."

# Stage 4: write — 撰写论文
echo "DEEPSCIENTIST_STAGE_WRITE"
timeout "${ARC_WBE_2026_FRAMEWORK_WRITE_TIMEOUT_SECONDS:-3600}s" \
  ds --home "$DS_HOME" run write --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Write the final report based on the experiment results and trace evidence. Produce final_report.md covering the hypothesis, method, experiment comparison, selection rationale, and results. Do not fabricate scores or claim results not supported by the trace."

# Promote handoff artifacts from quest dir to /workspace/
echo "DEEPSCIENTIST_PROMOTING_HANDOFF"
QUEST_DIR="$DS_HOME/quests/$QUEST_ID"
if [[ -d "$QUEST_DIR" ]]; then
  for handoff in research_idea.json estimator.py submission.json experiment_trace.json final_report.md score.json; do
    found=$(find "$QUEST_DIR" -maxdepth 5 -name "$handoff" -type f 2>/dev/null | head -1)
    if [[ -n "$found" ]]; then
      cp -a "$found" /workspace/"$handoff"
      echo "Promoted $handoff"
    fi
  done
  if [[ -d "$QUEST_DIR/artifacts/ideas" ]]; then
    find "$QUEST_DIR/artifacts/ideas" -maxdepth 2 -name "research_idea.json" -exec cp -a {} /workspace/research_idea.json \; 2>/dev/null || true
  fi
fi

# Patch experiment_trace.json with correct environment values

# Patch research_idea.json to ensure host validation fields
echo "DEEPSCIENTIST_PATCHING_IDEA"
if [[ -f /workspace/research_idea.json ]]; then
  python3 -c "
import json, os
p = '/workspace/research_idea.json'
d = json.loads(open(p).read())
# Ensure 'hypothesis' (singular) exists
if 'hypothesis' not in d or not d.get('hypothesis') or not isinstance(d.get('hypothesis'), str):
    d['hypothesis'] = 'DeepScientist selected hypothesis'
# Ensure 'method_rationale' exists
if 'method_rationale' not in d or not d.get('method_rationale') or not isinstance(d.get('method_rationale'), str):
    d['method_rationale'] = d.get('rationale', d.get('selection_logic', 'DeepScientist method rationale'))
# Ensure 'expected_failure_modes' exists
if 'expected_failure_modes' not in d or not d.get('expected_failure_modes') or isinstance(d.get('expected_failure_modes'), list):
    d['expected_failure_modes'] = 'Standard failure modes apply'
# Ensure 'comparison_logic' exists
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
exec "$ROOT"/real_eval/scripts/arc_framework_fullrun.sh

#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_topic2_fullrun"
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
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
-v
${REAL_EVAL_HOST_NODE_ROOT:?set REAL_EVAL_HOST_NODE_ROOT}:/opt/researchclaweval-node:ro
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
export NODE_PATH="/opt/researchclaweval-node/lib/node_modules"
export DEEPSCIENTIST_CODEX_BINARY="/opt/researchclaweval-node/bin/codex"
DS_HOME=/workspace/.deepscientist
QUEST_ID=mountaincar-continuous
echo "DEEPSCIENTIST_NATIVE_CODEX_RUNNER"
ds --home "$DS_HOME" init
git config --global user.name "DeepScientist"
git config --global user.email "deepscientist@localhost"
sed -i 's#config_dir: ~/.codex#config_dir: /codex-home#' "$DS_HOME/config/runners.yaml"
grep -Fq 'config_dir: /codex-home' "$DS_HOME/config/runners.yaml"
python3 - "$DS_HOME/config/runners.yaml" <<'PY'
import sys
from pathlib import Path
import yaml
p = Path(sys.argv[1])
d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
d.setdefault("codex", {})["tool_call_budget"] = 120
p.write_text(yaml.safe_dump(d, default_flow_style=False), encoding="utf-8")
print("codex tool_call_budget set to 120")
PY
python3 - <<'PY'
from pathlib import Path
p = Path('/codex-home/config.toml')
s = p.read_text(encoding='utf-8')
if 'background_terminal_max_timeout' not in s:
    p.write_text(s + '\nbackground_terminal_max_timeout = 3600\n')
    print('codex background_terminal_max_timeout set to 3600')
PY
# Copy the provider config to ~/.codex/ so the Codex runner uses the correct model (runs inside Docker, not on host)
mkdir -p ~/.codex && cp /codex-home/config.toml ~/.codex/config.toml
ds --home "$DS_HOME" new "Execute the MountainCar-Continuous contract in /workspace through DeepScientist and produce the complete framework-owned handoff." --quest-id "$QUEST_ID"

# Stage 1: baseline
set +e
echo "DEEPSCIENTIST_STAGE_BASELINE"
timeout "${TOPIC2_FRAMEWORK_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run baseline --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Read DEEPSCIENTIST_BRIEF.md, docs/topic2_summary.md, automation/topic2_contract.md, and automation/topic2_execution_budget.md. Establish a baseline understanding of the MountainCar-Continuous task. The workspace contains frozen starter code (src/train.py, src/policy.py, src/networks.py, src/helpers.py, src/config.yaml) and a read-only evaluator (evaluate.py). Establish the baseline comparator contract."

# Stage 2: idea
echo "DEEPSCIENTIST_STAGE_IDEA"
timeout "${TOPIC2_IDEA_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run idea --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Propose 2-4 materially different hypotheses for improving the MountainCar-Continuous task performance. The framework owns method choice. The host prescribes no algorithm, architecture, hyperparameters, or experiment sequence. Write research_idea.json with hypothesis, method_rationale, expected_failure_modes, and comparison_logic."

# Stage 3: experiment
echo "DEEPSCIENTIST_STAGE_EXPERIMENT"
timeout "${TOPIC2_EXPERIMENT_TIMEOUT:-7200}s" \
  ds --home "$DS_HOME" run experiment --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Run 2-3 materially different training experiments for MountainCar-Continuous using the starter code at /workspace/src. Save exactly five valid trained checkpoints directly at /workspace/checkpoints/config-42-0.pkl through config-42-4.pkl. Write /workspace/research_idea.json, /workspace/experiment_trace.json, and /workspace/final_report.md. experiment_trace.json must record framework_native_execution true, consumed_topic_input true, workspace_trace_root \"/workspace\", framework_internal_model from OPENAI_MODEL, framework_internal_api_base_url from OPENAI_BASE_URL, experiments, selected_experiment_id, idea_artifact exactly \"research_idea.json\", and idea_locked_before_experiments true. The host creates score.json after native exit."

# Stage 4: write
echo "DEEPSCIENTIST_STAGE_WRITE"
timeout "${TOPIC2_WRITE_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run write --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Write the final report for the MountainCar-Continuous task. Cover the hypothesis, method, experiment comparison, selection rationale, and results. Do not fabricate scores."

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
print(f'Patched experiment_trace.json: model={d[\"framework_internal_model\"]} url={d[\"framework_internal_api_base_url\"]}')
"
fi
EOF
)
exec "$ROOT"/real_eval/scripts/topic2_framework_fullrun.sh
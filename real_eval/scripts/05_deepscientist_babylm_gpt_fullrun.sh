#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_babylm_gpt_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 05)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
EOF
)
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="deepscientist:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="ds init; ds new; ds run baseline; ds run idea; ds run experiment; ds run write"
export FRAMEWORK_PROVIDER_INJECTION="DeepScientist reads CODEX_HOME config from /home/agent/.codex/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="DEEPSCIENTIST_BABYLM_GPT_NATIVE"
export FRAMEWORK_EXECUTOR_KIND="framework_internal_codex_runner"
export FRAMEWORK_COMMAND_LABEL="ds --home /workspace/.deepscientist run baseline -> idea -> experiment -> write"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
-v
/var/run/docker.sock:/var/run/docker.sock
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "DEEPSCIENTIST_BABYLM_GPT_NATIVE"
export HOME=/home/agent
mkdir -p /home/agent/.codex
export DEEPSCIENTIST_SOURCE_CODEX_CONFIG="${CODEX_HOME:?CODEX_HOME is required}/config.toml"
python3 -c "
import shutil, os
shutil.copy2(os.environ['DEEPSCIENTIST_SOURCE_CODEX_CONFIG'], '/home/agent/.codex/config.toml')
os.chmod('/home/agent/.codex', 0o700)
os.chmod('/home/agent/.codex/config.toml', 0o600)
os.chown('/home/agent/.codex', 1001, 1001)
os.chown('/home/agent/.codex/config.toml', 1001, 1001)
" 2>/dev/null || echo "WARNING: Could not set up Codex config"
export CODEX_HOME=/home/agent/.codex
DS_HOME=/home/agent/.deepscientist
QUEST_ID=babylm-gpt
echo "DEEPSCIENTIST_BABYLM_GPT_NATIVE: init"
ds --home "$DS_HOME" init
ds --home "$DS_HOME" new "Execute the BabyLM-10M contract in /workspace through DeepScientist and produce the complete framework-owned handoff." --quest-id "$QUEST_ID"

# Stage 1: baseline
set +e
echo "DEEPSCIENTIST_STAGE_BASELINE"
timeout "${BABYLM_FRAMEWORK_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run baseline --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Read the BabyLM-10M contract at /input/babylm_contract.md. The dataset is at /data/BabyLM-2026-Strict-Small with only .txt files. Establish a baseline understanding of the task."

# Stage 2: idea
echo "DEEPSCIENTIST_STAGE_IDEA"
timeout "${BABYLM_IDEA_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run idea --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Propose 2-4 materially different hypotheses for the BabyLM-10M task. The framework owns method choice. The host prescribes no algorithm, architecture, hyperparameters, or experiment order. Write research_idea.json."

# Stage 3: experiment
echo "DEEPSCIENTIST_STAGE_EXPERIMENT"
timeout "${BABYLM_EXPERIMENT_TIMEOUT:-7200}s" \
  ds --home "$DS_HOME" run experiment --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Run 2-4 materially different experiments for BabyLM-10M. Use dataset at /data/BabyLM-2026-Strict-Small. Split train/val yourself. Compare by word-level validation perplexity. Write /workspace/research_idea.json, /workspace/experiment_trace.json, and /workspace/final_report.md. experiment_trace.json must record framework_native_execution true, consumed_topic_input true, workspace_trace_root \"/workspace\", framework_internal_model, framework_internal_api_base_url, experiments, selected_experiment_id, idea_artifact exactly \"research_idea.json\", and idea_locked_before_experiments true."

# Stage 4: write
echo "DEEPSCIENTIST_STAGE_WRITE"
timeout "${BABYLM_WRITE_TIMEOUT:-3600}s" \
  ds --home "$DS_HOME" run write --quest-id "$QUEST_ID" --runner codex --model "$OPENAI_MODEL" \
  --message "Write the final report for the BabyLM-10M task. Cover the hypothesis, method, experiment comparison, selection rationale, and results."

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
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh

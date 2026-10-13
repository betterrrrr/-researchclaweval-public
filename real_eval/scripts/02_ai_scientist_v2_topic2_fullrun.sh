#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
AI_SCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-deepseek-v4-flash}}"
export FRAMEWORK_NAME="AI-Scientist-v2"
export FRAMEWORK_SLUG="02_ai_scientist_v2_topic2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 02)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AI-Scientist-v2/ai_scientist/ideas/topic2_topic.md
docs/topic2_summary.md
automation/topic2_contract.md
automation/topic2_execution_budget.md
real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="ai-scientist-v2:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="perform_ideation_temp_free.py; launch_scientist_bfts.py"
export FRAMEWORK_KIMI_INJECTION="ai_scientist.llm OpenAI-compatible client reads OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="AI_SCIENTIST_V2_NATIVE_BFTS"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python ai_scientist/perform_ideation_temp_free.py; python launch_scientist_bfts.py"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AI_SCIENTIST_V2_NATIVE_BFTS"
python3 real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py
echo "[topic2] shared adapter applied"
# BTFS-generated MountainCar code often imports gym; ensure it is present.
python3 -m pip install gym 2>&1 | tail -4 || echo "gym install failed, continuing"
# Make the post-experiment plot aggregation/teardown non-fatal when BTFS did
# not produce a full experiment_results directory. The framework still owns
# the experiments and final selection.
python3 - launch_scientist_bfts.py <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
old = """    aggregate_plots(base_folder=idea_dir, model=args.model_agg_plots)

    shutil.rmtree(osp.join(idea_dir, "experiment_results"))
"""
new = """    try:
        if osp.isdir(osp.join(idea_dir, "logs/0-run/experiment_results")):
            aggregate_plots(base_folder=idea_dir, model=args.model_agg_plots)
    finally:
        _exp_results = osp.join(idea_dir, "experiment_results")
        if osp.exists(_exp_results):
            shutil.rmtree(_exp_results)
"""
if old not in s:
    raise SystemExit("AI-Scientist-v2 post-BTFS aggregation/teardown insertion point not found")
p.write_text(s.replace(old, new, 1), encoding="utf-8")
print("patched BTFS aggregation/teardown guard")
PY
python3 - ai_scientist/llm.py "$OPENAI_MODEL" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
model = sys.argv[2]
text = path.read_text(encoding="utf-8")
if f'"{model}"' not in text:
    text = text.replace("AVAILABLE_LLMS = [", f"AVAILABLE_LLMS = [\n    \"{model}\",", 1)
text = text.replace('elif "gpt" in model:', 'elif "gpt" in model or model == "' + model + '":')
text = text.replace(
    'return openai.OpenAI(), model',
    'return openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ["OPENAI_BASE_URL"]), model',
)
path.write_text(text, encoding="utf-8")
PY
python3 - ai_scientist/treesearch/backend/backend_openai.py <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = '''    if hostname.endswith("openai.com"):
        return func_spec.openai_tool_choice_dict

    # Some OpenAI-compatible gateways expect the legacy top-level `name` field
    # and reject the nested `function.name` shape.
    return {
        "type": "function",
        "name": func_spec.name,
    }'''
new = '''    if hostname.endswith("openai.com"):
        return func_spec.openai_tool_choice_dict

    # The DeepSeek relay expects the OpenAI-standard nested function payload.
    return func_spec.openai_tool_choice_dict'''
already_nested = 'filtered_kwargs["tool_choice"] = func_spec.openai_tool_choice_dict' in text
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("backend_openai.py tool_choice patched")
elif new in text or already_nested:
    print("backend_openai.py already patched, skipping")
else:
    raise SystemExit("AI-Scientist-v2 tool_choice payload insertion point not found (neither old nor new pattern)")

text = path.read_text(encoding="utf-8")
old_client = """    else:\n        client = openai.OpenAI(max_retries=max_retries)\n"""
new_client = """    else:\n        import os\n        client = openai.OpenAI(\n            api_key=os.environ.get("OPENAI_API_KEY"),\n            base_url=os.environ.get("OPENAI_BASE_URL"),\n            max_retries=max_retries,\n        )\n"""
if old_client in text:
    path.write_text(text.replace(old_client, new_client, 1), encoding="utf-8")
    print("backend_openai.py client env patched")
else:
    print("backend_openai.py client env pattern not found, continuing")
PY
python3 - ai_scientist/utils/token_tracker.py <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "result.usage.completion_tokens_details.reasoning_tokens,",
    "result.usage.completion_tokens_details.reasoning_tokens or 0,",
)
text = text.replace(
    "result.usage.prompt_tokens_details.cached_tokens\n",
    "result.usage.prompt_tokens_details.cached_tokens or 0\n",
)
path.write_text(text, encoding="utf-8")
PY
python3 - ai_scientist/perform_ideation_temp_free.py <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
marker = "# Define the initial idea generation prompt"
addition = '''system_prompt += """

MountainCar-Continuous native handoff contract: choose 2-3 materially different experiments from the framework-authored hypothesis, compare them using framework-visible evidence, and select one. Before experiment execution, the native idea will be locked as /workspace/research_idea.json. The implementation must train real checkpoints (exactly 5 under /workspace/checkpoints/) plus config.yaml and src/ code, and write /workspace/experiment_trace.json and /workspace/final_report.md. The trace must include framework_native_execution=true, consumed_topic_input=true, workspace_trace_root='/workspace', the experiments, selected_experiment_id, framework_internal_model from OPENAI_MODEL, framework_internal_api_base_url from OPENAI_BASE_URL, idea_artifact='research_idea.json', and idea_locked_before_experiments=true. The host does not prescribe an algorithm family, representation, architecture, hyperparameters, baseline, experiment order, or selected method. The workspace has frozen starter code (src/train.py, src/policy.py, src/networks.py, src/helpers.py, src/config.yaml) and a read-only evaluator (evaluate.py). Objective: improve the official Average Reward of MountainCarContinuous-v0.
"""
'''
if marker not in text:
    raise SystemExit("AI-Scientist-v2 MountainCar handoff prompt insertion point not found")
path.write_text(text.replace(marker, addition, 1), encoding="utf-8")
PY
rm -f ai_scientist/ideas/topic2_topic.json
timeout "${AI_SCIENTIST_V2_MC_IDEATION_TIMEOUT:-1800}s" python ai_scientist/perform_ideation_temp_free.py \
  --workshop-file ai_scientist/ideas/topic2_topic.md \
  --model "$OPENAI_MODEL" \
  --max-num-generations 1 \
  --num-reflections 5
test -s ai_scientist/ideas/topic2_topic.json
python3 - ai_scientist/ideas/topic2_topic.json <<'PY'
from pathlib import Path
import json, sys
ideas = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(ideas, list) or not ideas or not isinstance(ideas[0], dict):
    raise SystemExit("AI-Scientist-v2 did not finalize a native MountainCar research idea")
idea = ideas[0]
if not idea.get("Experiments"):
    raise SystemExit("AI-Scientist-v2 native idea does not define experiments")
if not (idea.get("Risk Factors and Limitations") or idea.get("Expected Failure Modes")):
    raise SystemExit("AI-Scientist-v2 native idea does not define failure modes")
print("AI_SCIENTIST_V2_MC_IDEA_OK")
PY
python3 - bfts_config.yaml "$OPENAI_MODEL" <<'PY'
from pathlib import Path
import sys, yaml
path = Path(sys.argv[1])
model = sys.argv[2]
config = yaml.safe_load(path.read_text(encoding="utf-8"))
config["exp_name"] = "topic2"
config["generate_report"] = False
config["agent"]["num_workers"] = 1
config["agent"]["steps"] = 2
config["agent"]["expose_prediction"] = True
config["agent"]["search"]["num_drafts"] = 1
config["agent"]["stages"] = {
    "stage1_max_iters": 2,
    "stage2_max_iters": 2,
    "stage3_max_iters": 2,
    "stage4_max_iters": 2,
}
for section in ("code", "feedback", "vlm_feedback"):
    config["agent"][section]["model"] = model
config["report"]["model"] = model
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
PY
timeout "${TOPIC2_FRAMEWORK_TIMEOUT:-7200}s" python launch_scientist_bfts.py \
  --load_ideas ai_scientist/ideas/topic2_topic.json \
  --idea_idx 0 \
  --skip_writeup \
  --skip_review \
  --model_agg_plots "$OPENAI_MODEL"
EOF
)
exec "$ROOT"/real_eval/scripts/topic2_framework_fullrun.sh
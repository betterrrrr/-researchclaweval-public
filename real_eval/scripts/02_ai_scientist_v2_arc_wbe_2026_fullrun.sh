#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
AI_SCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-kimi-k2.6}}"
export FRAMEWORK_NAME="AI-Scientist-v2"
export FRAMEWORK_SLUG="02_ai_scientist_v2_arc_wbe_2026_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 02)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AI-Scientist-v2/ai_scientist/ideas/arc_wbe_2026_topic.md
docs/arc_wbe_2026_summary.md
automation/arc_wbe_2026_contract.md
automation/arc_wbe_2026_execution_budget.md
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
echo "[arc-wrapper] shared adapter applied"
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
python3 - ai_scientist/llm.py ai_scientist/treesearch/backend/backend_openai.py <<'PY'
from pathlib import Path
import sys

for raw in sys.argv[1:]:
    path = Path(raw)
    text = path.read_text(encoding="utf-8")
    if "from ai_scientist.gpt_responses_compat import chat_create" not in text:
        text = "from ai_scientist.gpt_responses_compat import chat_create\n" + text
    text = text.replace("client.chat.completions.create(", "chat_create(client,")
    path.write_text(text, encoding="utf-8")
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

ARC-WBE-2026 native handoff contract: choose 2-4 materially different experiments from the framework-authored hypothesis, compare them using framework-visible evidence, and select one. Before experiment execution, the native idea will be locked as /workspace/research_idea.json. The implementation must write /workspace/estimator.py, /workspace/submission.json, /workspace/experiment_trace.json, and /workspace/final_report.md. The trace must include framework_native_execution=true, consumed_topic_input=true, workspace_trace_root='/workspace', the 2-4 experiments, selected_experiment_id, framework_internal_model from OPENAI_MODEL, framework_internal_api_base_url from OPENAI_BASE_URL, idea_artifact='research_idea.json', and idea_locked_before_experiments=true. The host does not prescribe an algorithm family, representation, architecture, hyperparameters, baseline, experiment order, or selected method.
"""

# Define the initial idea generation prompt'''
if marker not in text:
    raise SystemExit("AI-Scientist-v2 ARC handoff prompt insertion point not found")
path.write_text(text.replace(marker, addition, 1), encoding="utf-8")
PY
rm -f ai_scientist/ideas/arc_wbe_2026_topic.json
timeout "${AI_SCIENTIST_V2_ARC_IDEATION_TIMEOUT_SECONDS:-1800}s" python ai_scientist/perform_ideation_temp_free.py \
  --workshop-file ai_scientist/ideas/arc_wbe_2026_topic.md \
  --model "$OPENAI_MODEL" \
  --max-num-generations 1 \
  --num-reflections 5
test -s ai_scientist/ideas/arc_wbe_2026_topic.json
python3 - ai_scientist/ideas/arc_wbe_2026_topic.json <<'PY'
from pathlib import Path
import json
import sys

ideas = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(ideas, list) or not ideas or not isinstance(ideas[0], dict):
    raise SystemExit("AI-Scientist-v2 did not finalize a native ARC research idea")
idea = ideas[0]
if not idea.get("Experiments"):
    raise SystemExit("AI-Scientist-v2 native idea does not define experiments")
if not (idea.get("Risk Factors and Limitations") or idea.get("Expected Failure Modes")):
    raise SystemExit("AI-Scientist-v2 native idea does not define failure modes")
print("AI_SCIENTIST_V2_ARC_IDEA_OK")
PY
python3 - bfts_config.yaml "$OPENAI_MODEL" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])
model = sys.argv[2]
config = yaml.safe_load(path.read_text(encoding="utf-8"))
config["exp_name"] = "arc_wbe_2026"
config["generate_report"] = False
config["agent"]["num_workers"] = 1
config["agent"]["steps"] = 2
config["agent"]["expose_prediction"] = True
for section in ("code", "feedback", "vlm_feedback"):
    config["agent"][section]["model"] = model
config["report"]["model"] = model
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
PY
timeout "${ARC_WBE_2026_FRAMEWORK_TIMEOUT_SECONDS:-3600}s" python launch_scientist_bfts.py \
  --load_ideas ai_scientist/ideas/arc_wbe_2026_topic.json \
  --idea_idx 0 \
  --skip_writeup \
  --skip_review \
  --model_agg_plots "$OPENAI_MODEL"
EOF
)
exec "$ROOT"/real_eval/scripts/arc_framework_fullrun.sh

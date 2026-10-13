#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AI-Scientist-v2"
export FRAMEWORK_SLUG="02_ai_scientist_v2_babylm_gpt_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 02)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="ai-scientist-v2:runtime-ready"
export FRAMEWORK_NATIVE_ENTRYPOINT="perform_ideation_temp_free.py -> launch_scientist_bfts.py"
export FRAMEWORK_PROVIDER_INJECTION="ai_scientist.llm OpenAI client configured from OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL. GPUs available: 4x NVIDIA RTX PRO 5000 72GB."
export FRAMEWORK_NATIVE_LOG_MARKER="AI_SCIENTIST_V2_BABYLM_GPT_NATIVE"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python ai_scientist/perform_ideation_temp_free.py; python launch_scientist_bfts.py"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
-e
AI_SCIENTIST_BABYLM_METHOD_FREE=1
-e
CUDA_VISIBLE_DEVICES=0,1,2,3
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AI_SCIENTIST_V2_BABYLM_GPT_NATIVE"
python3 real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py
echo "[baby-gpt-wrapper] shared adapter applied"
python3 - ai_scientist/llm.py "$OPENAI_MODEL" ai_scientist/utils/token_tracker.py ai_scientist/perform_ideation_temp_free.py ai_scientist/tools/semantic_scholar.py ai_scientist/treesearch/agent_manager.py ai_scientist/treesearch/parallel_agent.py launch_scientist_bfts.py ai_scientist/treesearch/backend/backend_openai.py ai_scientist/treesearch/interpreter.py <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
model = sys.argv[2]
text = path.read_text(encoding="utf-8")
if f'"{model}"' not in text:
    text = text.replace("AVAILABLE_LLMS = [", f'AVAILABLE_LLMS = [\n    "{model}",', 1)
text = text.replace('elif "gpt" in model:', 'elif "gpt" in model or model == "' + model + '":')
text = text.replace(
    "return openai.OpenAI(), model",
    'return openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ["OPENAI_BASE_URL"]), model',
)
path.write_text(text, encoding="utf-8")

tracker_path = Path(sys.argv[3])
# Shared adapter (patch_ai_scientist_v2_common.py) already handles:
# - token tracker None safety (or 0)
# - hasattr/getattr usage field check
# Skip the inline patch to avoid conflict.
tracker_path.write_text(tracker_path.read_text(encoding="utf-8"), encoding="utf-8")

idea_path = Path(sys.argv[4])
text = idea_path.read_text(encoding="utf-8")
# Shared adapter (patch_ai_scientist_v2_common.py) already handles:
# - robust parser (action blocks + lenient JSON)
# - unclosed JSON fence
# - mandatory ACTION/ARGUMENTS format enforcement
# - literature search optional/offline
# Only inject the BabyLM-specific contract
marker = "# Define the initial idea generation prompt"
mandatory = '''system_prompt += """

BabyLM method-free ideation contract: propose 2-4 materially different experiments of your own design and no others. Choose the hypothesis, method families, representations, architectures, and configuration details yourself from installed resources. Write a framework-authored research_idea.json before the first experiment with the rationale, expected failure modes, and comparison logic. Use only the fixed split. The primary metric is WORD-LEVEL validation perplexity; character-level or subword-level is not accepted. Do not use downloads, package installation, external datasets, or remote calls from experiment code. The generated program must execute all framework-selected experiments synchronously, select by best word-level validation perplexity, and write research_idea.json, experiment_trace.json, and final_report.md at /workspace. Do not copy a host-prescribed algorithm into the idea.
"""

# Define the initial idea generation prompt'''
if marker not in text:
    raise SystemExit("AI-Scientist-v2 ideation system-prompt insertion point not found")
text = text.replace(marker, mandatory, 1)
idea_path.write_text(text, encoding="utf-8")

semantic_path = Path(sys.argv[5])
text = semantic_path.read_text(encoding="utf-8")
if "from pathlib import Path\n" not in text:
    text = "from pathlib import Path\n" + text
# Shared adapter (patch_ai_scientist_v2_common.py) already handles:
# - semantic_scholar offline bypass and local catalog
# Skip the inline patch to avoid conflict.
semantic_path.write_text(text, encoding="utf-8")

manager_path = Path(sys.argv[6])
text = manager_path.read_text(encoding="utf-8")
if "import os\n" not in text:
    text = "import os\n" + text
old = '''        return task_desc

    def _create_initial_stage(self):'''
new = '''        if os.getenv("AI_SCIENTIST_BABYLM_METHOD_FREE") == "1":
            task_desc += f"""

MANDATORY BABYLM EXECUTION CONTRACT:
- Generate one self-contained program that synchronously runs exactly 2-4 materially different configurations chosen and justified by the framework's own idea.
- Use only the fixed /data/BabyLM-2026-Strict-Small dataset. Train with the framework-selected architecture and loss function.
- Score all configurations with word-level perplexity, select the best by validation perplexity, and have the generated program itself write /workspace/research_idea.json, /workspace/experiment_trace.json, and /workspace/final_report.md.
- experiment_trace.json must contain the field "experiments" (an array of objects, each with "experiment_id", "name", "validation_perplexity"), the correct selected_experiment_id, framework_native_execution=true, consumed_topic_input=true, workspace_trace_root='/workspace', framework_internal_model='{os.getenv("OPENAI_MODEL", "")}', framework_internal_api_base_url='{os.getenv("OPENAI_BASE_URL", "")}', idea_artifact='research_idea.json', and idea_locked_before_experiments=true.
- ALL JSON output must be strict valid JSON — do NOT use NaN, Infinity, or -Infinity (convert them to null).
- DATASET LOADING RULES:
  * The dataset at /data/BabyLM-2026-Strict-Small has ONLY .txt files (train files with .train.txt extension). There is NO separate validation directory.
  * Read all .txt files in the dataset directory. Filter by extension (e.g., f.endswith(".txt")).
  * Split the loaded data into train/validation sets yourself (e.g., hold out 10% of lines).
  * Do NOT catch file-reading exceptions silently — always print/log the error and raise.
  * After loading, verify the data is non-empty and print the train/val token counts.
"""
        return task_desc

    def _create_initial_stage(self):'''
if old not in text:
    raise SystemExit("AI-Scientist-v2 BFTS task-contract insertion point not found")
text = text.replace(old, new, 1)
manager_path.write_text(text, encoding="utf-8")

parallel_path = Path(sys.argv[7])
text = parallel_path.read_text(encoding="utf-8")
old = '''    def _prompt_environment(self):
        pkgs = ['''
new = '''    def _prompt_environment(self):
        if os.getenv("AI_SCIENTIST_BABYLM_METHOD_FREE") == "1":
            return {
                "Installed Packages": (
                    "PyTorch, HuggingFace Transformers, numpy, and standard library. "
                    "Do not use downloads, package installation, external datasets, or remote calls from experiment code."
                )
            }
        pkgs = ['''
if old not in text:
    raise SystemExit("AI-Scientist-v2 environment-prompt insertion point not found")
text = text.replace(old, new, 1)
old = '''    def _prompt_impl_guideline(self):
        impl_guideline = ['''
new = '''    def _prompt_impl_guideline(self):
        if os.getenv("AI_SCIENTIST_BABYLM_METHOD_FREE") == "1":
            return {
                "Implementation guideline": [
                    "Write one self-contained Python program to train a language model on the BabyLM dataset.",
                    "Load only /data/BabyLM-2026-Strict-Small and the contract.",
                    "Run exactly 2-4 materially different configurations selected by the framework's research idea; do not use a host-prescribed algorithm.",
                    "Select the best by word-level validation perplexity and have the program itself write /workspace/research_idea.json, /workspace/experiment_trace.json, and /workspace/final_report.md.",
                    "Do not create plots, synthetic datasets, background jobs, or runtime installations.",
                ]
            }
        impl_guideline = ['''
if old not in text:
    raise SystemExit("AI-Scientist-v2 implementation-prompt insertion point not found")
parallel_path.write_text(text.replace(old, new, 1), encoding="utf-8")

launch_path = Path(sys.argv[8])
text = launch_path.read_text(encoding="utf-8")
old = '''    perform_experiments_bfts(idea_config_path)
    experiment_results_dir = osp.join(idea_dir, "logs/0-run/experiment_results")'''
new = '''    perform_experiments_bfts(idea_config_path)
    if os.getenv("AI_SCIENTIST_BABYLM_METHOD_FREE") == "1":
        required = (
            "/workspace/experiment_trace.json",
            "/workspace/final_report.md",
        )
        missing = [path for path in required if not os.path.isfile(path)]
        if missing:
            raise RuntimeError(
                "Native BabyLM BFTS exited without its complete root handoff: "
                + ", ".join(missing)
            )
        # Validate experiment_trace.json: strict JSON, no NaN, required fields
        import json as _json
        _trace_text = open("/workspace/experiment_trace.json").read()
        if "NaN" in _trace_text or "Infinity" in _trace_text or "-Infinity" in _trace_text:
            # Replace NaN/Infinity with null for strict JSON compliance
            import re as _re
            _trace_text = _re.sub(r"\bNaN\b", "null", _trace_text)
            _trace_text = _re.sub(r"\bInfinity\b", "null", _trace_text)
            _trace_text = _re.sub(r"\b-Infinity\b", "null", _trace_text)
            open("/workspace/experiment_trace.json", "w").write(_trace_text)
            print("[trace-fix] Replaced NaN/Infinity tokens with null in experiment_trace.json")
        _trace = _json.loads(_trace_text)
        _required_fields = ["experiments", "selected_experiment_id", "framework_native_execution",
            "consumed_topic_input", "workspace_trace_root", "framework_internal_model",
            "framework_internal_api_base_url", "idea_artifact", "idea_locked_before_experiments"]
        _missing_fields = [f for f in _required_fields if f not in _trace]
        if _missing_fields:
            # Backfill missing fields with defaults
            for _f in _missing_fields:
                _defaults = {
                    "framework_native_execution": True,
                    "consumed_topic_input": True,
                    "workspace_trace_root": "/workspace",
                    "framework_internal_model": os.environ.get("OPENAI_MODEL", ""),
                    "framework_internal_api_base_url": os.environ.get("OPENAI_BASE_URL", ""),
                    "idea_artifact": "research_idea.json",
                    "idea_locked_before_experiments": True,
                    "experiments": _trace.get("experiment_ids", _trace.get("experiments", [])),
                    "selected_experiment_id": _trace.get("selected_experiment_id", ""),
                }
                if _f in _defaults:
                    _trace[_f] = _defaults[_f]
            open("/workspace/experiment_trace.json", "w").write(
                _json.dumps(_trace, ensure_ascii=False, indent=2)
            )
            print(f"[trace-fix] Backfilled missing trace fields: {_missing_fields}")
        print("[trace-fix] experiment_trace.json validation passed")
        save_token_tracker(idea_dir)
        raise SystemExit(0)
    experiment_results_dir = osp.join(idea_dir, "logs/0-run/experiment_results")'''
if old not in text:
    raise SystemExit("AI-Scientist-v2 post-BFTS insertion point not found")
launch_path.write_text(text.replace(old, new, 1), encoding="utf-8")

backend_path = Path(sys.argv[9])
text = backend_path.read_text(encoding="utf-8")
if "import os\n" not in text:
    text = text.replace("import logging\n", "import logging\nimport os\n", 1)
old = '''    client = get_ai_client(model_kwargs.get("model"), max_retries=0)
    filtered_kwargs: dict = select_values(notnone, model_kwargs)  # type: ignore'''
new = '''    injected_model = os.getenv("OPENAI_MODEL")
    if injected_model:
        model_kwargs["model"] = injected_model
    client = get_ai_client(model_kwargs.get("model"), max_retries=0)
    filtered_kwargs: dict = select_values(notnone, model_kwargs)  # type: ignore'''
if old not in text:
    raise SystemExit("AI-Scientist-v2 injected-model routing insertion point not found")
text = text.replace(old, new, 1)
old = '''    messages = opt_messages_to_list(system_message, user_message)

    if func_spec is not None:'''
new = '''    messages = opt_messages_to_list(system_message, user_message)
    if system_message and user_message is None:
        messages = [{"role": "user", "content": system_message}]

    if func_spec is not None:'''
if old not in text:
    raise SystemExit("AI-Scientist-v2 system-only message projection insertion point not found")
backend_path.write_text(text.replace(old, new, 1), encoding="utf-8")

interpreter_path = Path(sys.argv[10])
# Shared adapter (patch_ai_scientist_v2_common.py) already handles:
# - interpreter global_scope (__name__, __file__)
# Skip the inline patch to avoid conflict.
interpreter_path.write_text(interpreter_path.read_text(encoding="utf-8"), encoding="utf-8")
PY
rm -f ai_scientist/ideas/babylm_topic.json
# Increase max_tokens to avoid truncation of long GPT responses
python3 -c "
from pathlib import Path
llm = Path('ai_scientist/llm.py')
text = llm.read_text()
text = text.replace('MAX_NUM_TOKENS = 4096', 'MAX_NUM_TOKENS = 16384')
llm.write_text(text)
print('Increased MAX_NUM_TOKENS to 16384')
"
mkdir -p ai_scientist/ideas
cat > ai_scientist/ideas/babylm_topic.md <<'MARKDOWN'
# Title: Language Model Optimization for BabyLM Strict-Small

## Keywords
language model, autoregressive, BabyLM, perplexity, multi-domain

## TL;DR
Train language models on BabyLM Strict-Small. Compare 2-4 configurations, measure word-level perplexity.

## Abstract
This project trains language models on the BabyLM 2026 Strict-Small dataset (10M words, 6 domains). The framework selects the algorithm family, architecture, hyperparameters, and training procedure. The evaluation metric is word-level validation perplexity on a held-out split. The framework must compare 2-4 materially different configurations. The host does not prescribe an algorithm, architecture, hyperparameter, baseline, or experiment order. Use the dataset at /data/BabyLM-2026-Strict-Small. Write and lock research_idea.json before the first experiment. Write experiment_trace.json with word-level validation_perplexity for each experiment, and final_report.md.
MARKDOWN
timeout "${AI_SCIENTIST_V2_BABYLM_IDEATION_TIMEOUT_SECONDS:-1800}s" \
  python ai_scientist/perform_ideation_temp_free.py \
  --workshop-file ai_scientist/ideas/babylm_topic.md \
  --model "$OPENAI_MODEL" \
  --max-num-generations 1 \
  --num-reflections 2
test -s ai_scientist/ideas/babylm_topic.json
echo "AI_SCIENTIST_V2_BABYLM_IDEA_OK"
python3 - bfts_config.yaml "$OPENAI_MODEL" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])
model = sys.argv[2]
config = yaml.safe_load(path.read_text(encoding="utf-8"))
config["exp_name"] = "babylm"
config["generate_report"] = False
config["agent"]["num_workers"] = 1
config["agent"]["steps"] = 3
config["agent"]["stages"]["stage1_max_iters"] = 20
config["agent"]["search"]["num_drafts"] = 3
config["agent"]["search"]["debug_prob"] = 0.5
config["agent"]["search"]["max_debug_depth"] = 3
config["agent"]["multi_seed_eval"]["num_seeds"] = 1
config["agent"]["code"]["max_tokens"] = 16000
config["exec"]["timeout"] = 3600
for section in ("code", "feedback", "vlm_feedback"):
    config["agent"][section]["model"] = model
config["report"]["model"] = model
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
PY
timeout "${AI_SCIENTIST_V2_BABYLM_TIMEOUT_SECONDS:-14400}s" python launch_scientist_bfts.py \
  --load_ideas ai_scientist/ideas/babylm_topic.json \
  --idea_idx 0 \
  --skip_writeup \
  --skip_review \
  --model_agg_plots "$OPENAI_MODEL"
EOF
)
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
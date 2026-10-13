#!/usr/bin/env bash
set -euo pipefail
GPUS="${GPUS:-all}"
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-${BABYLM_MODEL:-gpt-5.4}}}"
export AI_RESEARCHER_COMPLETION_MODEL="${AI_RESEARCHER_COMPLETION_MODEL:-openai/${FRAMEWORK_MODEL_RAW}}"
export AI_RESEARCHER_CHEAP_MODEL="${AI_RESEARCHER_CHEAP_MODEL:-$AI_RESEARCHER_COMPLETION_MODEL}"
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_babylm_gpt_fullrun"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 01)}"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${AI_RESEARCHER_RUNTIME_IMAGE:-ai-researcher:runtime-ready}"
export FRAMEWORK_DISABLE_GPU="0"
export NVIDIA_DISABLE_REQUIRE=1
export FRAMEWORK_NATIVE_ENTRYPOINT="research_agent/run_infer_idea.py"
export FRAMEWORK_PROVIDER_INJECTION="COMPLETION_MODEL/CHEEP_MODEL/API_BASE_URL from the injected evaluation provider environment. GPUs available: 4x NVIDIA RTX PRO 5000 72GB."
export FRAMEWORK_NATIVE_LOG_MARKER="AI_RESEARCHER_BABYLM_GPT_NATIVE"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python research_agent/run_infer_idea.py --category babylm"
# Use unique port per run to avoid conflicts
AI_RESEARCHER_PORT="${AI_RESEARCHER_PORT:-$((12372 + RANDOM % 1000))}"
export FRAMEWORK_DOCKER_ARGS=$(cat <<EOF
-v
/var/run/docker.sock:/var/run/docker.sock
-e
COMPLETION_MODEL=$AI_RESEARCHER_COMPLETION_MODEL
-e
CHEEP_MODEL=$AI_RESEARCHER_CHEAP_MODEL
-e
BASE_IMAGES=${AI_RESEARCHER_EXEC_RUNTIME_IMAGE:-ai-researcher-exec:blackwell-25.11}
-e
GPUS=all
-e
PYTHONPATH=/workspace:/workspace/research_agent:/workspace/research_agent/inno/tools
-e
RESEARCHCLAWEVAL_DOCKER_HOST=host.docker.internal
-e
AI_RESEARCHER_REFERENCE_CATALOG_ONLY=1
-e
AI_RESEARCHER_PORT=$AI_RESEARCHER_PORT
-e
NVIDIA_DISABLE_REQUIRE=1
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AI_RESEARCHER_BABYLM_GPT_NATIVE"
echo "COMPLETION_MODEL=${COMPLETION_MODEL:-UNSET}"
# Patch setup_dataset, docker_env, PLATFORM, and mdconvert for BabyLM compatibility
python3 - \
  research_agent/inno/environment/utils.py \
  research_agent/inno/environment/docker_env.py \
  research_agent/constant.py \
  research_agent/inno/environment/markdown_browser/mdconvert.py <<'PY'
from pathlib import Path
import os, shutil, re

utilsp = Path(os.sys.argv[1])
text = utilsp.read_text(encoding="utf-8")
start = text.index("def setup_dataset(category: str, local_workplace: str):")
next_func = text.find("\ndef ", start + 4)
end = next_func if next_func >= 0 else len(text)
repl = """def setup_dataset(category: str, local_workplace: str):
    dataset_candidate_path = os.path.join(local_workplace, "dataset_candidate")
    if os.path.exists(dataset_candidate_path):
        return
    source_path = os.path.join("/workspace", "benchmark", "process", "dataset_candidate", category)
    if category == "babylm":
        real_dataset = os.environ.get("RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT")
        if not real_dataset or not os.path.isdir(real_dataset):
            raise RuntimeError(f"BabyLM dataset unavailable: {real_dataset}")
        os.makedirs(dataset_candidate_path, exist_ok=True)
        shutil.copy2(os.path.join(source_path, "metaprompt.py"), dataset_candidate_path)
        target = os.path.join(local_workplace, "project", "data", "BabyLM-2026-Strict-Small")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.exists(target):
            shutil.copytree(real_dataset, target)
        return
    shutil.copytree(source_path, dataset_candidate_path)
"""
utilsp.write_text(text[:start] + repl + text[end:], encoding="utf-8")

dockerp = Path(os.sys.argv[2])
text = dockerp.read_text(encoding="utf-8")
text = text.replace(
    '        self.docker_workplace = f"/{config.workplace_name}"',
    '        self.docker_workplace = "/workspace" if config.workplace_name == "." else f"/{config.workplace_name}"',
    1,
)
old_local = '        self.local_workplace = osp.join(config.local_root, config.workplace_name)'
new_local = '''        self.local_workplace = osp.join(config.local_root, config.workplace_name)
        host_workspace = os.getenv("RESEARCHCLAWEVAL_HOST_WORKSPACE", "")
        if host_workspace and os.path.normpath(self.local_workplace).startswith("/workspace"):
            self.local_workplace = os.path.join(host_workspace, os.path.normpath(self.local_workplace).removeprefix("/workspace").lstrip("/"))'''
if old_local in text:
    text = text.replace(old_local, new_local, 1)
old = "            \"--restart\", \"unless-stopped\", BASE_IMAGES"
if old in text:
    text = text.replace(old, '            "--restart", "unless-stopped", BASE_IMAGES', 1)
text = text.replace(
    "hostname = 'localhost'",
    "hostname = os.getenv('RESEARCHCLAWEVAL_DOCKER_HOST', 'localhost')",
    1,
)
text = text.replace(
    "assert port_info and (port_info[0] == port_info[1])",
    "assert port_info",
    1,
)
dockerp.write_text(text, encoding="utf-8")
dockerp2 = Path(os.sys.argv[2])
text2 = dockerp2.read_text(encoding="utf-8")
text2 = text2.replace(
    '        start_time = time.time()',
    '        start_time = time.time()\n        time.sleep(3)',
    1,
)
dockerp2.write_text(text2, encoding="utf-8")

constp = Path(os.sys.argv[3])
text = constp.read_text(encoding="utf-8")
if "PLATFORM =" not in text:
    constp.write_text(text + '\nPLATFORM = os.getenv("PLATFORM", "linux/amd64")\n', encoding="utf-8")

mdp = Path(os.sys.argv[4])
text = mdp.read_text(encoding="utf-8")
m = re.search(r"^(\s*)(from docling\.document_converter import DocumentConverter as DocLingDocumentConverter)", text, re.MULTILINE)
if m:
    ind = m.group(1)
    old = m.group(0)
    new = f"""{ind}try:
{ind}    from docling.document_converter import DocumentConverter as DocLingDocumentConverter
{ind}except ModuleNotFoundError:
{ind}    class DocLingDocumentConverter:
{ind}        def convert(self, *_args, **_kwargs):
{ind}            raise RuntimeError("docling is unavailable in this runtime")
"""
    mdp.write_text(text.replace(old, new, 1), encoding="utf-8")
PY
rm -f benchmark/process/dataset_candidate/babylm/reference_candidates.json
mkdir -p benchmark/process/dataset_candidate/babylm
cat > benchmark/process/dataset_candidate/babylm/reference_candidates.json <<'JSON'
{
  "candidates": [
    {
      "name": "BabyLM baseline (HuggingFace)",
      "url": "https://github.com/babylm/baseline-hf",
      "description": "Official HuggingFace BabyLM baseline training script"
    },
    {
      "name": "BabyLM evaluation pipeline",
      "url": "https://github.com/babylm/evaluation-pipeline",
      "description": "Official BabyLM strict evaluation pipeline"
    }
  ]
}
JSON
mkdir -p benchmark/final/babylm
cat > benchmark/final/babylm/babylm_10m.json <<'JSON'
{
  "target": "Neural Language Model Training for BabyLM Strict-Small",
  "instance_id": "babylm_10m",
  "authors": ["ResearchClawEval"],
  "year": 2026,
  "url": "https://babylm.github.io/",
  "abstract": "BabyLM 2026 Strict-Small word-level language modeling on the real dataset. The framework must choose and justify its own methods.",
  "venue": "ResearchClawEval",
  "topic": "language-modeling",
  "field": "babylm",
  "source_papers": [
    {
      "reference": "Attention Is All You Need (Vaswani et al. 2017)",
      "usage": "Foundation of Transformer architecture for neural language modeling."
    },
    {
      "reference": "BabyLM Challenge 2025: https://babylm.github.io/",
      "usage": "Task constraints and strict-small dataset budget."
    },
    {
      "reference": "HuggingFace Transformers: https://github.com/huggingface/transformers",
      "usage": "Reference implementation for neural language model training."
    }
  ],
  "task1": "Implement a neural language model using PyTorch. Train on the BabyLM Strict-Small dataset at /data/BabyLM-2026-Strict-Small. Evaluate word-level perplexity on a held-out validation split. Compare 2-4 materially different configurations.",
  "task2": "Design and implement neural language model experiments using PyTorch. Choose 2-4 materially different configurations, train them, evaluate word-level perplexity, select the best, and write research_idea.json, experiment_trace.json, and final_report.md."
}
JSON
cat > benchmark/process/dataset_candidate/babylm/metaprompt.py <<'PY'
TASK = "BabyLM 2026 Strict-Small: word-level language modeling on the real dataset."
DATASET = """
Use the real BabyLM 2026 Strict-Small dataset at /data/BabyLM-2026-Strict-Small.
"""
BASELINE = "No host-prescribed baseline. The framework must choose and justify its own methods."
COMPARISON = "Compare 2-4 materially distinct experiments under the same BabyLM data and epoch limits. The primary metric is WORD-LEVEL validation perplexity."
EVALUATION = "Write and lock research_idea.json before the first experiment. Run 2-4 experiments using the real dataset. Log word-level validation_perplexity for each experiment."
REF = "Do not use proxy scripts, toy datasets, or placeholder results."
METHOD_OWNERSHIP = "The framework owns the hypothesis, algorithm family, architecture, hyperparameters, experiment sequence, comparison, and selected method."
PY
timeout "${AI_RESEARCHER_BABYLM_TIMEOUT_SECONDS:-10800}s" \
  python research_agent/run_infer_idea.py \
  --instance_path benchmark/final/babylm/babylm_10m.json \
  --container_name "ai_researcher_babylm_${REAL_EVAL_RUN_ID}" \
  --model "openai/gpt-5.4" \
  --workplace_name "." \
  --cache_path "cache_${REAL_EVAL_RUN_ID}" \
  --port "${AI_RESEARCHER_PORT:-12372}" \
  --max_iter_times 0 \
  --category babylm
# Copy artifacts from inner container workspace to root workspace
for art in research_idea.json experiment_trace.json final_report.md; do
  found=$(find /workspace -name "$art" -type f 2>/dev/null | head -1)
  if [[ -n "$found" ]]; then
    cp "$found" "/workspace/$art"
    echo "AI_RESEARCHER_BABYLM_GPT_NATIVE: copied $art from $found"
  fi
done
EOF
)
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
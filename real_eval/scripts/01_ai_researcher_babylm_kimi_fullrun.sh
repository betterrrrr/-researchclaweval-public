#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-${BABYLM_MODEL:-kimi-k2.6}}}"
AI_RESEARCHER_COMPLETION_MODEL="${AI_RESEARCHER_COMPLETION_MODEL:-openai/${FRAMEWORK_MODEL_RAW}}"
AI_RESEARCHER_CHEAP_MODEL="${AI_RESEARCHER_CHEAP_MODEL:-$AI_RESEARCHER_COMPLETION_MODEL}"
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_babylm_kimi_fullrun"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 01)}"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${AI_RESEARCHER_RUNTIME_IMAGE:-ai-researcher:runtime-ready}"
export FRAMEWORK_DISABLE_GPU="0"
export FRAMEWORK_NATIVE_ENTRYPOINT="research_agent/run_infer_idea.py"
export FRAMEWORK_PROVIDER_INJECTION="COMPLETION_MODEL/CHEEP_MODEL/API_BASE_URL from the injected evaluation provider environment"
export FRAMEWORK_NATIVE_LOG_MARKER="AI_RESEARCHER_BABYLM_KIMI_NATIVE"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python research_agent/run_infer_idea.py --category babylm"
export PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
export BABYLM_MODEL="${FRAMEWORK_MODEL_RAW}"
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
GPUS="device=0,1,2,3"
-e
PYTHONPATH=/workspace
-e
RESEARCHCLAWEVAL_DOCKER_HOST=host.docker.internal
-e
AI_RESEARCHER_REFERENCE_CATALOG_ONLY=1
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AI_RESEARCHER_BABYLM_KIMI_NATIVE"
python3 - \
  research_agent/inno/environment/utils.py \
  research_agent/inno/environment/docker_env.py \
  research_agent/run_infer_idea.py \
  research_agent/inno/tools/__init__.py \
  research_agent/constant.py \
  research_agent/inno/environment/markdown_browser/mdconvert.py \
  research_agent/inno/environment/markdown_browser/requests_markdown_browser.py \
  research_agent/inno/workflow/flowcache.py \
  research_agent/inno/agents/inno_agent/prepare_agent.py \
  research_agent/inno/agents/inno_agent/exp_analyser.py \
  research_agent/inno/agents/inno_agent/ml_agent.py \
  research_agent/inno/agents/inno_agent/idea_agent.py \
  research_agent/inno/agents/inno_agent/judge_agent.py <<'PY'
from pathlib import Path
import sys

utils = Path(sys.argv[1])
text = utils.read_text(encoding="utf-8")
start = text.index("def setup_dataset(category: str, local_workplace: str):")
next_function = text.find("\ndef ", start + 4)
end = next_function if next_function >= 0 else len(text)
replacement = '''def setup_dataset(category: str, local_workplace: str):
    dataset_candidate_path = os.path.join(local_workplace, "dataset_candidate")
    if os.path.exists(dataset_candidate_path):
        return
    source_path = os.path.join(os.getcwd(), "benchmark", "process", "dataset_candidate", category)
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
'''
utils.write_text(text[:start] + replacement + text[end:], encoding="utf-8")

docker_env = Path(sys.argv[2])
text = docker_env.read_text(encoding="utf-8")
text = text.replace(
    '        self.docker_workplace = f"/{config.workplace_name}"',
    '        self.docker_workplace = "/workspace" if config.workplace_name == "." else f"/{config.workplace_name}"',
    1,
)
old = '''        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name, 
            "--user", "root", "-v", f"{self.local_workplace}:{self.docker_workplace}",
            "-w", f"{self.docker_workplace}", "-p", f"{self.communication_port}:8000", 
            "--restart", "unless-stopped", BASE_IMAGES
        ]'''
new = '''        host_workspace = os.getenv("RESEARCHCLAWEVAL_HOST_WORKSPACE", "")
        local_workplace = self.local_workplace
        if host_workspace and local_workplace.startswith("/workspace/"):
            local_workplace = os.path.join(host_workspace, local_workplace.removeprefix("/workspace/"))
        gpu_cmd = ["--gpus", GPUS] if GPUS else []
        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name, 
            "--user", "root", "-v", f"{local_workplace}:{self.docker_workplace}",
            "-w", f"{self.docker_workplace}", "-p", f"{self.communication_port}:8000", 
            "--restart", "unless-stopped", BASE_IMAGES
        ]'''
if old not in text:
    raise SystemExit("docker_command block not found")
text = text.replace(old, new, 1)
text = text.replace(
    "assert port_info and (port_info[0] == port_info[1])",
    "assert port_info",
)
text = text.replace(
    "hostname = 'localhost'",
    "hostname = os.getenv('RESEARCHCLAWEVAL_DOCKER_HOST', 'localhost')",
)
docker_env.write_text(text, encoding="utf-8")

entrypoint = Path(sys.argv[3])
text = entrypoint.read_text(encoding="utf-8")
# [FIX] Source already has main(args, "") - skip stale patch
# old = "    main(args)"
# new = "    main(args, references=\"\")"
# if old not in text:
#     raise SystemExit("main() call not found")
# text = text.replace(old, new, 1)
old = '        github_result = self.git_search({"metadata": metadata})'
new = '        github_result = "" if category == "babylm" else self.git_search({"metadata": metadata})'
if old not in text:
    raise SystemExit("git_search call not found")
entrypoint.write_text(text.replace(old, new, 1), encoding="utf-8")

tools = Path(sys.argv[4])
text = tools.read_text(encoding="utf-8")
old = "import_tools_recursively(current_dir, 'inno.tools')"
new = '''for module_name in (
    "terminal_tools",
    "inner",
    "inno_tools.planning_tools",
    "inno_tools.web_tools",
):
    importlib.import_module(f"research_agent.inno.tools.{module_name}")'''
if old not in text:
    raise SystemExit("tool registration insertion point not found")
text = text.replace(old, new, 1)
tools.write_text(text, encoding="utf-8")

constants = Path(sys.argv[5])
text = constants.read_text(encoding="utf-8")
if "PLATFORM =" not in text:
    constants.write_text(text + "\nPLATFORM = 'linux/amd64'\n", encoding="utf-8")

mdconvert = Path(sys.argv[6])
text = mdconvert.read_text(encoding="utf-8")
old = "from docling.document_converter import DocumentConverter as DocLingDocumentConverter"
new = '''try:
    from docling.document_converter import DocumentConverter as DocLingDocumentConverter
except ModuleNotFoundError:
    class DocLingDocumentConverter:
        def convert(self, *_args, **_kwargs):
            raise RuntimeError("docling is unavailable in this runtime")
'''
if old not in text:
    raise SystemExit("Docling import insertion point not found")
mdconvert.write_text(text.replace(old, new, 1), encoding="utf-8")

browser = Path(sys.argv[7])
text = browser.read_text(encoding="utf-8")
old = '        self._memory = PaperMemory(project_path="./paper_db", db_name=".paper_memory_" + platform, platform=platform, api_key=os.getenv("OPENAI_API_KEY"), embedding_model=\'text-embedding-3-small\')'
new = '''        class _NoopPaperMemory:
            def count(self, *_args, **_kwargs):
                return 1
            def add_paper_content(self, *_args, **_kwargs):
                return None
            def query_paper_content(self, *_args, **_kwargs):
                return []
        self._memory = _NoopPaperMemory()'''
if old not in text:
    raise SystemExit("PaperMemory initialization insertion point not found")
browser.write_text(text.replace(old, new, 1), encoding="utf-8")

flowcache = Path(sys.argv[8])
text = flowcache.read_text(encoding="utf-8")
old = "from langchain_community.embeddings import HuggingFaceEmbeddings"
new = "# langchain community embeddings not available"
text = text.replace(old, new, 1)
flowcache.write_text(text, encoding="utf-8")

prepare = Path(sys.argv[9])
text = prepare.read_text(encoding="utf-8")
old = "import openai"
new = "import openai\nimport os"
if old in text:
    text = text.replace(old, new, 1)
prepare.write_text(text, encoding="utf-8")

exp_analyser = Path(sys.argv[10])
text = exp_analyser.read_text(encoding="utf-8")
old = "import openai"
new = "import openai\nimport os"
if old in text:
    text = text.replace(old, new, 1)
exp_analyser.write_text(text, encoding="utf-8")

ml_agent = Path(sys.argv[11])
text = ml_agent.read_text(encoding="utf-8")
old = "import openai"
new = "import openai\nimport os"
if old in text:
    text = text.replace(old, new, 1)
ml_agent.write_text(text, encoding="utf-8")

idea_agent = Path(sys.argv[12])
text = idea_agent.read_text(encoding="utf-8")
old = "import openai"
new = "import openai\nimport os"
if old in text:
    text = text.replace(old, new, 1)
idea_agent.write_text(text, encoding="utf-8")

judge_agent = Path(sys.argv[13])
text = judge_agent.read_text(encoding="utf-8")
old = "import openai"
new = "import openai\nimport os"
if old in text:
    text = text.replace(old, new, 1)
judge_agent.write_text(text, encoding="utf-8")
PY
mkdir -p benchmark/final/babylm benchmark/process/dataset_candidate/babylm
cat > benchmark/final/babylm/babylm_10m.json <<'INST'
{
    "instance_id": "babylm_10m",
    "year": 2026,
    "url": "http://arxiv.org/abs/9999.99999",
    "abstract": "BabyLM 2026 Strict-Small is a benchmark for language modeling with limited data (10M words). Participants must train a neural language model on the provided text corpus and evaluate word-level perplexity.",
    "target": "BabyLM 2026 Strict-Small Language Modeling",
    "source_papers": [
        {
            "reference": "BabyLM: Exploring the Limits of Language Modeling with Small Data",
            "rank": 1,
            "type": ["methodological"],
            "justification": "This paper introduced the BabyLM challenge that defines the task, dataset, and evaluation protocol.",
            "usage": "The task definition, dataset structure, and evaluation metric are based on the BabyLM challenge specification."
        }
    ],
    "task1": "Design and train a neural language model on the BabyLM 2026 Strict-Small dataset. The dataset is available at /data/BabyLM-2026-Strict-Small (only .txt files, no separate validation set — split train/val yourself). The model must be a neural network (Transformer, LSTM, or similar), not an n-gram count-based model. The primary metric is word-level validation perplexity. Run 2-4 materially different configurations, compare by validation perplexity, and select the best. Write research_idea.json before the first experiment, then experiment_trace.json and final_report.md. The trace JSON must be strict — no NaN/Infinity.",
    "task2": "Write a report summarizing the experimental setup, results, and analysis.",
    "model": "neural_language_model",
    "dataset": "BabyLM-2026-Strict-Small",
    "metric": "word_level_validation_perplexity"
}
INST
cat > benchmark/process/dataset_candidate/babylm/metaprompt.py <<'PY'
TASK = "BabyLM 2026 Strict-Small real language-model training and evaluation."
DATASET = """
Use the real BabyLM 2026 Strict-Small dataset. In the execution container it is
available under all of these paths after setup:
- /data/BabyLM-2026-Strict-Small
- /workplace_<run_id>/dataset_candidate/BabyLM-2026-Strict-Small
- /workplace_<run_id>/project/data/BabyLM-2026-Strict-Small
- /workplace_<run_id>/project/dataset_candidate/BabyLM-2026-Strict-Small

DATASET LOADING RULES: The dataset has ONLY .txt files (train files, no separate validation set). Read all .txt files, filter by extension .txt, split train/val yourself. Do NOT silently catch file-reading exceptions — always log and raise. Verify loaded data is non-empty.
"""
BASELINE = "The framework must choose its own neural network approach. The host does not prescribe a baseline, algorithm, architecture, or experiment order. However, the model must be a neural network (Transformer, LSTM, or similar), not an n-gram count-based model."
COMPARISON = "Compare 2-4 materially different neural network configurations under the same BabyLM data and epoch limits. The primary metric is WORD-LEVEL validation perplexity. Character-level or subword-level perplexity is not accepted. Use PyTorch and HuggingFace Transformers for implementation."
EVALUATION = "Run BabyLM-compatible language-model evaluation using PyTorch. Compute word-level perplexity on a held-out validation split. Save metrics to JSON files. The JSON must be strict — no NaN/Infinity (convert to null). experiment_trace.json must include experiments array, idea_artifact, and idea_locked_before_experiments."
REF = "Do not use proxy scripts, sklearn toy datasets, n-gram models, old experiment outputs, or placeholder results. The model must be a neural network."
PY
timeout "${AI_RESEARCHER_BABYLM_TIMEOUT_SECONDS:-10800}s" \
  python research_agent/run_infer_idea.py \
  --instance_path benchmark/final/babylm/babylm_10m.json \
  --container_name "ai_researcher_babylm_${REAL_EVAL_RUN_ID}" \
  --model "$COMPLETION_MODEL" \
  --workplace_name "workplace_${REAL_EVAL_RUN_ID}" \
  --cache_path "cache_${REAL_EVAL_RUN_ID}" \
  --port "${AI_RESEARCHER_PORT:-12372}" \
  --max_iter_times 0 \
  --category babylm
for art in research_idea.json experiment_trace.json final_report.md; do
  found=$(find /workspace -name "$art" -type f 2>/dev/null | head -1)
  if [[ -n "$found" ]]; then
    cp "$found" "/workspace/$art"
    echo "AI_RESEARCHER_BABYLM_KIMI_NATIVE: copied $art from $found"
  fi
done
EOF
)
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
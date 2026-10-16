#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-${PSYDEFDETECT_EVAL_MODEL:-gpt-5.4}}}"
AI_RESEARCHER_COMPLETION_MODEL="${AI_RESEARCHER_COMPLETION_MODEL:-openai/${FRAMEWORK_MODEL_RAW}}"
AI_RESEARCHER_CHEAP_MODEL="${AI_RESEARCHER_CHEAP_MODEL:-$AI_RESEARCHER_COMPLETION_MODEL}"
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_psydefdetect_fullrun"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 01)}"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AI-Researcher/benchmark/final/psydefdetect/psydefdetect.json
AI-Researcher/benchmark/process/dataset_candidate/psydefdetect/metaprompt.py
AI-Researcher/benchmark/process/dataset_candidate/psydefdetect/reference_candidates.json
AI-Researcher/benchmark/process/dataset_candidate/psydefdetect/defense_mechanism_classification_in_supportive_conversations.tex
automation/psydefdetect_contract.md
automation/psydefdetect_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${AI_RESEARCHER_RUNTIME_IMAGE:-ai-researcher:runtime-ready}"
export FRAMEWORK_DISABLE_GPU="1"
export FRAMEWORK_NATIVE_ENTRYPOINT="research_agent/run_infer_idea.py"
export FRAMEWORK_PROVIDER_INJECTION="COMPLETION_MODEL/CHEEP_MODEL/API_BASE_URL from the injected evaluation provider environment"
export FRAMEWORK_NATIVE_LOG_MARKER="AI_RESEARCHER_NATIVE_INFER_IDEA"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python research_agent/run_infer_idea.py --category psydefdetect"
export FRAMEWORK_DOCKER_ARGS=$(cat <<EOF
-v
/var/run/docker.sock:/var/run/docker.sock
-e
COMPLETION_MODEL=$AI_RESEARCHER_COMPLETION_MODEL
-e
CHEEP_MODEL=$AI_RESEARCHER_CHEAP_MODEL
-e
BASE_IMAGES=${AI_RESEARCHER_EXEC_RUNTIME_IMAGE:-ai-researcher-exec:runtime-ready}
-e
GPUS=
-e
PYTHONPATH=/workspace
-e
RESEARCHCLAWEVAL_DOCKER_HOST=host.docker.internal
-e
AI_RESEARCHER_REFERENCE_CATALOG_ONLY=1
-e
AI_RESEARCHER_PSYDEFDETECT_COMPACT_ANALYSIS=1
-e
AI_RESEARCHER_PSYDEFDETECT_COMPACT_SURVEY=1
-e
AI_RESEARCHER_PSYDEFDETECT_COMPACT_JUDGEMENT=1
-e
AI_RESEARCHER_PSYDEFDETECT_COMPACT_EXECUTION=1
-e
AI_RESEARCHER_PSYDEFDETECT_LOCAL_EXPERIMENTS_ONLY=1
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AI_RESEARCHER_NATIVE_INFER_IDEA"
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
    source_path = os.path.join("..", "benchmark", "process", "dataset_candidate", category)
    if category == "psydefdetect":
        real_dataset = os.environ.get("RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT")
        if not real_dataset or not os.path.isdir(real_dataset):
            raise RuntimeError(f"PsyDefDetect dataset unavailable: {real_dataset}")
        os.makedirs(dataset_candidate_path, exist_ok=True)
        shutil.copy2(os.path.join(source_path, "metaprompt.py"), dataset_candidate_path)
        target = os.path.join(local_workplace, "project", "data", "psydefdetect")
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
        if host_workspace and os.path.normpath(local_workplace) == "/workspace":
            local_workplace = host_workspace
        extra_args = []
        host_dataset = os.getenv("RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT", "")
        host_contract = os.getenv("RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE", "")
        if host_dataset:
            extra_args.extend(["-v", f"{host_dataset}:/data/psydefdetect:ro"])
        if host_contract:
            extra_args.extend(["-v", f"{host_contract}:/input/psydefdetect_contract.md:ro"])
        if os.getenv("AI_RESEARCHER_PSYDEFDETECT_LOCAL_EXPERIMENTS_ONLY") != "1":
            for key in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "API_BASE_URL"):
                value = os.getenv(key)
                if value:
                    extra_args.extend(["-e", key])
        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",
            "--add-host", "host.docker.internal:host-gateway",
        ] + gpu_cmd + [
            "--name", self.container_name, "--user", "root",
            "-v", f"{local_workplace}:{self.docker_workplace}",
        ] + extra_args + [
            "-w", self.docker_workplace, "-p", f"{self.communication_port}:8000",
            "--restart", "unless-stopped", BASE_IMAGES,
        ]'''
if old not in text:
    raise SystemExit("AI-Researcher Docker command block not found")
docker_env.write_text(text.replace(old, new, 1), encoding="utf-8")
text = docker_env.read_text(encoding="utf-8")
text = text.replace(
    "assert port_info and (port_info[0] == port_info[1])",
    "assert port_info",
    1,
)
text = text.replace(
    "hostname = 'localhost'",
    "hostname = os.getenv('RESEARCHCLAWEVAL_DOCKER_HOST', 'localhost')",
    1,
)
docker_env.write_text(text, encoding="utf-8")

entrypoint = Path(sys.argv[3])
text = entrypoint.read_text(encoding="utf-8")
old = '        github_result = self.git_search({"metadata": metadata})'
new = '''        if category == "psydefdetect":
            candidate_path = Path(__file__).resolve().parents[1] / "benchmark" / "process" / "dataset_candidate" / category / "reference_candidates.json"
            github_result = candidate_path.read_text(encoding="utf-8")
        else:
            github_result = self.git_search({"metadata": metadata})'''
if old not in text:
    raise SystemExit("AI-Researcher GitHub candidate insertion point not found")
text = text.replace(old, new, 1)
if "from pathlib import Path" not in text:
    text = "from pathlib import Path\n" + text
old = '        metadata = self.load_ins({"instance_path": instance_path, "task_level": task_level})'
new = old + '\n        if category == "psydefdetect" and not references:\n            references = warp_source_papers(metadata["source_papers"])'
if old not in text:
    raise SystemExit("AI-Researcher reference projection insertion point not found")
text = text.replace(old, new, 1)
text = text.replace(
    '            "working_dir": workplace_name, # TODO: change to the codebase path',
    '            "working_dir": "workspace" if category == "psydefdetect" else workplace_name,',
    1,
)
text = text.replace(
    '        prepare_messages, context_variables = await self.prepare_agent(messages, context_variables)',
    '        prepare_messages, context_variables = await self.prepare_agent(messages, context_variables, max_turns=int(os.getenv("AI_RESEARCHER_PREPARE_MAX_TURNS", "8")))',
    1,
)
old = '        prepare_dict = extract_json_from_output(prepare_res)'
new = '''        prepare_dict = context_variables.get("prepare_result") or extract_json_from_output(prepare_res)
        if not prepare_dict or "reference_papers" not in prepare_dict:
            raise RuntimeError("Prepare Agent did not select reference inputs within its turn budget")'''
if old not in text:
    raise SystemExit("AI-Researcher Prepare result validation insertion point not found")
text = text.replace(old, new, 1)
old = '        download_res = self.download_papaer({"paper_list": paper_list, "local_root": local_root, "workplace_name": workplace_name})'
new = '''        if category == "psydefdetect":
            paper_name = "defense_mechanism_classification_in_supportive_conversations.tex"
            paper_source = Path(__file__).resolve().parents[1] / "benchmark" / "process" / "dataset_candidate" / category / paper_name
            paper_target = Path(local_root) / workplace_name / "papers" / paper_name
            paper_target.parent.mkdir(parents=True, exist_ok=True)
            paper_target.write_text(paper_source.read_text(encoding="utf-8"), encoding="utf-8")
            download_res = f"Benchmark concept reference is available at /workspace/papers/{paper_name}"
        else:
            download_res = self.download_papaer({"paper_list": paper_list, "local_root": local_root, "workplace_name": workplace_name})'''
if old not in text:
    raise SystemExit("AI-Researcher local paper projection insertion point not found")
text = text.replace(old, new, 1)
agent_turn_budgets = {
    'await self.idea_agent(messages, context_variables)': 'await self.idea_agent(messages, context_variables, max_turns=4)',
    'await self.idea_agent(messages, context_variables, iter_times=i+1)': 'await self.idea_agent(messages, context_variables, iter_times=i+1, max_turns=4)',
    'await self.idea_agent(messages, context_variables, iter_times="select")': 'await self.idea_agent(messages, context_variables, iter_times="select", max_turns=4)',
    'await self.code_survey_agent(messages, context_variables)': 'await self.code_survey_agent(messages, context_variables, max_turns=4)',
    'await self.coding_plan_agent(messages, context_variables)': 'await self.coding_plan_agent(messages, context_variables, max_turns=30)',
    'await self.ml_agent(messages, context_variables)': 'await self.ml_agent(messages, context_variables, max_turns=48)',
    'await self.judge_agent(input_messages, context_variables)': 'await self.judge_agent(input_messages, context_variables, max_turns=4)',
    'await self.ml_agent(judge_messages, context_variables, iter_times=i+1)': 'await self.ml_agent(judge_messages, context_variables, iter_times=i+1, max_turns=40)',
    'await self.judge_agent(judge_messages, context_variables, iter_times=i+1)': 'await self.judge_agent(judge_messages, context_variables, iter_times=i+1, max_turns=4)',
    'await self.ml_agent(judge_messages, context_variables, iter_times="submit")': 'await self.ml_agent(judge_messages, context_variables, iter_times="submit", max_turns=12)',
    'await self.exp_analyser(judge_messages, context_variables, iter_times=f"refine_{i+1}")': 'await self.exp_analyser(judge_messages, context_variables, iter_times=f"refine_{i+1}", max_turns=30)',
    'await self.ml_agent(judge_messages, context_variables, iter_times=f"refine_{i+1}")': 'await self.ml_agent(judge_messages, context_variables, iter_times=f"refine_{i+1}", max_turns=80)',
}
for old_call, new_call in agent_turn_budgets.items():
    if old_call not in text:
        raise SystemExit(f"AI-Researcher agent turn-budget insertion point not found: {old_call}")
    text = text.replace(old_call, new_call, 1)
old = '    file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root=env_config.local_root, workplace_name=env_config.workplace_name, downloads_folder=os.path.join(env_config.local_root, env_config.workplace_name, "downloads"))'
new = '''    if args.category == "psydefdetect":
        file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root="/", workplace_name="workspace", downloads_folder="/workspace/downloads")
    else:
        file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root=env_config.local_root, workplace_name=env_config.workplace_name, downloads_folder=os.path.join(env_config.local_root, env_config.workplace_name, "downloads"))'''
if old not in text:
    raise SystemExit("AI-Researcher file browser root insertion point not found")
text = text.replace(old, new, 1)
old = 'local_root = os.path.join(os.getcwd(),"workplace_paper" , f"task_{instance_id}" + "_" + COMPLETION_MODEL.replace("/", "__"),  args.workplace_name)'
if old not in text:
    raise SystemExit("AI-Researcher local_root assignment not found")
text = text.replace(old, 'local_root = "/workspace"\n    args.workplace_name = "."', 1)
text = text.replace("    main(args)\n", "    main(args, references=\"\")\n", 1)
entrypoint.write_text(text, encoding="utf-8")

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
    raise SystemExit("AI-Researcher tool registration insertion point not found")
tools.write_text(text.replace(old, new, 1), encoding="utf-8")

constants = Path(sys.argv[5])
text = constants.read_text(encoding="utf-8")
if "PLATFORM =" not in text:
    constants.write_text(text + '\nPLATFORM = os.getenv("PLATFORM", "linux/amd64")\n', encoding="utf-8")

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
    raise SystemExit("AI-Researcher Docling import insertion point not found")
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
    raise SystemExit("AI-Researcher PaperMemory insertion point not found")
browser.write_text(text.replace(old, new, 1), encoding="utf-8")
text = browser.read_text(encoding="utf-8")
old = '''        if self._current_page_path is None:
            raise FileNotFoundError("No file is opened, please open a file first.")
        collection = self._current_page_path.split("/")[-1].replace(".", "_dot_")'''
new = '''        if self._current_page_path is None:
            raise FileNotFoundError("No file is opened, please open a file first.")
        if os.getenv("AI_RESEARCHER_REFERENCE_CATALOG_ONLY") == "1":
            return self.page_content
        collection = self._current_page_path.split("/")[-1].replace(".", "_dot_")'''
if old not in text:
    raise SystemExit("AI-Researcher compact page retrieval insertion point not found")
browser.write_text(text.replace(old, new, 1), encoding="utf-8")

flowcache = Path(sys.argv[8])
text = flowcache.read_text(encoding="utf-8")
old = '    async def __call__(self, messages: List[Dict], context_variables: Dict, iter_times: int = None, *args, **kwargs):\n        # messages = [{"role": "user", "content": query}]'
new = old + '\n        max_turns = kwargs.pop("max_turns", float("inf"))'
if old not in text:
    raise SystemExit("AI-Researcher AgentModule turn-budget insertion point not found")
text = text.replace(old, new, 1)
old = 'response = await self.client.run_async(self.agent, messages, context_variables=context_variables, debug=True)'
if text.count(old) != 2:
    raise SystemExit("AI-Researcher AgentModule run_async call count changed")
text = text.replace(old, old[:-1] + ', max_turns=max_turns)', 2)
flowcache.write_text(text, encoding="utf-8")

prepare_agent = Path(sys.argv[9])
text = prepare_agent.read_text(encoding="utf-8")
if "import os\n" not in text:
    text = "import os\n" + text
old = '    tools = [gen_code_tree_structure, read_file, execute_command, case_resolved, terminal_page_down, terminal_page_up, terminal_page_to]'
new = '''    catalog_only = os.getenv("AI_RESEARCHER_REFERENCE_CATALOG_ONLY") == "1"
    if catalog_only:
        tools = [case_resolved]
    else:
        tools = [gen_code_tree_structure, read_file, execute_command, case_resolved, terminal_page_down, terminal_page_up, terminal_page_to]'''
if old not in text:
    raise SystemExit("AI-Researcher Prepare tool-list insertion point not found")
text = text.replace(old, new, 1)
old = '      return f"""\nYou are given a list of papers, searching results of the papers on GitHub, and innovative ideas according to the papers. Your working directory is `/{working_dir}`, you can only access files in this directory.'
new = '''      if os.getenv("AI_RESEARCHER_REFERENCE_CATALOG_ONLY") == "1":
        return f"""
You are selecting reference inputs for a fixed local benchmark. The user message contains the complete compact candidate catalog and conceptual source-paper context.

Compare the candidates by relevance to psychological defense mechanism dialogue classification. Select at least five candidates yourself. Do not clone repositories, access the network, scan the workspace, or run experiments in this preparation stage. Use each selected repository URL as its reference path. The `reference_papers` list must contain the supplied source-paper title exactly once, independent of the repository count. Call `case_resolved` with your selection now. The benchmark host supplied candidates but did not select them for you.
        """
      return f"""
You are given a list of papers, searching results of the papers on GitHub, and innovative ideas according to the papers. Your working directory is `/{working_dir}`, you can only access files in this directory.'''
if old not in text:
    raise SystemExit("AI-Researcher Prepare catalog instructions insertion point not found")
prepare_agent.write_text(text.replace(old, new, 1), encoding="utf-8")

ml_agent = Path(sys.argv[11])
text = ml_agent.read_text(encoding="utf-8")
if "import os\n" not in text:
    text = "import os\n" + text
if "import json\n" not in text:
    text = "import json\n" + text
if "from functools import wraps\n" not in text:
    text = "from functools import wraps\n" + text
if "from pathlib import Path\n" not in text:
    text = "from pathlib import Path\n" + text
old = '''    def instructions(context_variables):
      working_dir = context_variables.get("working_dir", None)
      return f"""\\
You are a machine learning engineer tasked with implementing innovative ML projects.'''
new = '''    def instructions(context_variables):
      working_dir = context_variables.get("working_dir", None)
      if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_EXECUTION") == "1":
        return f"""\\
You are AI-Researcher's Machine Learning Agent executing the fixed PsyDefDetect benchmark in `/{working_dir}`.

Act on the supplied implementation task immediately. Do not repeatedly list or inspect the project directory. Use the framework tools to create the experiment code, then execute it synchronously. Use only the mounted PsyDefDetect dataset and fixed split. Select exactly two materially different experiments yourself, score both with the supplied local scorer, select the better valid result, and promote predictions.jsonl or submission.csv, score.json, experiment_trace.json, and final_report.md to `/{working_dir}`. Write a framework-authored research_idea.json before the first experiment. The host does not prescribe an algorithm, feature representation, architecture, hyperparameter, baseline, or experiment order.

Use only installed local packages. Experiment code must not import requests/openai or make remote API calls; the outer AI-Researcher agent already uses the injected evaluation provider for planning and code generation. Do not download models, install packages, start background jobs, or poll. Invoke `run_psydefdetect_local_score.py` through execute_command with all required CLI arguments; run_python cannot pass those scorer arguments and must not be used for the scorer. The trace must contain exactly two experiment objects whose string `id` fields are exactly `exp1` and `exp2`; `selected_experiment_id` must equal whichever of those two ids has the higher observed score. At the trace TOP LEVEL, as siblings of experiments, record framework_native_execution=true, consumed_topic_input=true, workspace_trace_root="/workspace", framework_internal_model="{os.getenv('OPENAI_MODEL', '')}", and framework_internal_api_base_url="{os.getenv('OPENAI_BASE_URL', '')}". score.json must contain only psydefdetect_score and score_key; do not retype accuracy or other metrics. After both scores exist, do not inspect the workspace again. Call write_psydefdetect_handoff with your selected id and your complete score JSON, trace JSON, and final report text; then immediately call complete_psydefdetect with a concise evidence summary. Do not inspect samples or start another experiment after the handoff exists.
"""
      return f"""\\
You are a machine learning engineer tasked with implementing innovative ML projects.'''
if old not in text:
    raise SystemExit("AI-Researcher compact ML instruction insertion point not found")
text = text.replace(old, new, 1)
old = '''    tools = [gen_code_tree_structure, execute_command, read_file, create_file, write_file, list_files, create_directory, run_python, case_resolved, case_not_resolved, terminal_page_down, terminal_page_up, terminal_page_to]
    tools = [with_env(code_env)(tool) if 'env' in signature(tool).parameters else tool for tool in tools]
    
    return Agent('''
new = '''    tools = [gen_code_tree_structure, execute_command, read_file, create_file, write_file, list_files, create_directory, run_python, case_resolved, case_not_resolved, terminal_page_down, terminal_page_up, terminal_page_to]
    tools = [with_env(code_env)(tool) if 'env' in signature(tool).parameters else tool for tool in tools]
    if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_EXECUTION") == "1":
        tools = [gen_code_tree_structure, execute_command, create_file, write_file, create_directory, run_python, case_resolved, case_not_resolved]
        tools = [with_env(code_env)(tool) if 'env' in signature(tool).parameters else tool for tool in tools]
        required_artifacts = tuple(
            Path("/workspace") / name
            for name in (
                "predictions.jsonl",
                "score.json",
                "experiment_trace.json",
                "final_report.md",
            )
        )

        def experiment_evidence():
            score_paths = (
                Path("/workspace/score_exp1.json"),
                Path("/workspace/score_exp2.json"),
            )
            prediction_paths = (
                Path("/workspace/predictions_exp1.jsonl"),
                Path("/workspace/predictions_exp2.jsonl"),
            )
            if not all(path.is_file() for path in score_paths + prediction_paths):
                return None
            try:
                scores = [
                    float(json.loads(path.read_text(encoding="utf-8"))["psydefdetect_score"])
                    for path in score_paths
                ]
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                return None
            best_index = max(range(2), key=scores.__getitem__)
            return {
                "scores": scores,
                "best_id": f"exp{best_index + 1}",
                "best_score": scores[best_index],
                "best_predictions": prediction_paths[best_index],
            }

        def delivery_instruction():
            evidence = experiment_evidence()
            if evidence is None:
                return "Run and officially score exactly two local experiments before completing."
            trace_shape = {
                "framework_native_execution": True,
                "consumed_topic_input": True,
                "workspace_trace_root": "/workspace",
                "framework_internal_model": os.getenv("OPENAI_MODEL", ""),
                "framework_internal_api_base_url": os.getenv("OPENAI_BASE_URL", ""),
                "selected_experiment_id": evidence["best_id"],
                "experiments": [
                    {"id": "exp1", "score": evidence["scores"][0]},
                    {"id": "exp2", "score": evidence["scores"][1]},
                ],
            }
            return (
                f"Both experiments are scored: exp1={evidence['scores'][0]:.12g}, "
                f"exp2={evidence['scores'][1]:.12g}; {evidence['best_id']} is the required selection. "
                "Do not call read_file, list_files, execute_command, or run_python again. Call "
                "write_psydefdetect_handoff now with selected_experiment_id, a score_json object string "
                "containing ONLY psydefdetect_score and score_key, plus your final_report Markdown. "
                "The experiment_trace_json MUST use this TOP-LEVEL shape (fill in the two observed "
                f"scores exactly): {json.dumps(trace_shape, separators=(',', ':'))}. "
                "The native/provider keys must be siblings of experiments, never only inside each "
                "experiment. Report only the two official macro-F1 scores; do not invent accuracy or "
                "other metrics."
            )

        def handoff_status():
            if not all(path.is_file() for path in required_artifacts):
                return None
            try:
                trace = json.loads(required_artifacts[2].read_text(encoding="utf-8"))
                root_score = json.loads(required_artifacts[1].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return f"root handoff JSON is invalid: {exc}"
            experiments = trace.get("experiments")
            experiment_ids = {
                item.get("id")
                for item in experiments or []
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
            }
            selected_id = trace.get("selected_experiment_id")
            evidence = experiment_evidence()
            selected_item = next(
                (
                    item
                    for item in experiments or []
                    if isinstance(item, dict) and item.get("id") == selected_id
                ),
                None,
            )
            selected_score = selected_item.get("score") if isinstance(selected_item, dict) else None
            if isinstance(selected_score, dict):
                selected_score = selected_score.get("psydefdetect_score")
            root_score_value = root_score.get("psydefdetect_score") if isinstance(root_score, dict) else None
            required_top_level = {
                "framework_native_execution": True,
                "consumed_topic_input": True,
                "workspace_trace_root": "/workspace",
                "framework_internal_model": os.getenv("OPENAI_MODEL"),
                "framework_internal_api_base_url": os.getenv("OPENAI_BASE_URL"),
            }
            missing_top_level = [
                key for key, expected in required_top_level.items()
                if trace.get(key) != expected
            ]
            unverified_experiment_metrics = [
                key
                for item in experiments or []
                if isinstance(item, dict)
                for key in ("accuracy", "macro_f1_positive_1_8", "macro_f1_all_0_8")
                if key in item
            ]
            valid = (
                evidence is not None
                and isinstance(experiments, list)
                and len(experiments) == 2
                and len(experiment_ids) == 2
                and isinstance(selected_id, str)
                and selected_id.strip() in experiment_ids
                and selected_id == evidence["best_id"]
                and isinstance(selected_score, (int, float))
                and abs(float(selected_score) - evidence["best_score"]) < 1e-12
                and isinstance(root_score_value, (int, float))
                and abs(float(root_score_value) - evidence["best_score"]) < 1e-12
                and set(root_score) == {"psydefdetect_score", "score_key"}
                and root_score.get("score_key") == "psydefdetect_score"
                and required_artifacts[0].read_bytes() == evidence["best_predictions"].read_bytes()
                and not missing_top_level
                and not unverified_experiment_metrics
            )
            if not valid:
                if missing_top_level:
                    return (
                        "experiment_trace.json must place these keys at the TOP LEVEL as siblings "
                        "of experiments and selected_experiment_id: "
                        + ", ".join(missing_top_level)
                        + ". Call write_file on /workspace/experiment_trace.json now; do not put "
                        "these fields only inside experiment objects."
                    )
                if (
                    not isinstance(root_score, dict)
                    or set(root_score) != {"psydefdetect_score", "score_key"}
                ):
                    return (
                        "score.json must contain ONLY psydefdetect_score and score_key from the "
                        "official selected score. Remove retyped accuracy or other metrics with write_file."
                    )
                if unverified_experiment_metrics:
                    return (
                        "experiment_trace.json contains retyped non-primary metrics that are not "
                        "accepted evidence. Keep each experiment's id, score, description/config/path "
                        "evidence only, then rewrite the trace."
                    )
                return (
                    "The root handoff fails the required contract: select the higher observed score, make score.json and "
                    "predictions.jsonl match that experiment, record two unique ids/scores, and preserve native/topic/model/base-url fields."
                )
            return "complete"

        def write_psydefdetect_handoff(
            selected_experiment_id: str,
            score_json: str,
            experiment_trace_json: str,
            final_report: str,
        ):
            """Write the framework-authored four-file handoff after both official scores exist."""
            evidence = experiment_evidence()
            if evidence is None:
                return "Run and officially score exactly two experiments before writing the handoff."
            if selected_experiment_id != evidence["best_id"]:
                return (
                    f"selected_experiment_id must be {evidence['best_id']} because it has the "
                    "higher observed official score."
                )
            try:
                score_payload = json.loads(score_json)
                trace_payload = json.loads(experiment_trace_json)
            except (TypeError, json.JSONDecodeError) as exc:
                return f"score_json and experiment_trace_json must be valid JSON objects: {exc}"
            if not isinstance(score_payload, dict) or not isinstance(trace_payload, dict):
                return "score_json and experiment_trace_json must each encode one JSON object."
            root_score = score_payload.get("psydefdetect_score")
            if (
                not isinstance(root_score, (int, float))
                or abs(float(root_score) - evidence["best_score"]) >= 1e-12
                or score_payload.get("score_key") != "psydefdetect_score"
                or set(score_payload) != {"psydefdetect_score", "score_key"}
            ):
                return (
                    "score_json must contain ONLY the selected official psydefdetect_score and "
                    'score_key="psydefdetect_score"; do not retype other metrics.'
                )
            experiments = trace_payload.get("experiments")
            if not isinstance(experiments, list) or len(experiments) != 2:
                return "experiment_trace_json must contain exactly two experiment objects."
            experiment_ids = {
                item.get("id")
                for item in experiments
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            observed_scores = {}
            for item in experiments:
                if not isinstance(item, dict):
                    continue
                value = item.get("score")
                if isinstance(value, dict):
                    value = value.get("psydefdetect_score")
                if isinstance(value, (int, float)):
                    observed_scores[item.get("id")] = float(value)
            observed_scores_match = (
                set(observed_scores) == {"exp1", "exp2"}
                and abs(observed_scores["exp1"] - evidence["scores"][0]) < 1e-12
                and abs(observed_scores["exp2"] - evidence["scores"][1]) < 1e-12
            )
            trace_valid = (
                experiment_ids == {"exp1", "exp2"}
                and observed_scores_match
                and trace_payload.get("selected_experiment_id") == evidence["best_id"]
                and trace_payload.get("framework_native_execution") is True
                and trace_payload.get("consumed_topic_input") is True
                and trace_payload.get("workspace_trace_root") == "/workspace"
                and trace_payload.get("framework_internal_model") == os.getenv("OPENAI_MODEL")
                and trace_payload.get("framework_internal_api_base_url")
                == os.getenv("OPENAI_BASE_URL")
                and not any(
                    key in item
                    for item in experiments
                    for key in (
                        "accuracy",
                        "macro_f1_positive_1_8",
                        "macro_f1_all_0_8",
                    )
                )
            )
            if not trace_valid:
                return (
                    "experiment_trace_json must record exact exp1/exp2 official scores, select the "
                    "higher score, and preserve the required native/topic/model/base-url fields."
                )
            report_text = str(final_report).strip()
            if (
                len(report_text) < 160
                or "exp1" not in report_text
                or "exp2" not in report_text
                or evidence["best_id"] not in report_text
                or not any(
                    marker in report_text.lower()
                    for marker in ("psydefdetect", "defense mechanism")
                )
            ):
                return (
                    "final_report must be substantive, on-topic, and discuss exp1, exp2, and the selected experiment."
                )
            required_artifacts[0].write_bytes(evidence["best_predictions"].read_bytes())
            required_artifacts[1].write_text(score_json.strip() + "\\n", encoding="utf-8")
            required_artifacts[2].write_text(
                experiment_trace_json.strip() + "\\n", encoding="utf-8"
            )
            required_artifacts[3].write_text(report_text + "\\n", encoding="utf-8")
            status = handoff_status()
            if status != "complete":
                return status or "The written handoff is incomplete; correct the supplied payloads."
            return (
                f"Valid PsyDefDetect handoff written for {evidence['best_id']} with "
                f"psydefdetect_score={evidence['best_score']:.12g}. Call complete_psydefdetect now."
            )

        seen_tool_calls = set()

        def stop_after_handoff(tool):
            if tool.__name__ == "case_not_resolved":
                return tool

            if tool.__name__ == "case_resolved":
                def complete_psydefdetect(*args, **kwargs):
                    status = handoff_status()
                    if status == "complete":
                        return tool(*args, **kwargs)
                    if status is not None:
                        return status + " Use write_file to correct the handoff before completing."
                    return delivery_instruction() + " Complete those physical files before completing."

                complete_psydefdetect.__doc__ = (
                    "Finish the PsyDefDetect task only after the complete validated root handoff exists."
                )
                complete_psydefdetect.__signature__ = signature(tool)
                return complete_psydefdetect

            @wraps(tool)
            def guarded(*args, **kwargs):
                status = handoff_status()
                if status is not None:
                    if status != "complete" and tool.__name__ == "write_file":
                        return tool(*args, **kwargs)
                    if status != "complete":
                        return (
                            status
                            + " Use write_file only to correct experiment_trace.json; do not inspect data or run another experiment."
                        )
                    return (
                        "The valid four-file PsyDefDetect handoff already exists. "
                        "Do not inspect data, run commands, or start another experiment; call complete_psydefdetect now with the two scores and selected id."
                    )

                evidence = experiment_evidence()
                if evidence is not None:
                    if tool.__name__ in {"create_file", "write_file"}:
                        return tool(*args, **kwargs)
                    command = str(kwargs.get("command") or (args[0] if args else "")).strip()
                    allowed_copy = (
                        tool.__name__ == "execute_command"
                        and command
                        == f"cp {evidence['best_predictions']} /workspace/predictions.jsonl"
                    )
                    if allowed_copy:
                        return tool(*args, **kwargs)
                    return delivery_instruction()

                code_path = kwargs.get("code_path") or (args[0] if args else None)
                if tool.__name__ == "run_python" and str(code_path).endswith(
                    "run_psydefdetect_local_score.py"
                ):
                    return (
                        "run_python cannot supply the scorer's required CLI arguments. "
                        "Use execute_command once with --dataset-root, --split-manifest, --predictions, and --output-score."
                    )
                call_key = (
                    tool.__name__,
                    json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=repr),
                )
                if call_key in seen_tool_calls:
                    return (
                        "This exact tool call already ran and is blocked as a duplicate. "
                        "Do not repeat it; choose the next concrete step toward the two experiments and valid handoff."
                    )
                seen_tool_calls.add(call_key)
                return tool(*args, **kwargs)

            guarded.__signature__ = signature(tool)
            return guarded

        tools = [stop_after_handoff(tool) for tool in tools]
        tools.append(write_psydefdetect_handoff)

    return Agent('''
if old not in text:
    raise SystemExit("AI-Researcher post-handoff tool guard insertion point not found")
ml_agent.write_text(text.replace(old, new, 1), encoding="utf-8")
compile(ml_agent.read_text(encoding="utf-8"), str(ml_agent), "exec")

idea_agent = Path(sys.argv[12])
text = idea_agent.read_text(encoding="utf-8")
if "import os\n" not in text:
    text = "import os\n" + text
old = '''    def instructions(context_variables):
        return f"""\\
You are an `Idea Generation Agent` specialized in analyzing academic papers located in `{file_env.docker_workplace}/papers/` and generating innovative ideas.'''
new = '''    def instructions(context_variables):
        if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_SURVEY") == "1":
            return """\\
You are AI-Researcher's Idea Generation Agent for the fixed PsyDefDetect benchmark. The user message already contains the complete conceptual reference and task contract. Do not browse files or call navigation tools. Produce one concise, feasible research idea and choose exactly two materially different experiments from the installed local resources. Explain the hypothesis, method rationale, failure modes, comparison, and selection criterion, then return the idea directly in this turn. Do not copy a host-prescribed algorithm.
"""
        return f"""\\
You are an `Idea Generation Agent` specialized in analyzing academic papers located in `{file_env.docker_workplace}/papers/` and generating innovative ideas.'''
if old not in text:
    raise SystemExit("AI-Researcher compact idea instructions insertion point not found")
text = text.replace(old, new, 1)
old = '''    tool_list = [
        open_local_file,
        page_up_markdown,
        page_down_markdown,
        find_on_page_ctrl_f,
        find_next,
        question_answer_on_whole_page,
    ]'''
new = '''    if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_SURVEY") == "1":
        tool_list = []
    else:
        tool_list = [
            open_local_file,
            page_up_markdown,
            page_down_markdown,
            find_on_page_ctrl_f,
            find_next,
            question_answer_on_whole_page,
        ]'''
if old not in text:
    raise SystemExit("AI-Researcher compact idea tool-list insertion point not found")
text = text.replace(old, new, 1)
old = '''    def instructions(context_variables):
        return f"""\\
You are a `Code Survey Agent` specialized in analyzing code implementations of innovative ideas.'''
new = '''    def instructions(context_variables):
        if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_SURVEY") == "1":
            return """\\
You are AI-Researcher's Code Survey Agent for the fixed PsyDefDetect benchmark. Do not inspect directories or external codebases. Based on the framework-authored idea supplied in the user message, return a concise implementation report for exactly two installed-library local experiments chosen by the framework. Include fixed-split scoring, evidence-based selection, research_idea.json-before-execution, and root-level artifact delivery requirements. Return the report directly in this turn.
"""
        return f"""\\
You are a `Code Survey Agent` specialized in analyzing code implementations of innovative ideas.'''
if old not in text:
    raise SystemExit("AI-Researcher compact code-survey instructions insertion point not found")
text = text.replace(old, new, 1)
old = '''    tool_list = [
        gen_code_tree_structure,
        read_file,
        terminal_page_down,
        terminal_page_up,
        terminal_page_to, 
        list_files
    ]'''
new = '''    if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_SURVEY") == "1":
        tool_list = []
    else:
        tool_list = [
            gen_code_tree_structure,
            read_file,
            terminal_page_down,
            terminal_page_up,
            terminal_page_to,
            list_files,
        ]'''
if old not in text:
    raise SystemExit("AI-Researcher compact code-survey tool-list insertion point not found")
idea_agent.write_text(text.replace(old, new, 1), encoding="utf-8")

judge_agent = Path(sys.argv[13])
text = judge_agent.read_text(encoding="utf-8")
if "import os\n" not in text:
    text = "import os\n" + text
old = '''    def instructions(context_variables):
        working_dir = context_variables.get("working_dir", None)
        return f"""You are a advisor that can help the `Machine Learning Agent` to implement the task.'''
new = '''    def instructions(context_variables):
        working_dir = context_variables.get("working_dir", None)
        if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_JUDGEMENT") == "1":
            return """You are AI-Researcher's Judge Agent for the fixed PsyDefDetect benchmark. Evaluate only the completed two-experiment evidence supplied in the current user message. Do not delegate, browse files, or request more experiments. Call case_resolved in this turn; mark fully_correct=true only when the message confirms two local experiments, evidence-based selection, and the valid four-file root handoff."""
        return f"""You are a advisor that can help the `Machine Learning Agent` to implement the task.'''
if old not in text:
    raise SystemExit("AI-Researcher compact judge instructions insertion point not found")
text = text.replace(old, new, 1)
old = '''        functions=[
            case_resolved,
            transfer_to_code_review_agent,
        ],'''
new = '''        functions=(
            [case_resolved]
            if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_JUDGEMENT") == "1"
            else [case_resolved, transfer_to_code_review_agent]
        ),'''
if old not in text:
    raise SystemExit("AI-Researcher compact judge tool-list insertion point not found")
judge_agent.write_text(text.replace(old, new, 1), encoding="utf-8")

exp_analyser = Path(sys.argv[10])
text = exp_analyser.read_text(encoding="utf-8")
if "import os\n" not in text:
    text = "import os\n" + text
old = '''    tools = tool_files + tool_codes + [case_resolved]
    return Agent('''
new = '''    if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_ANALYSIS") == "1":
        tools = [case_resolved]
    else:
        tools = tool_files + tool_codes + [case_resolved]
    return Agent('''
if old not in text:
    raise SystemExit("AI-Researcher compact analysis tool insertion point not found")
text = text.replace(old, new, 1)
old = '''    def instructions(context_variables: dict):
        return """\\
You are given an innovative idea and some experimental results conducted by `Machine Learning Agent` in the directory `/workspace/projects/` to implement the idea.'''
new = '''    def instructions(context_variables: dict):
        if os.getenv("AI_RESEARCHER_PSYDEFDETECT_COMPACT_ANALYSIS") == "1":
            return """\\
Analyze the PsyDefDetect experiment evidence included in the current user message. Do not browse files or repeat experiments in this analysis stage. Call `case_resolved` in this turn with a concise evidence-based analysis_report and a further_plan containing exactly one materially different follow-up experiment. The follow-up must use installed local libraries and must not use remote API requests, model downloads, or runtime package installation.
"""
        return """\\
You are given an innovative idea and some experimental results conducted by `Machine Learning Agent` in the directory `/workspace/projects/` to implement the idea.'''
if old not in text:
    raise SystemExit("AI-Researcher compact analysis prompt insertion point not found")
exp_analyser.write_text(text.replace(old, new, 1), encoding="utf-8")

entrypoint = Path(sys.argv[3])
text = entrypoint.read_text(encoding="utf-8")
old = '        messages = [{"role": "user", "content": ml_dev_query}]'
new = '''        if category == "psydefdetect":
            ml_dev_query = f"""\\
Implement and execute PsyDefDetect now in /{workplace_name}. Do not begin with directory listing.

Use /{workplace_name}/project/data/psydefdetect, automation/psydefdetect_split.canonical.json, and automation/scripts/run_psydefdetect_local_score.py. Choose exactly two materially different local experiments yourself using installed resources and lock their rationale in research_idea.json before execution. Experiment code must not make remote calls. Run and score both experiments, select by observed macro-F1, and immediately write the complete framework-owned handoff at /{workplace_name}: predictions.jsonl or submission.csv, score.json, experiment_trace.json, and final_report.md. The trace must use exactly `exp1` and `exp2` as its two experiment ids and set string `selected_experiment_id` to the higher-scoring id. Do not install packages, download models, use background jobs, or start a third experiment. After both official score files exist, call write_psydefdetect_handoff directly instead of inspecting files, then call complete_psydefdetect with the two observed scores and selected id.
"""
        messages = [{"role": "user", "content": ml_dev_query}]'''
if old not in text:
    raise SystemExit("AI-Researcher PsyDefDetect ML query insertion point not found")
text = text.replace(old, new, 1)
old = '        MAX_ITER_TIMES = max_iter_times'
new = '        MAX_ITER_TIMES = 0 if category == "psydefdetect" else max_iter_times'
if old not in text:
    raise SystemExit("AI-Researcher refinement budget insertion point not found")
text = text.replace(old, new, 1)
old = '        judge_messages.append({"role": "user", "content": ml_submit_query})'
new = '''        if category == "psydefdetect":
            ml_submit_query = f"""\\
The framework has already executed exactly two PsyDefDetect experiments and produced the selected valid four-file handoff. Do not inspect files, run commands, modify code, or start another experiment. Call case_resolved now using the two observed scores and selected_experiment_id already present in the conversation.
"""
        judge_messages.append({"role": "user", "content": ml_submit_query})'''
if old not in text:
    raise SystemExit("AI-Researcher final submit insertion point not found")
text = text.replace(old, new, 1)
old = '        IDEA_NUM = 5'
new = '        IDEA_NUM = 2 if category == "psydefdetect" else 5'
if old not in text:
    raise SystemExit("AI-Researcher idea budget insertion point not found")
text = text.replace(old, new, 1)
old = '        EXP_ITER_TIMES = 2\n        for i in range(EXP_ITER_TIMES):'
new = '        EXP_ITER_TIMES = 0 if category == "psydefdetect" else 2\n        refine_res = submit_res\n        for i in range(EXP_ITER_TIMES):'
if old not in text:
    raise SystemExit("AI-Researcher experiment refinement budget insertion point not found")
text = text.replace(old, new, 1)
old = '''            judge_messages, context_variables = await self.exp_analyser(judge_messages, context_variables, iter_times=f"refine_{i+1}", max_turns=30)
            analysis_report = judge_messages[-1]["content"]

            analysis_report = context_variables["experiment_report"][-1]["analysis_report"]'''
new = '''            judge_messages, context_variables = await self.exp_analyser(judge_messages, context_variables, iter_times=f"refine_{i+1}", max_turns=8)
            analysis_report = judge_messages[-1]["content"]
            if not context_variables.get("experiment_report"):
                retry_messages = [{
                    "role": "user",
                    "content": "The analysis state contract is still incomplete. Analyze the evidence already supplied and call case_resolved now.",
                }]
                retry_messages, context_variables = await self.exp_analyser(
                    retry_messages,
                    context_variables,
                    iter_times=f"refine_{i+1}_contract_retry",
                    max_turns=4,
                )
            if not context_variables.get("experiment_report"):
                raise RuntimeError("Experiment Analysis Agent did not publish experiment_report through case_resolved")

            analysis_report = context_variables["experiment_report"][-1]["analysis_report"]'''
if old not in text:
    raise SystemExit("AI-Researcher experiment-report retry insertion point not found")
entrypoint.write_text(text.replace(old, new, 1), encoding="utf-8")
PY
inner_prefix="psydefdetect_ai_researcher_${REAL_EVAL_RUN_ID}"
cleanup_inner() {
  docker ps -aq --filter "name=^/${inner_prefix}" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_inner EXIT
port="$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
cd research_agent
timeout "${AI_RESEARCHER_PSYDEFDETECT_TIMEOUT_SECONDS:-7200}s" python run_infer_idea.py \
  --instance_path ../benchmark/final/psydefdetect/psydefdetect.json \
  --container_name "$inner_prefix" \
  --model "$COMPLETION_MODEL" \
  --workplace_name . \
  --cache_path "cache_${REAL_EVAL_RUN_ID}" \
  --port "$port" \
  --max_iter_times 0 \
  --category psydefdetect
EOF
)
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_fullrun.sh

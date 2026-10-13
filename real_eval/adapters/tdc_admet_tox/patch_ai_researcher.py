#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        print(f"SKIP: AI-Researcher adapter insertion point changed: {label}")
        return
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_dataset_setup(root: Path) -> None:
    path = root / "research_agent/inno/environment/utils.py"
    text = path.read_text(encoding="utf-8")
    start = text.index("def setup_dataset(category: str, local_workplace: str):")
    replacement = """def setup_dataset(category: str, local_workplace: str):
    dataset_candidate_path = os.path.join(local_workplace, "dataset_candidate")
    if os.path.exists(dataset_candidate_path):
        return
    source_path = os.path.join(local_workplace, "benchmark", "process", "dataset_candidate", category)
    if category == "tdc_admet_tox":
        visible_dataset = os.environ.get("RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT")
        if not visible_dataset or not os.path.isdir(visible_dataset):
            raise RuntimeError("TDC-ADMET-Tox public dataset is unavailable")
        os.makedirs(dataset_candidate_path, exist_ok=True)
        shutil.copy2(os.path.join(source_path, "metaprompt.py"), dataset_candidate_path)
        return
    shutil.copytree(source_path, dataset_candidate_path)
"""
    path.write_text(text[:start] + replacement, encoding="utf-8")


def patch_nested_runtime(root: Path) -> None:
    path = root / "research_agent/inno/environment/docker_env.py"
    text = path.read_text(encoding="utf-8")
    old_workspace = '        self.docker_workplace = f"/{config.workplace_name}"'
    if text.count(old_workspace) != 1:
        raise SystemExit("AI-Researcher adapter insertion point changed: local workspace path")
    text = text.replace(
        old_workspace,
        '        self.docker_workplace = "/workspace" if config.workplace_name == "." else f"/{config.workplace_name}"\n'
        "        self._server_process = None",
        1,
    )
    start = text.index("    def init_container(self):")
    end = text.index("    def run_command(self, command", start)
    local_runtime = """    def init_container(self):
        os.makedirs(self.local_workplace, exist_ok=True)
        if self.setup_package is not None:
            unzip_command = [
                "tar", "-xzvf", f"packages/{self.setup_package}.tar.gz",
                "-C", self.local_workplace,
            ]
            subprocess.run(unzip_command, check=True)
        if self.git_clone:
            raise RuntimeError("network repository cloning is disabled for TDC-ADMET-Tox")

        server_path = Path(__file__).resolve().parents[3] / "docker" / "tcp_server.py"
        if not server_path.is_file():
            raise RuntimeError(f"local command server is unavailable: {server_path}")
        self._server_process = subprocess.Popen(
            [
                "python3", str(server_path),
                "--workplace", self.docker_workplace,
                "--port", str(self.communication_port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.wait_for_container_ready(timeout=30)

    def wait_for_container_ready(self, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._server_process is not None and self._server_process.poll() is not None:
                raise RuntimeError("local command server exited before becoming ready")
            try:
                with socket.create_connection(("127.0.0.1", self.communication_port), timeout=1):
                    return True
            except OSError:
                time.sleep(0.2)
        raise TimeoutError("local command server failed to start")

    def stop_container(self):
        if self._server_process is None or self._server_process.poll() is not None:
            return
        self._server_process.terminate()
        try:
            self._server_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._server_process.kill()
            self._server_process.wait(timeout=5)

"""
    path.write_text(text[:start] + local_runtime + text[end:], encoding="utf-8")


def patch_import_compatibility(root: Path) -> None:
    canonical_imports = {
        "research_agent/inno/environment/utils.py": (
            ("from inno.util import run_command_in_container", "from research_agent.inno.util import run_command_in_container"),
            ("from constant import DOCKER_WORKPLACE_NAME", "from research_agent.constant import DOCKER_WORKPLACE_NAME"),
        ),
        "research_agent/inno/environment/docker_env.py": (
            (
                "from constant import BASE_IMAGES, AI_USER, GITHUB_AI_TOKEN, GPUS, PLATFORM",
                "from research_agent.constant import BASE_IMAGES, AI_USER, GITHUB_AI_TOKEN, GPUS, PLATFORM",
            ),
        ),
        "research_agent/inno/environment/browser_env.py": (
            ("from inno.io_utils import read_file", "from research_agent.inno.io_utils import read_file"),
            (
                "from inno.environment.mdconvert import _get_page_markdown",
                "from research_agent.inno.environment.mdconvert import _get_page_markdown",
            ),
            (
                "from inno.environment.browser_cookies import convert_cookies_to_python",
                "from research_agent.inno.environment.browser_cookies import convert_cookies_to_python",
            ),
            (
                "from inno.environment.cookies_data import COOKIES_LIST",
                "from research_agent.inno.environment.cookies_data import COOKIES_LIST",
            ),
        ),
    }
    for relative_path, replacements in canonical_imports.items():
        path = root / relative_path
        for old, new in replacements:
            replace_once(path, old, new, f"canonical import in {relative_path}")

    tools = root / "research_agent/inno/tools/__init__.py"
    replace_once(
        tools,
        "import_tools_recursively(current_dir, 'inno.tools')",
        """for module_name in (
    "terminal_tools",
    "inner",
    "inno_tools.planning_tools",
    "inno_tools.web_tools",
):
    importlib.import_module(f"research_agent.inno.tools.{module_name}")""",
        "canonical required tool registration",
    )

    agents = root / "research_agent/inno/agents/__init__.py"
    replace_once(
        agents,
        "import_agents_recursively(current_dir, 'inno.agents')",
        """for module_name in (
    "inno_agent.exp_analyser",
    "inno_agent.idea_agent",
    "inno_agent.judge_agent",
    "inno_agent.ml_agent",
    "inno_agent.plan_agent",
    "inno_agent.prepare_agent",
    "inno_agent.survey_agent",
):
    importlib.import_module(f"research_agent.inno.agents.{module_name}")""",
        "canonical required agent registration",
    )

    mdconvert = root / "research_agent/inno/environment/markdown_browser/mdconvert.py"
    text = mdconvert.read_text(encoding="utf-8")
    import re
    m = re.search(r'^(\s*)(from docling\.document_converter import DocumentConverter as DocLingDocumentConverter)', text, re.MULTILINE)
    if m:
        ind = m.group(1)
        old = m.group(0)
        new = f"""{ind}try:
{ind}    from docling.document_converter import DocumentConverter as DocLingDocumentConverter
{ind}except ModuleNotFoundError:
{ind}    DocLingDocumentConverter = None"""
        mdconvert.write_text(text.replace(old, new, 1), encoding="utf-8")
    replace_once(
        mdconvert,
        """        converter = DocLingDocumentConverter()
        result = converter.convert(local_path)
        text_content = result.document.export_to_markdown()""",
        """        if DocLingDocumentConverter is None:
            text_content = pdfminer.high_level.extract_text(local_path)
        else:
            converter = DocLingDocumentConverter()
            result = converter.convert(local_path)
            text_content = result.document.export_to_markdown()""",
        "lightweight PDF fallback",
    )

    browser = root / "research_agent/inno/environment/markdown_browser/requests_markdown_browser.py"
    replace_once(
        browser,
        "from inno.memory.paper_memory import PaperMemory",
        "from research_agent.inno.memory.paper_memory import PaperMemory",
        "canonical paper memory import",
    )
    replace_once(
        browser,
        "from constant import API_BASE_URL",
        "from research_agent.constant import API_BASE_URL",
        "canonical constant import",
    )
    replace_once(
        browser,
        """        platform = 'default'
        self._memory = PaperMemory(project_path="./paper_db", db_name=".paper_memory_" + platform, platform=platform, api_key=os.getenv("OPENAI_API_KEY"), embedding_model='text-embedding-3-small')""",
        "        self._memory = None",
        "lazy paper memory initialization",
    )
    replace_once(
        browser,
        """        if self._memory.count(collection) == 0:
            self._memory.add_paper_content(paper_content=self.page_content, collection=collection)
        query_results = self._memory.query_paper_content(query_text=question, collection=collection, n_results=5)""",
        """        if self._memory is None:
            platform = "default"
            self._memory = PaperMemory(
                project_path="./paper_db",
                db_name=".paper_memory_" + platform,
                platform=platform,
                api_key=os.getenv("OPENAI_API_KEY"),
                embedding_model="text-embedding-3-small",
            )
        if self._memory.count(collection) == 0:
            self._memory.add_paper_content(paper_content=self.page_content, collection=collection)
        query_results = self._memory.query_paper_content(
            query_text=question, collection=collection, n_results=5
        )""",
        "lazy paper memory use",
    )


def patch_native_flow(root: Path) -> None:
    path = root / "research_agent/run_infer_idea.py"
    replace_once(
        path,
        """    arxiv_url = eval_instance["url"]
    meta = get_arxiv_paper_meta(arxiv_url)
    if meta is None:
        date = "2024-01-01"
    else:
        date = meta["published"].strftime("%Y-%m-%d")""",
        """    arxiv_url = eval_instance["url"]
    if eval_instance.get("instance_id") == "tdc_admet_tox":
        date = "2024-01-01"
    else:
        meta = get_arxiv_paper_meta(arxiv_url)
        if meta is None:
            date = "2024-01-01"
        else:
            date = meta["published"].strftime("%Y-%m-%d")""",
        "offline instance metadata",
    )
    replace_once(
        path,
        '        github_result = self.git_search({"metadata": metadata})',
        """        github_result = (
            "Use the mounted contract, validation scorer, and framework workspace only."
            if category == "tdc_admet_tox"
            else self.git_search({"metadata": metadata})
        )""",
        "offline code reference",
    )
    old = """        prepare_messages, context_variables = await self.prepare_agent(messages, context_variables)
        prepare_res = prepare_messages[-1]["content"]
        prepare_dict = extract_json_from_output(prepare_res)
        paper_list = prepare_dict["reference_papers"]
        download_res = self.download_papaer({"paper_list": paper_list, "local_root": local_root, "workplace_name": workplace_name})"""
    new = """        if category == "tdc_admet_tox":
            prepare_res = json.dumps({
                "reference_papers": [],
                "local_inputs": [
                    "/workspace/automation/tdc_admet_tox_contract.md",
                    "/workspace/docs/tdc_admet_tox_feature_generation_contract.md",
                ],
            })
            download_res = "No external paper or repository download is permitted."
        else:
            prepare_messages, context_variables = await self.prepare_agent(messages, context_variables)
            prepare_res = prepare_messages[-1]["content"]
            prepare_dict = extract_json_from_output(prepare_res)
            paper_list = prepare_dict["reference_papers"]
            download_res = self.download_papaer({"paper_list": paper_list, "local_root": local_root, "workplace_name": workplace_name})"""
    replace_once(path, old, new, "offline reference preparation")
    replace_once(
        path,
        "        IDEA_NUM = 5",
        '        IDEA_NUM = 2 if category == "tdc_admet_tox" else 5',
        "bounded idea count",
    )
    replace_once(
        path,
        '    local_root = os.path.join(os.getcwd(),"workplace_paper" , f"task_{instance_id}" + "_" + COMPLETION_MODEL.replace("/", "__"),  args.workplace_name)',
        '    local_root = "/workspace"\n    args.workplace_name = "."',
        "run workspace root",
    )
    replace_once(
        path,
        '    file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root=env_config.local_root, workplace_name=env_config.workplace_name, downloads_folder=os.path.join(env_config.local_root, env_config.workplace_name, "downloads"))',
        '    file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root="/", workplace_name="workspace", downloads_folder="/workspace/downloads")',
        "workspace file browser",
    )
    replace_once(
        path,
        "    web_env = BrowserEnv(browsergym_eval_env = None, local_root=env_config.local_root, workplace_name=env_config.workplace_name)",
        "    web_env = None  # TDC-ADMET-Tox is fully offline; no Playwright browser env",
        "offline web env",
    )
    old = "    asyncio.run(flow(instance_path=args.instance_path, task_level=args.task_level, local_root=local_root, workplace_name=args.workplace_name, max_iter_times=args.max_iter_times, category=args.category, references = references))"
    new = """    try:
        asyncio.run(flow(instance_path=args.instance_path, task_level=args.task_level, local_root=local_root, workplace_name=args.workplace_name, max_iter_times=args.max_iter_times, category=args.category, references=references))
    finally:
        if args.category == "tdc_admet_tox":
            _promote_tdc_handoff(local_root)
        code_env.stop_container()"""
    replace_once(path, old, new, "local command server cleanup")
    replace_once(path, "    main(args)\n", '    main(args, references="")\n', "native main call")

    constants = root / "research_agent/constant.py"
    constants_text = constants.read_text(encoding="utf-8")
    if "PLATFORM =" not in constants_text:
        constants.write_text(
            constants_text + '\nPLATFORM = os.getenv("PLATFORM", "linux/amd64")\n',
            encoding="utf-8",
        )


def patch_native_handoff(root: Path) -> None:
    path = root / "research_agent/run_infer_idea.py"
    text = path.read_text(encoding="utf-8")
    if "def _promote_tdc_handoff(" in text:
        return
    if "from pathlib import Path\n" not in text:
        text = text.replace("import json\n", "import json\nfrom pathlib import Path\n", 1)
    if "import shutil\n" not in text:
        text = text.replace("import os\n", "import os\nimport shutil\n", 1)
    helper = '''

def _promote_tdc_handoff(root: str) -> None:
    """Materialize the framework's project handoff at the native workspace root."""
    if os.environ.get("TDC_ADMET_TOX_NATIVE_RUN") != "1":
        return
    source = Path(root) / "project"
    target = Path(root)
    if not source.is_dir():
        return
    for name in (
        "predictions.csv",
        "research_idea.json",
        "experiment_trace.json",
        "environment.json",
        "paper.md",
        "final_report.md",
    ):
        source_path = source / name
        if source_path.is_file():
            shutil.copy2(source_path, target / name)
    for name in ("runs", "logs"):
        source_path = source / name
        if source_path.is_dir():
            shutil.copytree(source_path, target / name, dirs_exist_ok=True)

'''
    for anchor in ("def main(args, references):\n", "def main(args):\n"):
        if text.count(anchor) == 1:
            text = text.replace(anchor, helper + anchor, 1)
            break
    else:
        raise SystemExit("AI-Researcher adapter insertion point changed: native handoff helper")
    path.write_text(text, encoding="utf-8")


TDC_HARD_BUDGET = """TDC-ADMET-Tox HARD BUDGET RULES (MANDATORY, override all other guidance):
 - Total wall time is 7,200 seconds and the process is killed hard at that limit. Stop all experiment work at least 900 seconds before the limit and spend that time writing the complete handoff: /workspace/predictions.csv, /workspace/experiment_trace.json (evaluation schema with task_id 'tdc_admet_tox', experiments[], claims[]), /workspace/environment.json, /workspace/paper.md, and running the framework-stage audit until it passes.
 - Choose an approach that can complete within the budget on the installed CPU-only runtime (NumPy, pandas, SciPy, scikit-learn; no RDKit). If a candidate would not finish within the remaining budget, reduce or replace it.
 - First build a configuration that finishes in minutes, then immediately write the baseline handoff files (predictions.csv, skeleton experiment_trace.json, environment.json, paper.md). Only then run at most 1-2 more configurations, updating the trace incrementally.
 - A sweep, grid, random search, or hyperparameter scan is a violation. More than 4 validation candidates total is a violation. If an experiment cannot finish within the remaining budget, drop it and keep the finished handoff.
 - Write handoff files incrementally as soon as evidence exists; never wait until the very end.
 - EXPERIMENT_TRACE.JSON MUST BE THE CONTRACT SCHEMA, NOT A SUMMARY. Each experiment is one complete CONFIGURATION (a distinct model/training/feature strategy evaluated on validation data), not one endpoint. Write exactly this shape:
   {
     "task_id": "tdc_admet_tox",
     "framework_native_execution": true,
     "consumed_topic_input": true,
     "framework_internal_model": "<the actual OPENAI_MODEL value>",
     "framework_internal_api_base_url": "<the actual OPENAI_BASE_URL value>",
     "selection_metric": "validation_macro_average_auroc",
     "final_prediction_file": "predictions.csv",
     "resource_budget": {"cpu_cores": 4, "memory_gib": 16, "gpu_count": 0, "workspace_disk_gib": 10, "max_experiment_runtime_seconds": 3600, "max_total_wall_seconds": 7200, "network_policy": "injected_llm_relay_only"},
     "total_wall_seconds": <number>,
     "selected_experiment_id": "<run_id of the best configuration>",
     "environment_file": "environment.json",
     "experiments": [
       {
         "run_id": "run_001",
         "status": "complete",
         "hypothesis": "<string>",
         "model_strategy": "<string>",
         "feature_strategy": "<string>",
         "runtime_seconds": <number>,
         "seed": <integer>,
         "candidate_count": 1,
         "config_file": "runs/run_001/config.json",
         "prediction_file": "runs/run_001/predictions_validation.csv",
         "metrics_file": "runs/run_001/metrics.json",
         "log_file": "runs/run_001/train.log",
         "validation_metrics": {
           "macro_average_auroc": <number>,
           "macro_average_auprc": <number>,
           "macro_average_brier_score": <number>,
           "per_endpoint": {
             "AMES": {"auroc": <number>, "auprc_average_precision": <number>, "brier_score": <number>},
             "hERG": {"auroc": <number>, "auprc_average_precision": <number>, "brier_score": <number>},
             "DILI": {"auroc": <number>, "auprc_average_precision": <number>, "brier_score": <number>}
           }
         }
       }
     ],
     "claims": [
       {
         "claim_id": "table1_ames_auroc_run_001",
         "endpoint": "AMES",
         "metric": "auroc",
         "value": <exact number from metrics_file>,
         "source_run_id": "run_001",
         "prediction_file": "runs/run_001/predictions_validation.csv",
         "config_file": "runs/run_001/config.json",
         "log_file": "runs/run_001/train.log"
       }
     ],
     "reproduction": {
       "entrypoint": "<path to a runnable .py file>",
       "command": "python <entrypoint>",
       "seed": <integer>,
       "source_files": ["<files>"]
     }
   }
 - Write one metrics.json per experiment with "split": "validation" and the same numbers as in trace experiments[].validation_metrics, and a per-endpoint predictions file (columns sample_id,endpoint,probability) from validation inference. Claims must reference the experiment's own config/prediction/log files, and every number in paper.md tables or prose must have a claim marker like <!-- claim:table1_ames_auroc_run_001 -->.
 - After the last experiment, run: python3 automation/scripts/validate_tdc_admet_tox_run.py --stage framework --public-dataset-root /data/tdc_admet_tox
   Fix whatever it reports (trace schema, claim linkage, paper markers) before finishing. The audit must pass with exit code 0."""


def patch_agent_budget(root: Path) -> None:
    # Both native agent prompts are f-strings. Escape the JSON example braces
    # while it is inserted into source so they remain literal prompt text at
    # runtime instead of being parsed as nested f-string expressions.
    budget_for_fstring = TDC_HARD_BUDGET.replace("{", "{{").replace("}", "}}")
    ml = root / "research_agent/inno/agents/inno_agent/ml_agent.py"
    text = ml.read_text(encoding="utf-8")
    anchor = "AVAILABLE TOOLS:"
    if TDC_HARD_BUDGET.splitlines()[0] not in text:
        replace_once(ml, anchor, budget_for_fstring + "\n\n" + anchor, "ml_agent budget injection")
    plan = root / "research_agent/inno/agents/inno_agent/plan_agent.py"
    plan_text = plan.read_text(encoding="utf-8")
    plan_anchor = "AVAILABLE RESOURCES:"
    if TDC_HARD_BUDGET.splitlines()[0] not in plan_text:
        replace_once(plan, plan_anchor, budget_for_fstring + "\n\n" + plan_anchor, "plan_agent budget injection")


TDC_CONTEXT_BOUND = '''    def _bound_context(self, messages, max_tokens=180000):
        if not messages:
            return messages
        encode = encode_string_by_tiktoken
        decode = decode_tokens_by_tiktoken
        def total_tokens(items):
            total = 0
            for item in items:
                content = item.get("content")
                if isinstance(content, str):
                    total += len(encode(content))
            return total
        while total_tokens(messages) > max_tokens and len(messages) > 6:
            dropped = False
            for index in range(1, len(messages) - 2):
                role = messages[index].get("role")
                if role == "tool":
                    continue
                if role == "assistant" and messages[index].get("tool_calls"):
                    end = index + 1
                    while end < len(messages) and messages[end].get("role") == "tool":
                        end += 1
                    del messages[index:end]
                else:
                    del messages[index]
                dropped = True
                break
            if not dropped:
                break
        if total_tokens(messages) > max_tokens:
            for index in range(1, len(messages)):
                item = messages[index]
                content = item.get("content")
                if isinstance(content, str) and len(encode(content)) > 4000:
                    keep = 4000
                    if total_tokens(messages) <= max_tokens:
                        break
                    item["content"] = decode(encode(content)[:keep])
        return messages

'''


def patch_context_bound(root: Path) -> None:
    path = root / "research_agent/inno/core.py"
    text = path.read_text(encoding="utf-8")
    if "import os\n" not in text:
        replace_once(
            path,
            "import json\n",
            "import json\nimport os\n",
            "core os import",
        )
    replace_once(
        path,
        "    async def get_chat_completion_async(",
        TDC_CONTEXT_BOUND + "    async def get_chat_completion_async(",
        "context bound helper insertion",
    )
    text = path.read_text(encoding="utf-8")
    old = (
        "        if agent.examples:\n"
        "            examples = agent.examples(context_variables) if callable(agent.examples) else agent.examples\n"
        "            history = examples + history\n"
        "        \n"
        "        messages = [{\"role\": \"system\", \"content\": instructions}] + history"
    )
    new = (
        "        if agent.examples:\n"
        "            examples = agent.examples(context_variables) if callable(agent.examples) else agent.examples\n"
        "            history = examples + history\n"
        "        \n"
        "        messages = [{\"role\": \"system\", \"content\": instructions}] + history\n"
        "        if os.environ.get(\"TDC_ADMET_TOX_NATIVE_RUN\") == \"1\":\n"
        "            messages = self._bound_context(messages)"
    )
    if text.count(old) != 2:
        raise SystemExit("AI-Researcher adapter insertion point changed: context bound call")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch_repetition_guard(root: Path) -> None:
    path = root / "research_agent/inno/core.py"
    text = path.read_text(encoding="utf-8")
    prefix, separator, async_body = text.partition("    async def run_async(")
    if not separator:
        raise SystemExit("AI-Researcher adapter insertion point changed: async run")
    async_body = separator + async_body
    old_init = (
        "        context_variables = copy.deepcopy(context_variables)\n"
        "        history = copy.deepcopy(messages)\n"
        "        init_len = len(messages)\n"
    )
    new_init = old_init + "        _tdc_repeat_signatures = {}\n"
    if async_body.count(old_init) != 1:
        raise SystemExit("AI-Researcher adapter insertion point changed: repetition state")
    async_body = async_body.replace(old_init, new_init, 1)
    old_message = (
        "            history.append(\n"
        "                json.loads(message.model_dump_json())\n"
        "            )  # to avoid OpenAI types (?)\n\n"
        "            if enter_agent.tool_choice != \"required\":\n"
    )
    new_message = (
        "            history.append(\n"
        "                json.loads(message.model_dump_json())\n"
        "            )  # to avoid OpenAI types (?)\n\n"
        "            if os.environ.get(\"TDC_ADMET_TOX_NATIVE_RUN\") == \"1\" and message.tool_calls:\n"
        "                signature = tuple(\n"
        "                    (call.function.name, call.function.arguments)\n"
        "                    for call in message.tool_calls\n"
        "                )\n"
        "                _tdc_repeat_signatures[signature] = _tdc_repeat_signatures.get(signature, 0) + 1\n"
        "                if _tdc_repeat_signatures[signature] >= 8:\n"
        "                    self.logger.info(\n"
        "                        \"TDC repetition guard stopped an unchanged native tool cycle\",\n"
        "                        title=\"TDC Handoff Guard\",\n"
        "                        color=\"yellow\",\n"
        "                    )\n"
        "                    history.append({\n"
        "                        \"role\": \"assistant\",\n"
        "                        \"content\": \"TDC repetition guard: stop repeated tool calls and finalize the existing handoff.\",\n"
        "                    })\n"
        "                    break\n\n"
        "            if enter_agent.tool_choice != \"required\":\n"
    )
    if async_body.count(old_message) != 1:
        raise SystemExit("AI-Researcher adapter insertion point changed: repetition check")
    path.write_text(prefix + async_body.replace(old_message, new_message, 1), encoding="utf-8")


def patch_host_scorer_guard(root: Path) -> None:
    path = root / "research_agent/inno/tools/file_surfer_tool.py"
    old = """    except Exception as e:
        return f"Error in `open_local_file`: {e}\""""
    new = """    except Exception as e:
        if "host_score" in path or not os.path.isfile(path):
            return (
                "Error in `open_local_file`: the file is not available inside the native "
                "workspace. Host-only artifacts such as "
                "automation/scripts/run_tdc_admet_tox_host_score.py are never projected "
                "into the framework container. Do not retry this path; continue using the "
                "visible contract, feature-generation contract, validator, and validation "
                "scorer files only."
            )
        return f"Error in `open_local_file`: {e}\""""
    replace_once(path, old, new, "host scorer guard")


def main() -> int:
    root = Path.cwd()
    marker = root / ".tdc_admet_tox_ai_researcher_patch_applied"
    if marker.exists():
        return 0
    patch_dataset_setup(root)
    patch_nested_runtime(root)
    patch_import_compatibility(root)
    patch_native_flow(root)
    patch_native_handoff(root)
    patch_agent_budget(root)
    patch_context_bound(root)
    patch_repetition_guard(root)
    patch_host_scorer_guard(root)
    marker.write_text("tdc_admet_tox_ai_researcher_patch_v2\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

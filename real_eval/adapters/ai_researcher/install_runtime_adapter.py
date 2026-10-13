#!/usr/bin/env python3
"""install_runtime_adapter.py — Minimal TDC-ADMET-Tox compatibility adapter.

Replaces the old 620-line ``real_eval/adapters/tdc_admet_tox/patch_ai_researcher.py``.

Allowed operations (per adapter-policy.v1.json):
  canonical imports, dataset mount, local command-server,
  relay env, context truncation, schema tools.

Forbidden operations (not present here):
  hardcoded prepare, agent prompt replacement, method/baseline/strategy,
  host handoff promotion, score creation, hidden-label access.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        # Import target may already be canonical from a prior run — skip.
        return
    if count != 1:
        raise SystemExit(
            f"AI-Researcher adapter insertion point changed: {label} "
            f"(found {count} occurrences)"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# ── 1. Canonical imports ──────────────────────────────────────────────────

_CANONICAL_IMPORTS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "research_agent/inno/environment/utils.py",
        [
            (
                "from inno.util import run_command_in_container",
                "from research_agent.inno.util import run_command_in_container",
            ),
            (
                "from constant import DOCKER_WORKPLACE_NAME",
                "from research_agent.constant import DOCKER_WORKPLACE_NAME",
            ),
        ],
    ),
    (
        "research_agent/inno/environment/docker_env.py",
        [
            (
                "from constant import BASE_IMAGES, AI_USER, GITHUB_AI_TOKEN, GPUS, PLATFORM",
                "from research_agent.constant import BASE_IMAGES, AI_USER, GITHUB_AI_TOKEN, GPUS, PLATFORM",
            ),
        ],
    ),
    (
        "research_agent/inno/environment/browser_env.py",
        [
            (
                "from inno.io_utils import read_file",
                "from research_agent.inno.io_utils import read_file",
            ),
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
        ],
    ),
    (
        "research_agent/inno/environment/markdown_browser/requests_markdown_browser.py",
        [
            (
                "from inno.memory.paper_memory import PaperMemory",
                "from research_agent.inno.memory.paper_memory import PaperMemory",
            ),
            (
                "from constant import API_BASE_URL",
                "from research_agent.constant import API_BASE_URL",
            ),
        ],
    ),
]


def _patch_canonical_imports(root: Path) -> None:
    for rel_path, replacements in _CANONICAL_IMPORTS:
        for old, new in replacements:
            _replace_once(root / rel_path, old, new, f"canonical import in {rel_path}")


# ── 2. Schema tools — explicit tool/agent registrations ───────────────────


def _patch_tools_init(root: Path) -> None:
    path = root / "research_agent/inno/tools/__init__.py"
    _replace_once(
        path,
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


def _patch_agents_init(root: Path) -> None:
    path = root / "research_agent/inno/agents/__init__.py"
    _replace_once(
        path,
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


# ── 3. Dataset mount — local dataset directory for tdc_admet_tox ──────────


def _patch_dataset_setup(root: Path) -> None:
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


# ── 4. Local command-server + relay env (replaces Docker-in-Docker) ───────


def _patch_docker_env(root: Path) -> None:
    path = root / "research_agent/inno/environment/docker_env.py"
    text = path.read_text(encoding="utf-8")

    # Override docker_workplace to /workspace for flat mounts
    old_workspace = '        self.docker_workplace = f"/{config.workplace_name}"'
    if text.count(old_workspace) == 1:
        text = text.replace(
            old_workspace,
            '        self.docker_workplace = "/workspace" if config.workplace_name == "." else f"/{config.workplace_name}"\n'
            "        self._server_process = None",
            1,
        )

    # Replace init_container / wait_for_container_ready / stop_container
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


# ── 5. Context truncation — bounded idea count, workspace root, cleanup ───


def _patch_native_flow(root: Path) -> None:
    path = root / "research_agent/run_infer_idea.py"

    # Offline instance metadata (skip arxiv fetch for tdc_admet_tox)
    _replace_once(
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

    # Offline code reference (skip github search for tdc_admet_tox)
    _replace_once(
        path,
        '        github_result = self.git_search({"metadata": metadata})',
        """        github_result = (
            "Use the mounted contract, validation scorer, and framework workspace only."
            if category == "tdc_admet_tox"
            else self.git_search({"metadata": metadata})
        )""",
        "offline code reference",
    )

    # Bounded idea count
    _replace_once(
        path,
        "        IDEA_NUM = 5",
        '        IDEA_NUM = 2 if category == "tdc_admet_tox" else 5',
        "bounded idea count",
    )

    # Run workspace root
    _replace_once(
        path,
        '    local_root = os.path.join(os.getcwd(),"workplace_paper" , f"task_{instance_id}" + "_" + COMPLETION_MODEL.replace("/", "__"),  args.workplace_name)',
        '    local_root = "/workspace"\n    args.workplace_name = "."',
        "run workspace root",
    )

    # Workspace file browser
    _replace_once(
        path,
        '    file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root=env_config.local_root, workplace_name=env_config.workplace_name, downloads_folder=os.path.join(env_config.local_root, env_config.workplace_name, "downloads"))',
        '    file_env = RequestsMarkdownBrowser(viewport_size=1024 * 4, local_root="/", workplace_name="workspace", downloads_folder="/workspace/downloads")',
        "workspace file browser",
    )

    # Local command server cleanup
    old = "    asyncio.run(flow(instance_path=args.instance_path, task_level=args.task_level, local_root=local_root, workplace_name=args.workplace_name, max_iter_times=args.max_iter_times, category=args.category, references = references))"
    new = """    try:
        asyncio.run(flow(instance_path=args.instance_path, task_level=args.task_level, local_root=local_root, workplace_name=args.workplace_name, max_iter_times=args.max_iter_times, category=args.category, references=references))
    finally:
        if category == "tdc_admet_tox":
            code_env.stop_container()
"""
    _replace_once(path, old, new, "local command server cleanup")
    _replace_once(path, '    main(args, "")\n', '    main(args, references="")\n', "native main call")

    # Ensure PLATFORM constant exists
    constants = root / "research_agent/constant.py"
    constants_text = constants.read_text(encoding="utf-8")
    if "PLATFORM =" not in constants_text:
        constants.write_text(
            constants_text + '\nPLATFORM = os.getenv("PLATFORM", "linux/amd64")\n',
            encoding="utf-8",
        )


# ── 6. Optional docling PDF fallback ──────────────────────────────────────


def _patch_mdconvert(root: Path) -> None:
    path = root / "research_agent/inno/environment/markdown_browser/mdconvert.py"
    _replace_once(
        path,
        "from docling.document_converter import DocumentConverter as DocLingDocumentConverter",
        """try:
    from docling.document_converter import DocumentConverter as DocLingDocumentConverter
except ModuleNotFoundError:
    DocLingDocumentConverter = None""",
        "optional docling import",
    )
    _replace_once(
        path,
        """        if DocLingDocumentConverter is None:
            return None
        converter = DocLingDocumentConverter()
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


# ── 7. Lazy PaperMemory initialization ────────────────────────────────────


def _patch_paper_memory(root: Path) -> None:
    path = root / "research_agent/inno/environment/markdown_browser/requests_markdown_browser.py"
    _replace_once(
        path,
        """        platform = 'OpenAI'
        self._memory = PaperMemory(project_path="./paper_db", db_name=".paper_memory_" + platform, platform=platform, api_key=os.getenv("OPENAI_API_KEY"), embedding_model='text-embedding-3-small')""",
        "        self._memory = None",
        "lazy paper memory initialization",
    )
    _replace_once(
        path,
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


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    root = Path.cwd()
    marker = root / ".tdc_admet_tox_ai_researcher_adapter_applied"
    if marker.exists():
        return 0

    _patch_canonical_imports(root)
    _patch_tools_init(root)
    _patch_agents_init(root)
    _patch_dataset_setup(root)
    _patch_docker_env(root)
    _patch_native_flow(root)
    _patch_mdconvert(root)
    _patch_paper_memory(root)

    marker.write_text("tdc_admet_tox_ai_researcher_adapter_v1\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"
CONFIG = ROOT / "real_eval/config/seven_tdc_admet_tox_gpt_fullrun_frameworks.json"
VALIDATOR = ROOT / "real_eval/scripts/validate_framework_run.py"
GENERATOR = ROOT / "automation/scripts/generate_tdc_admet_tox_native_inputs.py"
PREFLIGHT = ROOT / "real_eval/scripts/preflight_seven_serial_tdc_admet_tox.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_common_fullrun_keeps_hidden_labels_outside_framework_container() -> None:
    text = read(COMMON)
    docker_block = text[text.index("declare -a docker_cmd=(") : text.index("timeout 7200s")]

    assert 'docker network create --internal "$NETWORK_NAME"' in text
    assert '--network "$NETWORK_NAME"' in docker_block
    assert 'CLIENT_RELAY_BASE_URL="http://tdc-gpt-relay:8787/v1"' in text
    assert "TDC_ADMET_TOX_HIDDEN_LABELS_ROOT" not in docker_block
    assert "HIDDEN_LABELS_FILE" not in docker_block
    assert '-v "$DATASET_ROOT:/data/tdc_admet_tox:ro"' in docker_block
    assert "/var/run/docker.sock" not in text
    assert "RESEARCHCLAWEVAL_HOST_WORKSPACE" not in docker_block
    assert "RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT" not in docker_block
    assert 'chmod 700 "$CODEX_HOME_DIR"' in text
    assert 'chmod 600 "$CODEX_HOME_DIR/config.toml"' in text
    assert "redact_env_secrets.py" in text
    assert 'hidden_labels_projected": False' in text
    assert '-v "$DATASET_ROOT:$FRAMEWORK_CONTAINER_WORKDIR/data/tdc_admet_tox:ro"' in text


def test_host_scoring_is_strictly_after_framework_audit() -> None:
    text = read(COMMON)

    framework_audit = text.index("--stage framework")
    host_score = text.index("run_tdc_admet_tox_host_score.py")
    final_audit = text.index("--stage final")
    assert framework_audit < host_score < final_audit
    assert 'if [[ "$research_completed" == true ]]' in text
    assert '--output-score "$WORKSPACE/score.json"' in text


def test_official_skill_host_requires_runtime_install_evidence() -> None:
    text = read(COMMON)

    assert 'FRAMEWORK_EXECUTOR_KIND" == "official_framework_skill' in text
    assert "$WORKSPACE/.aris/installed-skills-codex.txt" in text
    assert "$WORKSPACE/.agents/skills/research-pipeline" in text
    assert "$WORKSPACE/aris_tdc_admet_tox_last_message.txt" in text


def test_native_completion_requires_observed_process_commands() -> None:
    text = read(COMMON)

    assert 'FRAMEWORK_NATIVE_PROCESS_MARKERS="${FRAMEWORK_NATIVE_PROCESS_MARKERS:?' in text
    assert 'NATIVE_STDOUT_FILE="$LOG_DIR/native_stdout.log"' in text
    assert 'NATIVE_PROCESS_EVIDENCE_FILE="$BASE/native_process_evidence.json"' in text
    assert '| tee -a "$LOG_FILE" "$NATIVE_STDOUT_FILE"' in text
    assert '"all_passed": bool(checks) and all(row["found"] for row in checks)' in text
    assert "native_evidence_ok=0" in text


def test_supported_fullruns_use_documented_native_entrypoints() -> None:
    expected = {
        "01": "python research_agent/run_infer_idea.py",
        "02": "python3 launch_scientist_bfts.py",
        "03": "bash tools/install_aris_codex.sh",
        "04": "python3 -m researchclaw.cli run",
        "05": 'ds --home "$DS_HOME" run run-experiment',
        "07": "/opt/venv/bin/evoscientist",
    }
    for framework_id, marker in expected.items():
        path = next((ROOT / "real_eval/scripts").glob(f"{framework_id}_*_tdc_admet_tox_fullrun.sh"))
        text = read(path)
        assert marker in text
        assert "FRAMEWORK_NATIVE_PROCESS_MARKERS" in text
        assert "PS4='NATIVE_CMD> '" in text
        assert "set -x" in text
        if framework_id == "03":
            assert 'FRAMEWORK_EXECUTOR_KIND="official_framework_skill"' in text
            assert "skills/skills-codex/" in text
            assert "rm -rf .aris .agents" in text
            assert "codex exec --yolo" in text
        else:
            assert "codex exec" not in text
        assert "tdc_admet_tox_framework_fullrun.sh" in text


def test_non_admitted_framework_is_retained_as_explicit_outcome() -> None:
    drclaw = read(ROOT / "real_eval/scripts/06_drclaw_tdc_admet_tox_fullrun.sh")

    assert "blocked_benchmark_authorization" in drclaw
    assert "section 8.6" in drclaw


def test_fullrun_matrix_is_seven_framework_gpt_only() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert payload["topic_id"] == "tdc_admet_tox"
    assert payload["evaluation_variant"] == "gpt"
    assert payload["comparison_mode"] == "native_framework_orchestration"
    assert payload["model"] == "gpt-5.4"
    assert payload["frameworks"][0]["required_images"] == ["ai-researcher:runtime-ready"]
    assert payload["frameworks"][4]["required_images"] == [
        "deepscientist:tdc-runtime-ready"
    ]
    assert [row["id"] for row in payload["frameworks"]] == [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
    ]
    for row in payload["frameworks"]:
        wrapper = row["wrapper"].lower()
        assert "tdc_admet_tox" in wrapper
        assert all(
            marker not in wrapper for marker in ("babylm", "gave2", "arc_wbe_2026", "psydefdetect")
        )


def test_recovery_preflight_allows_only_ordered_framework_subsets() -> None:
    text = read(PREFLIGHT)

    assert 'recovery_of = config.get("recovery_of")' in text
    assert 'errors.append("framework_recovery_subset_invalid")' in text
    assert 'errors.append("framework_matrix_not_seven_ordered")' in text
    assert 'row_ids == [framework_id for framework_id in FRAMEWORK_IDS' in text


def test_generated_input_pack_has_no_other_topic_or_hidden_label_path(tmp_path: Path) -> None:
    output = tmp_path / "inputs"
    proc = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--output-root",
            str(output),
            "--primary-model",
            "gpt-5.4",
            "--provider-base-url",
            "http://tdc-gpt-relay:8787/v1",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in output.rglob("*")
        if path.is_file()
    ).lower()
    assert all(
        marker not in combined
        for marker in (
            "babylm",
            "gave2",
            "arc_wbe_2026",
            "arc-wbe-2026",
            "psydefdetect",
            "tdc_admet_tox_hidden_labels_root",
            "test_labels.csv",
        )
    )


def test_framework_specific_runtime_repairs_preserve_native_owners(tmp_path: Path) -> None:
    output = tmp_path / "inputs"
    proc = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--output-root",
            str(output),
            "--primary-model",
            "gpt-5.4",
            "--provider-base-url",
            "http://tdc-gpt-relay:8787/v1",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    auto_config = read(output / "AutoResearchClaw/config.tdc_admet_tox.yaml")
    assert "graceful_degradation: true" in auto_config
    assert "web_search:\n  enabled: false" in auto_config
    assert "enable_scholar: false" in auto_config

    auto_wrapper = read(ROOT / "real_eval/scripts/04_autoresearchclaw_tdc_admet_tox_fullrun.sh")
    assert "--skip-noncritical-stage" in auto_wrapper
    assert "python3 -m researchclaw.cli run" in auto_wrapper

    deep_wrapper = read(ROOT / "real_eval/scripts/05_deepscientist_tdc_admet_tox_fullrun.sh")
    assert "deepscientist:tdc-runtime-ready" in deep_wrapper
    assert "tar -xpf /opt/deepscientist-tdc-home.tar" in deep_wrapper
    assert 'ds --home "$DS_HOME" init' in deep_wrapper

    evo_wrapper = read(ROOT / "real_eval/scripts/07_evoscientist_tdc_admet_tox_fullrun.sh")
    assert 'FRAMEWORK_WORKSPACE_DATASET_PROJECTION="1"' in evo_wrapper
    assert "/opt/venv/bin/evoscientist" in evo_wrapper


def copy_files(source_root: Path, destination_root: Path, relative_paths: list[str]) -> None:
    for relative in relative_paths:
        source = source_root / relative
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def test_ai_researcher_adapter_matches_current_native_source(tmp_path: Path) -> None:
    workspace = tmp_path / "ai-researcher"
    copy_files(
        ROOT / "AI-Researcher",
        workspace,
        [
            "research_agent/inno/agents/__init__.py",
            "research_agent/inno/environment/utils.py",
            "research_agent/inno/environment/browser_env.py",
            "research_agent/inno/environment/docker_env.py",
            "research_agent/inno/environment/markdown_browser/mdconvert.py",
            "research_agent/inno/environment/markdown_browser/requests_markdown_browser.py",
            "research_agent/inno/tools/__init__.py",
            "research_agent/run_infer_idea.py",
            "research_agent/constant.py",
        ],
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "real_eval/adapters/ai_researcher/install_runtime_adapter.py")],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    docker_env = read(workspace / "research_agent/inno/environment/docker_env.py")
    assert "subprocess.Popen" in docker_env
    assert 'socket.create_connection(("127.0.0.1", self.communication_port)' in docker_env
    assert '"docker", "run"' not in docker_env
    assert "/var/run/docker.sock" not in docker_env
    assert "from research_agent.constant import BASE_IMAGES" in docker_env
    browser_env = read(workspace / "research_agent/inno/environment/browser_env.py")
    assert "from research_agent.inno.io_utils import read_file" in browser_env
    assert "tdc_admet_tox" in read(workspace / "research_agent/run_infer_idea.py")
    tools = read(workspace / "research_agent/inno/tools/__init__.py")
    assert 'import_tools_recursively(current_dir, "inno.tools")' not in tools
    assert 'import_tools_recursively(current_dir, \'inno.tools\')' not in tools
    assert 'f"research_agent.inno.tools.{module_name}"' in tools
    agents = read(workspace / "research_agent/inno/agents/__init__.py")
    assert "import_agents_recursively(current_dir, 'inno.agents')" not in agents
    assert 'f"research_agent.inno.agents.{module_name}"' in agents
    mdconvert = read(
        workspace / "research_agent/inno/environment/markdown_browser/mdconvert.py"
    )
    assert "except ModuleNotFoundError:" in mdconvert
    assert "pdfminer.high_level.extract_text(local_path)" in mdconvert
    browser = read(
        workspace
        / "research_agent/inno/environment/markdown_browser/requests_markdown_browser.py"
    )
    assert "from research_agent.inno.memory.paper_memory import PaperMemory" in browser
    assert "self._memory = None" in browser


def test_ai_researcher_fullrun_has_native_import_gate() -> None:
    wrapper = read(ROOT / "real_eval/scripts/01_ai_researcher_tdc_admet_tox_fullrun.sh")

    import_gate = wrapper.index("AI_RESEARCHER_TDC_IMPORT_GATE_OK")
    native_launch = wrapper.rindex("timeout 7000s python3 research_agent/run_infer_idea.py")
    assert import_gate < native_launch
    for module in ("plan_agent", "ml_agent", "judge_agent", "run_infer_idea"):
        assert module in wrapper


def test_ai_scientist_adapter_matches_current_native_source(tmp_path: Path) -> None:
    workspace = tmp_path / "ai-scientist"
    copy_files(
        ROOT / "AI-Scientist-v2",
        workspace,
        [
            "ai_scientist/llm.py",
            "ai_scientist/perform_ideation_temp_free.py",
            "ai_scientist/utils/token_tracker.py",
            "ai_scientist/tools/semantic_scholar.py",
            "ai_scientist/treesearch/agent_manager.py",
            "ai_scientist/treesearch/backend/backend_openai.py",
            "ai_scientist/treesearch/interpreter.py",
            "bfts_config.yaml",
            "launch_scientist_bfts.py",
        ],
    )
    env = {**dict(), "OPENAI_MODEL": "gpt-5.4"}
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "real_eval/adapters/tdc_admet_tox/patch_ai_scientist_v2.py"),
        ],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "MANDATORY TDC-ADMET-TOX NATIVE CONTRACT" in read(
        workspace / "ai_scientist/treesearch/agent_manager.py"
    )
    assert '"gpt-5.4"' in read(workspace / "ai_scientist/llm.py")
    ideation = read(workspace / "ai_scientist/perform_ideation_temp_free.py")
    parsed = ast.parse(ideation)
    parser_node = next(
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name == "_parse_action_blocks"
    )
    parser_module = ast.Module(
        body=[ast.Import(names=[ast.alias(name="json")]), ast.Import(names=[ast.alias(name="re")]), parser_node],
        type_ignores=[],
    )
    ast.fix_missing_locations(parser_module)
    namespace: dict[str, object] = {}
    exec(compile(parser_module, "<ai-scientist-parser-test>", "exec"), namespace)
    parse_actions = namespace["_parse_action_blocks"]
    response = '''ACTION:
SearchSemanticScholar
ARGUMENTS:
{"query": "SMILES toxicity"}
ACTION:
FinalizeIdea
ARGUMENTS:
{"idea": {"Name": "native_gpt_idea", "Experiments": ["run 1", "run 2"]}}
'''
    assert callable(parse_actions)
    assert parse_actions(response) == [
        ("SearchSemanticScholar", {"query": "SMILES toxicity"}),
        (
            "FinalizeIdea",
            {"idea": {"Name": "native_gpt_idea", "Experiments": ["run 1", "run 2"]}},
        ),
    ]


def test_fullrun_validator_accepts_explicit_unsupported_outcome(tmp_path: Path) -> None:
    run_root = tmp_path / "blocked"
    writer = ROOT / "real_eval/scripts/write_tdc_admet_tox_blocked_result.py"
    subprocess.run(
        [
            sys.executable,
            str(writer),
            "--run-root",
            str(run_root),
            "--framework",
            "UnavailableFramework",
            "--slug",
            "unavailable_framework_tdc_admet_tox_fullrun",
            "--status",
            "unsupported_native_entrypoint",
            "--reason",
            "Official CLI is unavailable.",
            "--native-entrypoint",
            "unavailable-framework run",
            "--entrypoint-source",
            "docs/unavailable-framework.md",
            "--provider-injection",
            "isolated GPT relay",
        ],
        check=True,
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--framework",
            "tdc_admet_tox_fullrun",
            "--run-root",
            str(run_root),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["status"] == "unsupported_native_entrypoint"


def test_fullrun_validator_uses_structured_isolation_for_official_skill(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "aris"
    workspace = run_root / "workspace"
    (run_root / "logs").mkdir(parents=True)
    (workspace / ".aris").mkdir(parents=True)
    (workspace / ".agents/skills").mkdir(parents=True)
    (workspace / ".aris/installed-skills-codex.txt").write_text(
        "skill\tresearch-pipeline\n", encoding="utf-8"
    )
    (workspace / ".agents/skills/research-pipeline").symlink_to(
        workspace / ".aris/installed-skills-codex.txt"
    )
    (workspace / "aris_tdc_admet_tox_last_message.txt").write_text(
        "native skill completed\n", encoding="utf-8"
    )
    manifest = {
        "task_id": "tdc_admet_tox",
        "evaluation_variant": "gpt",
        "framework_orchestration": True,
        "framework": "ARIS",
        "native_entrypoint": "install_aris_codex.sh -> /research-pipeline",
        "native_entrypoint_source": "skills/skills-codex/README.md",
        "actual_launch_command": "codex exec /research-pipeline",
        "provider_injection": "isolated relay",
        "executor_kind": "official_framework_skill",
        "evaluation_model": "gpt-5.4",
        "copied_inputs": ["TDC_ADMET_TOX_BRIEF.md", "automation/tdc_admet_tox_contract.md"],
        "network_isolation": {
            "framework_network_internal": True,
            "public_network_visible_to_framework": False,
        },
        "hidden_labels_projected": False,
        "host_score_after_framework_gate": True,
    }
    (run_root / "fullrun_manifest.json").write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )
    dimensions = {
        "research_completed": False,
        "scored": False,
        "contract_complete": False,
        "engineering_complete": True,
    }
    (run_root / "outcome.json").write_text(
        json.dumps(dimensions) + "\n", encoding="utf-8"
    )
    (run_root / "state.json").write_text(
        json.dumps({"status": "failed_native_research", **dimensions}) + "\n",
        encoding="utf-8",
    )
    (run_root / "logs/e2e.log").write_text(
        "Do not use GAVE2, ARC-WBE-2026, PsyDefDetect, BabyLM, "
        "TDC_ADMET_TOX_HIDDEN_LABELS_ROOT, or test_labels.csv.\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--framework",
            "tdc_admet_tox_fullrun",
            "--run-root",
            str(run_root),
        ],
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["status"] == "failed_validation"
    assert payload["warnings"] == ["research_not_completed"]
    assert payload["evidence"]["native_admission_ok"] is True
    assert payload["evidence"]["copied_input_pollution"] == []
    assert payload["evidence"]["workspace_path_pollution"] == []

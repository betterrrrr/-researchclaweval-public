from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
REGISTRY = ROOT / "real_eval/registry"
PRIMARY_CONFIGS = {
    "seven_babylm_frameworks.json": ("babylm", "fullrun"),
    "seven_psydefdetect_smoke_frameworks.json": ("psydefdetect", "smoke"),
    "seven_psydefdetect_fullrun_frameworks.json": ("psydefdetect", "fullrun"),
    "seven_tdc_admet_tox_gpt_smoke_frameworks.json": ("tdc_admet_tox", "smoke"),
    "seven_tdc_admet_tox_gpt_fullrun_frameworks.json": ("tdc_admet_tox", "fullrun"),
}
SERIAL_RUNNERS = {
    "run_seven_serial_babylm.sh": ("babylm", "fullrun"),
    "run_seven_serial_psydefdetect_smoke.sh": ("psydefdetect", "smoke"),
    "run_seven_serial_psydefdetect_fullrun.sh": ("psydefdetect", "fullrun"),
}


def load_registry(name: str) -> dict:
    return json.loads((REGISTRY / name).read_text(encoding="utf-8"))


def config_for_primary(topic_id: str, mode: str) -> dict:
    for config_name, key in PRIMARY_CONFIGS.items():
        if key == (topic_id, mode):
            return json.loads((ROOT / "real_eval/config" / config_name).read_text(encoding="utf-8"))
    raise AssertionError(f"primary config not found for topic={topic_id} mode={mode}")


def validator_names() -> set[str]:
    source = ROOT / "real_eval/scripts/validate_framework_run.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "validate":
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and target.id == "mapping":
                            if not isinstance(child.value, ast.Dict):
                                continue
                            keys = []
                            for key in child.value.keys:
                                if not isinstance(key, ast.Constant) or not isinstance(
                                    key.value, str
                                ):
                                    raise AssertionError(
                                        "validator mapping keys must be string literals"
                                    )
                                keys.append(key.value)
                            return set(keys)
    raise AssertionError("validate_framework_run.py mapping not found")


def test_topic_registry_contains_current_topics():
    topics = {item["id"]: item for item in load_registry("topics.json")["topics"]}
    assert set(topics) >= {"babylm", "gave2_task2"}
    for topic in topics.values():
        assert (ROOT / topic["contract_file"]).exists()
        assert topic["dataset_env"]
        assert topic["dataset_root"]
        if topic.get("status") == "blocked":
            assert topic["supported_modes"] == []
        else:
            assert topic["supported_modes"]


def test_arc_topic_is_registered() -> None:
    payload = load_registry("topics.json")
    topic = next(item for item in payload["topics"] if item["id"] == "arc_wbe_2026")
    assert topic["label"] == "ARC-WBE-2026"
    assert topic["contract_file"] == "automation/arc_wbe_2026_contract.md"
    assert topic["dataset_root"] == "data/arc_white_box_estimation_2026"
    assert topic["dataset_external_dir"] == "ARC_WBE_2026"
    assert topic["dataset_env"] == "ARC_WBE_2026_DATASET_ROOT"
    assert topic["supported_modes"] == ["input_pack", "smoke", "fullrun"]


def test_psydefdetect_topic_is_registered() -> None:
    payload = load_registry("topics.json")
    topic = next(item for item in payload["topics"] if item["id"] == "psydefdetect")
    assert topic["label"] == "PsyDefDetect"
    assert topic["contract_file"] == "automation/psydefdetect_contract.md"
    assert topic["dataset_root"] == "data/psydefdetect"
    assert topic["dataset_external_dir"] == "PsyDefDetect"
    assert topic["dataset_env"] == "PSYDEFDETECT_DATASET_ROOT"
    assert topic["supported_modes"] == ["smoke", "fullrun"]


def test_tdc_admet_tox_gpt_native_campaign_is_registered() -> None:
    payload = load_registry("topics.json")
    topic = next(item for item in payload["topics"] if item["id"] == "tdc_admet_tox")
    assert topic["label"] == "TDC-ADMET-Tox"
    assert topic["contract_file"] == "automation/tdc_admet_tox_contract.md"
    assert topic["dataset_root"] == "data/tdc_admet_tox/public"
    assert topic["dataset_env"] == "TDC_ADMET_TOX_DATASET_ROOT"
    assert topic["host_hidden_labels_env"] == "TDC_ADMET_TOX_HIDDEN_LABELS_ROOT"
    assert topic["supported_modes"] == ["smoke", "fullrun"]
    assert topic["status"] == "gpt_native_wrappers_ready_smoke_pending"
    assert (ROOT / topic["dataset_root"] / "dataset_manifest.json").is_file()

    rows = [row for row in load_registry("runs.json")["runs"] if row["topic_id"] == "tdc_admet_tox"]
    assert len(rows) == 14
    for mode in ("smoke", "fullrun"):
        mode_rows = [row for row in rows if row["mode"] == mode]
        assert [row["framework_id"] for row in mode_rows] == [
            "01",
            "02",
            "03",
            "04",
            "05",
            "06",
            "07",
        ]
        assert all(row["validator"] == f"tdc_admet_tox_{mode}" for row in mode_rows)
        assert all("tdc_admet_tox" in row["wrapper"] for row in mode_rows)


def test_arc_input_pack_has_seven_framework_rows() -> None:
    rows = load_registry("runs.json")["runs"]
    matches = [
        row for row in rows if row["topic_id"] == "arc_wbe_2026" and row["mode"] == "input_pack"
    ]
    assert len(matches) == 7


def test_arc_input_pack_uses_arc_validator_for_every_framework() -> None:
    rows = load_registry("runs.json")["runs"]
    matches = [
        row for row in rows if row["topic_id"] == "arc_wbe_2026" and row["mode"] == "input_pack"
    ]

    assert [row["framework_id"] for row in matches] == ["01", "02", "03", "04", "05", "06", "07"]
    assert all(row["validator"] == "arc_wbe_2026_input_pack" for row in matches)
    assert all("gave2" not in row["validator"].lower() for row in matches)


def test_psydefdetect_smoke_and_fullrun_have_seven_framework_rows() -> None:
    rows = load_registry("runs.json")["runs"]
    for mode in ["smoke", "fullrun"]:
        matches = [row for row in rows if row["topic_id"] == "psydefdetect" and row["mode"] == mode]
        assert len(matches) == 7
        assert [row["framework_id"] for row in matches] == [
            "01",
            "02",
            "03",
            "04",
            "05",
            "06",
            "07",
        ]
        for row in matches:
            assert "psydefdetect" in row["wrapper"]
            assert row["validator"] == f"psydefdetect_{mode}"
            assert all(
                forbidden not in row["wrapper"].lower()
                for forbidden in ["gave2", "arc_wbe_2026", "babylm"]
            )


def test_framework_registry_has_seven_frameworks():
    frameworks = load_registry("frameworks.json")["frameworks"]
    assert [item["id"] for item in frameworks] == ["01", "02", "03", "04", "05", "06", "07"]
    for framework in frameworks:
        assert framework["source_env"].startswith("RESEARCHCLAWEVAL_")
        assert (ROOT / framework["source_dir"]).exists()
        assert framework["supported_topics"]


def test_run_registry_references_existing_wrappers_and_validators():
    known_validators = validator_names()
    runs = load_registry("runs.json")["runs"]
    assert runs
    for run in runs:
        assert (ROOT / run["wrapper"]).exists(), run
        assert run["validator"] in known_validators, run
        assert run["run_dir"], run
        assert isinstance(run["required_paths"], list), run
        assert isinstance(run.get("required_images", []), list), run


def test_run_registry_matches_primary_configs():
    all_runs = load_registry("runs.json")["runs"]
    by_topic_mode = {}
    for run in all_runs:
        by_topic_mode.setdefault((run["topic_id"], run["mode"]), []).append(run)

    for config_name, key in PRIMARY_CONFIGS.items():
        registry_rows = by_topic_mode[key]
        config_rows = json.loads(
            (ROOT / "real_eval/config" / config_name).read_text(encoding="utf-8")
        )["frameworks"]

        registry_by_id = {row["framework_id"]: row for row in registry_rows}
        assert list(registry_by_id) == [row["id"] for row in config_rows]
        for row in config_rows:
            registry_row = registry_by_id[row["id"]]
            assert registry_row["wrapper"] == row["wrapper"]
            assert registry_row["validator"] == row["validator"]


def test_babylm_autoresearchclaw_task16_route_preserves_identity_shims():
    runs = load_registry("runs.json")["runs"]
    row = next(
        run
        for run in runs
        if run["topic_id"] == "babylm"
        and run["mode"] == "fullrun"
        and run["framework_id"] == "04"
    )
    assert row["wrapper"] == "real_eval/scripts/04_autoresearchclaw_babylm_gpt_fullrun.sh"
    assert row["run_dir"] == "04_autoresearchclaw_babylm_gpt_fullrun"
    assert row["validator"] == "autoresearchclaw_babylm_fullrun"

    gpt_wrapper = ROOT / row["wrapper"]
    kimi_wrapper = ROOT / "real_eval/scripts/04_autoresearchclaw_babylm_kimi_fullrun.sh"
    legacy_wrapper = ROOT / "real_eval/scripts/04_autoresearchclaw_real_babylm.sh"
    gpt_text = gpt_wrapper.read_text(encoding="utf-8")
    kimi_text = kimi_wrapper.read_text(encoding="utf-8")
    assert "AUTORESEARCHCLAW_BABYLM_GPT_NATIVE" in gpt_text
    assert "lib_autoresearchclaw_handoff.sh" in gpt_text
    assert "AUTORESEARCHCLAW_BABYLM_KIMI_NATIVE" in kimi_text
    assert "codex_kimi_k27_code_relay_container.toml" in kimi_text
    assert 'exec "$ROOT/real_eval/scripts/04_autoresearchclaw_babylm_gpt_fullrun.sh"' in kimi_text
    assert legacy_wrapper.is_file()

    topic2_rows = [run for run in runs if run["topic_id"] == "gave2_task2"]
    assert all("04_autoresearchclaw_real_babylm.sh" not in run["wrapper"] for run in topic2_rows)


def test_run_registry_respects_topic_and_framework_support():
    topics = {item["id"]: item for item in load_registry("topics.json")["topics"]}
    frameworks = {item["id"]: item for item in load_registry("frameworks.json")["frameworks"]}
    for run in load_registry("runs.json")["runs"]:
        topic = topics[run["topic_id"]]
        framework = frameworks[run["framework_id"]]
        assert run["mode"] in topic["supported_modes"], run
        assert run["topic_id"] in framework["supported_topics"], run


def test_registry_matrix_cli_can_render_markdown():
    import importlib.util

    script = ROOT / "real_eval/scripts/registry_matrix.py"
    spec = importlib.util.spec_from_file_location("registry_matrix", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    topics, frameworks, runs = module.load_registry()
    blocked_topic_rows = [
        run for run in runs if run["topic_id"] == "gave2_task2"
    ]
    assert blocked_topic_rows == []
    rendered = module.render_markdown(topics, frameworks, blocked_topic_rows)
    assert rendered == "| Topic | Mode | Framework | Wrapper | Validator |\n|---|---|---|---|---|"

    psydefdetect_rows = [
        run for run in runs if run["topic_id"] == "psydefdetect" and run["mode"] == "fullrun"
    ]
    rendered_psydefdetect = module.render_markdown(topics, frameworks, psydefdetect_rows)
    assert "PsyDefDetect" in rendered_psydefdetect
    assert "AI-Scientist-v2" in rendered_psydefdetect


def test_registry_to_config_matches_primary_configs():
    import importlib.util

    script = ROOT / "real_eval/scripts/registry_to_config.py"
    spec = importlib.util.spec_from_file_location("registry_to_config", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for config_name, (topic_id, mode) in PRIMARY_CONFIGS.items():
        generated = module.config_for(topic_id, mode)
        current = json.loads((ROOT / "real_eval/config" / config_name).read_text(encoding="utf-8"))
        assert generated == current


def test_registry_paths_resolve_default_and_external_roots():
    import importlib.util

    script = ROOT / "real_eval/scripts/registry_paths.py"
    spec = importlib.util.spec_from_file_location("registry_paths", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    topics, frameworks = module.load_registry()
    empty_env = {}
    assert (
        module.resolve_framework_source(frameworks["01"], ROOT, empty_env) == ROOT / "AI-Researcher"
    )
    assert (
        module.resolve_topic_dataset(topics["gave2_task2"], ROOT, empty_env)
        == ROOT / "data/gave2/task2"
    )

    external_env = {
        "RESEARCHCLAWEVAL_FRAMEWORKS_ROOT": "/opt/researchclaweval/frameworks",
        "RESEARCHCLAWEVAL_DATASETS_ROOT": "/opt/researchclaweval/datasets",
    }
    assert module.resolve_framework_source(frameworks["01"], ROOT, external_env) == Path(
        "/opt/researchclaweval/frameworks/AI-Researcher"
    )
    assert module.resolve_topic_dataset(topics["gave2_task2"], ROOT, external_env) == Path(
        "/opt/researchclaweval/datasets/GAVE2_preliminary"
    )

    specific_env = {
        "RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT": "/mnt/ai-researcher",
        "GAVE2_DATASET_ROOT": "/mnt/gave2-task2",
        **external_env,
    }
    assert module.resolve_framework_source(frameworks["01"], ROOT, specific_env) == Path(
        "/mnt/ai-researcher"
    )
    assert module.resolve_topic_dataset(topics["gave2_task2"], ROOT, specific_env) == Path(
        "/mnt/gave2-task2"
    )


def test_registry_paths_cli_can_render_markdown():
    script = ROOT / "real_eval/scripts/registry_paths.py"
    proc = subprocess.run(
        ["python3", str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "| Kind | ID | Name | Env Override | Exists | Resolved Path |" in proc.stdout
    assert "AI-Researcher" in proc.stdout
    assert "GAVE2-Task2" in proc.stdout


def test_registry_paths_cli_can_print_single_path():
    script = ROOT / "real_eval/scripts/registry_paths.py"
    proc = subprocess.run(
        ["python3", str(script), "--format", "path", "--kind", "framework", "--id", "01"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert proc.stdout.strip() == str(ROOT / "AI-Researcher")


def test_registry_tools_cli_use_home_entry_when_root_env_is_unset():
    paths_script = ROOT / "real_eval/scripts/registry_paths.py"
    config_script = ROOT / "real_eval/scripts/registry_to_config.py"
    matrix_script = ROOT / "real_eval/scripts/registry_matrix.py"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("RESEARCHCLAWEVAL_")
    }

    framework = subprocess.run(
        [
            "python3",
            str(paths_script),
            "--format",
            "path",
            "--kind",
            "framework",
            "--id",
            "04",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    dataset = subprocess.run(
        [
            "python3",
            str(paths_script),
            "--format",
            "path",
            "--kind",
            "dataset",
            "--id",
            "arc_wbe_2026",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    config = subprocess.run(
        ["python3", str(config_script), "--topic", "tdc_admet_tox", "--mode", "smoke"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    matrix = subprocess.run(
        ["python3", str(matrix_script), "--topic", "psydefdetect", "--mode", "fullrun"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert framework.stdout.strip() == str(ROOT / "AutoResearchClaw")
    assert dataset.stdout.strip() == str(ROOT / "data/arc_white_box_estimation_2026")
    assert len(json.loads(config.stdout)["frameworks"]) == 7
    assert "PsyDefDetect" in matrix.stdout


def test_registry_tools_cli_preserve_explicit_root_and_framework_override_precedence(tmp_path: Path):
    paths_script = ROOT / "real_eval/scripts/registry_paths.py"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("RESEARCHCLAWEVAL_")
    }
    env.update(
        {
            "RESEARCHCLAWEVAL_ROOT": str(ROOT),
            "RESEARCHCLAWEVAL_FRAMEWORKS_ROOT": str(tmp_path / "global-frameworks"),
            "RESEARCHCLAWEVAL_AUTORESEARCHCLAW_ROOT": str(tmp_path / "specific-framework"),
            "RESEARCHCLAWEVAL_DATASETS_ROOT": str(tmp_path / "datasets"),
        }
    )

    framework = subprocess.run(
        [
            "python3",
            str(paths_script),
            "--format",
            "path",
            "--kind",
            "framework",
            "--id",
            "04",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    dataset = subprocess.run(
        [
            "python3",
            str(paths_script),
            "--format",
            "path",
            "--kind",
            "dataset",
            "--id",
            "arc_wbe_2026",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert framework.stdout.strip() == str(tmp_path / "specific-framework")
    assert dataset.stdout.strip() == str(tmp_path / "datasets/ARC_WBE_2026")


def test_psydefdetect_wrappers_use_registry_source_resolution():
    wrappers = sorted((ROOT / "real_eval/scripts").glob("0*_psydefdetect_*.sh"))
    assert len(wrappers) == 14
    forbidden = [
        "}/AI-Researcher",
        "}/AI-Scientist-v2",
        "}/Auto-claude-code-research-in-sleep",
        "}/AutoResearchClaw",
        "}/DeepScientist",
        "}/dr-claw",
        "}/EvoScientist",
        "gave2_task2",
        "arc_wbe_2026",
        "babylm",
    ]
    for wrapper in wrappers:
        text = wrapper.read_text(encoding="utf-8")
        if wrapper.name == "06_drclaw_psydefdetect_fullrun.sh":
            assert 'FRAMEWORK_NATIVE_ENTRYPOINT="node server/cli.js chat' in text
            assert "DRCLAW_NATIVE_CHAT" in text
            assert "codex exec" not in text
            continue
        assert "real_eval_resolve_framework_source" in text, wrapper
        assert 'source "$ROOT/real_eval/scripts/lib_real_eval.sh"' in text, wrapper
        for marker in forbidden:
            assert marker not in text.lower(), wrapper


def test_gave2_fullrun_wrappers_use_registry_source_resolution():
    wrappers = sorted((ROOT / "real_eval/scripts").glob("0*_gave2_task2_fullrun.sh"))
    assert len(wrappers) == 7
    forbidden = [
        "}/AI-Researcher",
        "}/AI-Scientist-v2",
        "}/Auto-claude-code-research-in-sleep",
        "}/AutoResearchClaw",
        "}/DeepScientist",
        "}/dr-claw",
        "}/EvoScientist",
    ]
    for wrapper in wrappers:
        text = wrapper.read_text(encoding="utf-8")
        assert "real_eval_resolve_framework_source" in text, wrapper
        assert 'source "$ROOT/real_eval/scripts/lib_real_eval.sh"' in text, wrapper
        for marker in forbidden:
            assert marker not in text, wrapper


def test_blocked_topic2_rejects_config_and_dry_run(tmp_path):
    script = ROOT / "real_eval/scripts/run_registry_serial_dry_run.py"
    run_root = tmp_path / "registry-dry-run"
    run_root.mkdir()
    config_proc = subprocess.run(
        [
            "python3",
            str(ROOT / "real_eval/scripts/registry_to_config.py"),
            "--topic",
            "gave2_task2",
            "--mode",
            "fullrun",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert config_proc.returncode != 0
    assert "topic gave2_task2 is blocked" in config_proc.stderr

    dry_run_proc = subprocess.run(
        [
            "python3",
            str(script),
            "--topic",
            "gave2_task2",
            "--mode",
            "fullrun",
            "--run-id",
            "test-registry-dry-run",
            "--run-root",
            str(run_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert dry_run_proc.returncode != 0
    assert "topic gave2_task2 is blocked" in dry_run_proc.stderr
    assert not any(run_root.iterdir())


def test_blocked_topic2_autoresearchclaw_wrapper_rejects_direct_invocation():
    wrapper = ROOT / "real_eval/scripts/04_autoresearchclaw_gave2_task2_fullrun.sh"
    env = os.environ.copy()
    env["RESEARCHCLAWEVAL_ROOT"] = str(ROOT)

    result = subprocess.run(
        ["bash", str(wrapper)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 75
    assert "Topic2 (GAVE2-Task2) is blocked" in result.stderr
    assert result.stdout == ""


def test_serial_shell_helpers_write_expected_files(tmp_path):
    config = tmp_path / "frameworks.json"
    dry_run = tmp_path / "dry_run.jsonl"
    tsv = tmp_path / "frameworks.tsv"
    status = tmp_path / "serial_status.json"
    config.write_text(
        json.dumps(
            {
                "frameworks": [
                    {
                        "id": "01",
                        "name": "AI-Researcher",
                        "run_dir": "01_ai_researcher",
                        "wrapper": "real_eval/scripts/01_ai_researcher.sh",
                        "validator": "babylm",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    row = json.dumps({"id": "01", "status": "finished"})

    subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; '
                'real_eval_write_serial_dry_run "$2" "$3"; '
                'real_eval_write_frameworks_tsv "$2" "$4"; '
                'real_eval_write_serial_status "$5" "$6"'
            ),
            "bash",
            str(ROOT / "real_eval/scripts/lib_real_eval.sh"),
            str(config),
            str(dry_run),
            str(tsv),
            str(status),
            row,
        ],
        check=True,
    )

    assert json.loads(dry_run.read_text(encoding="utf-8"))["id"] == "01"
    assert tsv.read_text(encoding="utf-8").splitlines() == [
        "01\tAI-Researcher\t01_ai_researcher\treal_eval/scripts/01_ai_researcher.sh\tbabylm"
    ]
    assert json.loads(status.read_text(encoding="utf-8")) == {
        "rows": [{"id": "01", "status": "finished"}]
    }


def test_state_status_shell_helper_is_safe_for_missing_or_bad_state(tmp_path):
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    missing = tmp_path / "missing.json"
    good.write_text(json.dumps({"status": "finished"}), encoding="utf-8")
    bad.write_text("{not-json", encoding="utf-8")

    proc = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; real_eval_state_status "$2"; real_eval_state_status "$3"; real_eval_state_status "$4"',
            "bash",
            str(ROOT / "real_eval/scripts/lib_real_eval.sh"),
            str(good),
            str(missing),
            str(bad),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert proc.stdout.splitlines() == ["finished", "unknown", "unknown"]


def test_registry_enabled_serial_runners_generate_framework_config_and_dry_run(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "RESEARCHCLAWEVAL_ROOT": str(ROOT),
            "REAL_EVAL_USE_REGISTRY": "1",
            "REAL_EVAL_DRY_RUN": "1",
            "REAL_EVAL_SKIP_PREFLIGHT": "1",
        }
    )

    for script_name, (topic_id, mode) in SERIAL_RUNNERS.items():
        run_root = tmp_path / f"{topic_id}-{mode}"
        script = ROOT / "real_eval/scripts" / script_name
        subprocess.run(
            ["bash", str(script)],
            check=True,
            env=env
            | {
                "REAL_EVAL_RUN_ID": f"test-registry-{topic_id}-{mode}",
                "REAL_EVAL_RUN_ROOT": str(run_root),
            },
            capture_output=True,
            text=True,
        )

        generated_config = run_root / "registry_framework_config.json"
        dry_run = run_root / "dry_run.jsonl"
        assert generated_config.exists(), script_name
        assert dry_run.exists(), script_name
        assert json.loads(generated_config.read_text(encoding="utf-8")) == config_for_primary(
            topic_id, mode
        )
        assert len(dry_run.read_text(encoding="utf-8").splitlines()) == 7


def test_registry_dry_run_covers_active_topics_and_modes(tmp_path):
    script = ROOT / "real_eval/scripts/run_registry_serial_dry_run.py"
    active_modes = {
        "babylm": ["fullrun"],
        "arc_wbe_2026": ["input_pack", "smoke", "fullrun"],
        "psydefdetect": ["smoke", "fullrun"],
        "tdc_admet_tox": ["smoke", "fullrun"],
    }
    for topic_id, modes in active_modes.items():
        for mode in modes:
            run_root = tmp_path / f"{topic_id}-{mode}"
            proc = subprocess.run(
                [
                    "python3",
                    str(script),
                    "--topic",
                    topic_id,
                    "--mode",
                    mode,
                    "--run-id",
                    f"task16-{topic_id}-{mode}",
                    "--run-root",
                    str(run_root),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert json.loads(proc.stdout)["framework_count"] == 7
            assert len((run_root / "dry_run.jsonl").read_text(encoding="utf-8").splitlines()) == 7


def test_registry_matrix_covers_active_topics_and_modes():
    script = ROOT / "real_eval/scripts/registry_matrix.py"
    active_modes = {
        "babylm": ["fullrun"],
        "arc_wbe_2026": ["input_pack", "smoke", "fullrun"],
        "psydefdetect": ["smoke", "fullrun"],
        "tdc_admet_tox": ["smoke", "fullrun"],
    }
    for topic_id, modes in active_modes.items():
        for mode in modes:
            proc = subprocess.run(
                [
                    "python3",
                    str(script),
                    "--topic",
                    topic_id,
                    "--mode",
                    mode,
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert len(json.loads(proc.stdout)["rows"]) == 7


def test_explicit_framework_config_takes_precedence_over_registry(tmp_path):
    override_config = tmp_path / "override_frameworks.json"
    override_config.write_text(
        json.dumps(
            {
                "frameworks": [
                    {
                        "id": "x",
                        "name": "Override",
                        "run_dir": "override",
                        "wrapper": "real_eval/scripts/does_not_run.sh",
                        "validator": "override",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    run_root = tmp_path / "override-run"
    env = os.environ.copy()
    env.update(
        {
            "RESEARCHCLAWEVAL_ROOT": str(ROOT),
            "REAL_EVAL_USE_REGISTRY": "1",
            "REAL_EVAL_DRY_RUN": "1",
            "REAL_EVAL_SKIP_PREFLIGHT": "1",
            "REAL_EVAL_FRAMEWORK_CONFIG": str(override_config),
            "REAL_EVAL_RUN_ID": "test-explicit-config-precedence",
            "REAL_EVAL_RUN_ROOT": str(run_root),
        }
    )

    subprocess.run(
        ["bash", str(ROOT / "real_eval/scripts/run_seven_serial_gave2_task2.sh")],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert not (run_root / "registry_framework_config.json").exists()
    rows = [
        json.loads(line)
        for line in (run_root / "dry_run.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [
        {
            "id": "x",
            "name": "Override",
            "run_dir": "override",
            "wrapper": "real_eval/scripts/does_not_run.sh",
            "validator": "override",
        }
    ]


def test_arc_serial_config_selection_preserves_valid_override_and_rejects_wrong_mode(tmp_path):
    selector = ROOT / "real_eval/scripts/lib_real_eval.sh"

    valid_override = tmp_path / "arc-input-pack.json"
    valid_override.write_text(
        json.dumps({"frameworks": [{"id": "04", "validator": "arc_wbe_2026_input_pack"}]}),
        encoding="utf-8",
    )
    selected = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; real_eval_select_framework_config "$2" "$3" "$4" arc_wbe_2026 input_pack',
            "bash",
            str(selector),
            str(ROOT),
            str(tmp_path / "run-valid"),
            str(ROOT / "real_eval/config/arc_wbe_2026_kimi_smoke_frameworks.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "REAL_EVAL_FRAMEWORK_CONFIG": str(valid_override)},
    )
    assert selected.stdout.strip() == str(valid_override)

    wrong_mode = tmp_path / "arc-smoke.json"
    wrong_mode.write_text(
        json.dumps({"frameworks": [{"id": "04", "validator": "arc_wbe_2026_smoke"}]}),
        encoding="utf-8",
    )
    rejected = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; real_eval_select_framework_config "$2" "$3" "$4" arc_wbe_2026 input_pack',
            "bash",
            str(selector),
            str(ROOT),
            str(tmp_path / "run-wrong"),
            str(ROOT / "real_eval/config/arc_wbe_2026_kimi_smoke_frameworks.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "REAL_EVAL_FRAMEWORK_CONFIG": str(wrong_mode)},
    )
    assert rejected.returncode != 0
    assert "mode" in rejected.stderr


def test_arc_input_pack_default_config_is_mode_consistent() -> None:
    serial = (ROOT / "real_eval/scripts/run_seven_serial_arc_wbe_2026.sh").read_text(
        encoding="utf-8"
    )
    preflight = (ROOT / "real_eval/scripts/preflight_seven_serial_arc_wbe_2026.sh").read_text(
        encoding="utf-8"
    )

    assert "arc_wbe_2026_input_pack_frameworks.json" in serial
    assert "arc_wbe_2026_input_pack_frameworks.json" in preflight
    assert "arc_wbe_2026_kimi_smoke_frameworks.json" not in serial
    assert "arc_wbe_2026_kimi_smoke_frameworks.json" not in preflight

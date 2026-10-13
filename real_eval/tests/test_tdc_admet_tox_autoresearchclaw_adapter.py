from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).absolute().parents[2]
ADAPTER_PATH = ROOT / "real_eval/adapters/tdc_admet_tox/patch_autoresearchclaw.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("tdc_autoresearchclaw_adapter", ADAPTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_workspace(destination: Path) -> None:
    shutil.copytree(ROOT / "AutoResearchClaw", destination)


@pytest.fixture(autouse=True)
def explicit_current_artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTORESEARCHCLAW_ARTIFACT_ROOT", str(tmp_path / "artifacts"))


def apply_adapter(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER_PATH)],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )


def test_source_compatibility_matches_fresh_workspace(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = load_adapter()
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)

    assert adapter.check_version_compatibility(workspace)
    assert "source compatibility warning" not in caplog.text


def test_adapter_applies_to_matching_native_source(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)

    result = apply_adapter(workspace)

    assert result.returncode == 0, result.stderr
    design = (workspace / "researchclaw/pipeline/stage_impls/_experiment_design.py").read_text(
        encoding="utf-8"
    )
    assert "_max_conditions = 4" in design
    assert "TDC_ADMET_TOX_NATIVE_RUN" not in design


def test_runtime_path_is_native_and_explicitly_current() -> None:
    wrapper = (ROOT / "real_eval/scripts/04_autoresearchclaw_tdc_admet_tox_fullrun.sh").read_text(
        encoding="utf-8"
    )

    assert "python3 -m researchclaw.cli run" in wrapper
    assert 'export AUTORESEARCHCLAW_ARTIFACT_ROOT="${artifact_root}/deliverables"' in wrapper
    assert "TDC_ADMET_TOX_NATIVE_RUN" not in wrapper


def test_runtime_patch_does_not_mutate_native_outputs_or_code(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)
    native_paths = (
        "researchclaw/pipeline/stage_impls/_execution.py",
        "researchclaw/pipeline/runner.py",
        "researchclaw/pipeline/_helpers.py",
    )
    before = {path: (workspace / path).read_bytes() for path in native_paths}

    result = apply_adapter(workspace)

    assert result.returncode == 0, result.stderr
    assert {path: (workspace / path).read_bytes() for path in native_paths} == before
    assert "_load_trace_validation_metrics" not in "\n".join(
        (workspace / path).read_text(encoding="utf-8") for path in native_paths
    )
    assert "TDC_ADMET_TOX_NATIVE_RUN" not in result.stdout


def test_source_compatibility_warns_and_exact_patch_still_fails_closed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = load_adapter()
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)
    shared = workspace / "researchclaw/prompts/shared.py"
    shared.write_text(
        shared.read_text(encoding="utf-8").replace(
            "## Multi-Seed Experiment Requirement (MANDATORY — NO EXCEPTIONS)",
            "## Legacy Multi-Seed Requirement",
        ),
        encoding="utf-8",
    )

    assert not adapter.check_version_compatibility(workspace)
    assert "source compatibility warning" in caplog.text
    with pytest.raises(SystemExit, match="multi-seed enforcement prompt block"):
        adapter.patch_multi_seed_enforcement(workspace)


def write_framework_artifacts(root: Path, *, prediction_name: str = "predictions.csv") -> None:
    artifacts = root / "artifacts"
    artifacts.mkdir()
    (artifacts / prediction_name).write_text("sample_id,endpoint,probability\n1,AMES,0.5\n", encoding="utf-8")
    (artifacts / "experiment_trace.json").write_text('{"task_id":"tdc_admet_tox"}\n', encoding="utf-8")
    (artifacts / "final_report.md").write_text("# Framework report\n", encoding="utf-8")


def test_complete_handoff_promotes_framework_artifacts_without_score(tmp_path: Path) -> None:
    adapter = load_adapter()
    write_framework_artifacts(tmp_path)

    result = adapter.patch_workspace_handoff(tmp_path)

    assert result["status"] == "done"
    assert (tmp_path / "predictions.csv").is_file()
    assert (tmp_path / "experiment_trace.json").is_file()
    assert (tmp_path / "final_report.md").is_file()
    assert not (tmp_path / "score.json").exists()


def test_missing_predictions_fails_closed(tmp_path: Path) -> None:
    adapter = load_adapter()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "experiment_trace.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "final_report.md").write_text("report\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="predictions.csv or submission.csv"):
        adapter.patch_workspace_handoff(tmp_path)


@pytest.mark.parametrize("missing_name", ["experiment_trace.json", "final_report.md"])
def test_missing_trace_or_report_fails_closed(tmp_path: Path, missing_name: str) -> None:
    adapter = load_adapter()
    write_framework_artifacts(tmp_path)
    (tmp_path / "artifacts" / missing_name).unlink()

    with pytest.raises(SystemExit, match=missing_name):
        adapter.patch_workspace_handoff(tmp_path)


def test_stale_root_score_is_rejected_and_unchanged(tmp_path: Path) -> None:
    adapter = load_adapter()
    write_framework_artifacts(tmp_path)
    score = tmp_path / "score.json"
    stale_score = '{"main_score":0.01,"score_source":"stale"}\n'
    score.write_text(stale_score, encoding="utf-8")

    with pytest.raises(SystemExit, match="score.json"):
        adapter.patch_workspace_handoff(tmp_path)

    assert score.read_text(encoding="utf-8") == stale_score
    assert not (tmp_path / "predictions.csv").exists()


def test_handoff_does_not_leak_hidden_label_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = load_adapter()
    write_framework_artifacts(tmp_path)
    hidden_root = "/host-only/hidden-labels-do-not-leak"
    monkeypatch.setenv("TDC_ADMET_TOX_HIDDEN_LABELS_ROOT", hidden_root)

    result = adapter.patch_workspace_handoff(tmp_path)

    assert hidden_root not in str(result)
    assert hidden_root not in (ROOT / "real_eval/adapters/tdc_admet_tox/patch_autoresearchclaw.py").read_text(
        encoding="utf-8"
    )


def test_first_patch_then_handoff_sequence_does_not_double_patch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)
    result1 = subprocess.run(
        [sys.executable, str(ADAPTER_PATH)],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result1.returncode == 0, result1.stderr

    artifact_root = workspace / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "predictions.csv").write_text(
        "sample_id,endpoint,probability\n1,AMES,0.5\n", encoding="utf-8"
    )
    (artifact_root / "experiment_trace.json").write_text(
        '{"task_id":"tdc_admet_tox"}\n', encoding="utf-8"
    )
    (artifact_root / "final_report.md").write_text("# Framework report\n", encoding="utf-8")
    env = {**os.environ, "AUTORESEARCHCLAW_ARTIFACT_ROOT": str(artifact_root), "WORKSPACE": str(workspace)}
    result2 = subprocess.run(
        [sys.executable, str(ADAPTER_PATH), "--handoff"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result2.returncode == 0, result2.stderr
    handoff = json.loads(result2.stdout)
    assert handoff["status"] == "done"
    assert (workspace / "predictions.csv").is_file()
    assert (workspace / "experiment_trace.json").is_file()
    assert (workspace / "final_report.md").is_file()
    assert (workspace / "final_report.md").read_text(encoding="utf-8") == "# Framework report\n"


def test_handoff_uses_only_explicit_current_artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = load_adapter()
    current = tmp_path / "artifacts" / "current"
    stale = tmp_path / "artifacts" / "stale"
    current.mkdir(parents=True)
    stale.mkdir(parents=True)
    (current / "predictions.csv").write_text(
        "sample_id,endpoint,probability\n1,AMES,0.5\n", encoding="utf-8"
    )
    (current / "experiment_trace.json").write_text('{"task_id":"tdc_admet_tox"}\n', encoding="utf-8")
    (current / "final_report.md").write_text("# Current report\n", encoding="utf-8")
    (stale / "predictions.csv").write_text(
        "sample_id,endpoint,probability\n1,AMES,0.1\n", encoding="utf-8"
    )
    (stale / "experiment_trace.json").write_text('{"task_id":"stale"}\n', encoding="utf-8")
    (stale / "final_report.md").write_text("# Stale report\n", encoding="utf-8")
    monkeypatch.setenv("AUTORESEARCHCLAW_ARTIFACT_ROOT", str(current))

    result = adapter.patch_workspace_handoff(tmp_path)

    assert result["status"] == "done"
    assert (tmp_path / "predictions.csv").read_text(encoding="utf-8").startswith("sample_id")
    assert "stale" not in (tmp_path / "predictions.csv").read_text(encoding="utf-8")

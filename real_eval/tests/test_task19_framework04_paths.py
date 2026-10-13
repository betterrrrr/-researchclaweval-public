from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "real_eval/scripts/lib_autoresearchclaw_handoff.sh"
TDC_PATCH = ROOT / "real_eval/adapters/tdc_admet_tox/patch_autoresearchclaw.py"
VALIDATOR = ROOT / "real_eval/scripts/validate_framework_run.py"


def run_shell(workspace: Path, topic: str, artifact_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"source {HANDOFF!s}; autoresearchclaw_handoff {topic} \"$1\" \"$2\"", "bash", str(workspace), str(artifact_root)],
        text=True,
        capture_output=True,
        check=False,
    )


def write_artifacts(root: Path, topic: str) -> None:
    deliverables = root / "deliverables"
    deliverables.mkdir(parents=True)
    names = {
        "arc_wbe_2026": ("estimator.py", "submission.json", "experiment_trace.json", "final_report.md", "score_evidence.json"),
        "babylm": ("research_idea.json", "experiment_trace.json", "final_report.md"),
        "psydefdetect": ("predictions.jsonl", "score.json", "experiment_trace.json", "final_report.md"),
        "tdc_admet_tox": ("predictions.csv", "experiment_trace.json", "final_report.md"),
    }[topic]
    for name in names:
        (deliverables / name).write_text(name, encoding="utf-8")


def write_babylm_current_artifacts(run_root: Path, run_id: str) -> None:
    workspace = run_root / "workspace"
    deliverables = workspace / "artifacts" / f"babylm-{run_id}" / "deliverables"
    deliverables.mkdir(parents=True)
    for name in ("research_idea.json", "experiment_trace.json", "final_report.md"):
        contents = name
        (deliverables / name).write_text(contents, encoding="utf-8")
        (workspace / name).write_text(contents, encoding="utf-8")


def run_current_babylm_validator(run_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(VALIDATOR),
            "--framework",
            "autoresearchclaw_babylm_fullrun",
            "--run-root",
            str(run_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_valid_ids_and_normal_four_topic_handoffs(tmp_path: Path) -> None:
    ids = ["run-20260812-01", "topic4_native.v2"]
    for run_id in ids:
        result = subprocess.run(
            ["bash", "-c", f"source {HANDOFF!s}; autoresearchclaw_validate_run_id \"$1\"", "bash", run_id],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0

    for topic in ("arc_wbe_2026", "babylm", "psydefdetect", "tdc_admet_tox"):
        workspace = tmp_path / topic
        artifact_root = workspace / "artifacts" / "current"
        write_artifacts(artifact_root, topic)
        result = run_shell(workspace, topic, artifact_root)
        assert result.returncode == 0, result.stderr


def test_run_id_rejects_traversal_and_slash(tmp_path: Path) -> None:
    for run_id in ("../escape", "topic/escape", "", "bad run", ".", ".."):
        result = subprocess.run(
            ["bash", "-c", f"source {HANDOFF!s}; autoresearchclaw_validate_run_id \"$1\"", "bash", run_id],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0


def test_current_babylm_fullrun_validator_accepts_only_its_run_scoped_handoff(tmp_path: Path) -> None:
    run_id = "fresh-run-20260812"
    run_root = tmp_path / run_id / "04_autoresearchclaw_babylm_gpt_fullrun"
    write_babylm_current_artifacts(run_root, run_id)

    result = run_current_babylm_validator(run_root)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "finished"


def test_current_babylm_fullrun_validator_rejects_stale_run_artifacts(tmp_path: Path) -> None:
    run_id = "fresh-run-20260812"
    run_root = tmp_path / run_id / "04_autoresearchclaw_babylm_gpt_fullrun"
    write_babylm_current_artifacts(run_root, "stale-run-20260811")

    result = run_current_babylm_validator(run_root)

    assert result.returncode == 13
    assert json.loads(result.stdout)["status"] == "failed_no_artifacts"


def test_shared_handoff_rejects_symlink_file_dir_and_outside_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    root = workspace / "artifacts" / "current"
    write_artifacts(root, "babylm")
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (root / "deliverables" / "final_report.md").unlink()
    (root / "deliverables" / "final_report.md").symlink_to(outside)
    assert run_shell(workspace, "babylm", root).returncode != 0

    root2 = workspace / "artifacts" / "current2"
    write_artifacts(root2, "babylm")
    (root2 / "deliverables").rename(root2 / "deliverables-real")
    (root2 / "deliverables").symlink_to(root2 / "deliverables-real", target_is_directory=True)
    assert run_shell(workspace, "babylm", root2).returncode != 0

    outside_root = tmp_path / "outside-root"
    write_artifacts(outside_root, "babylm")
    traversal = workspace / "artifacts" / ".." / ".." / "outside-root"
    assert run_shell(workspace, "babylm", traversal).returncode != 0


def load_tdc_module():
    spec = importlib.util.spec_from_file_location("task19_tdc_patch", TDC_PATCH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tdc_handoff_requires_explicit_current_root_and_rejects_symlink(tmp_path: Path, monkeypatch) -> None:
    module = load_tdc_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("WORKSPACE", str(workspace))
    monkeypatch.delenv("AUTORESEARCHCLAW_ARTIFACT_ROOT", raising=False)
    try:
        module.patch_workspace_handoff(workspace)
    except SystemExit as exc:
        assert "explicitly configured" in str(exc)
    else:
        raise AssertionError("missing explicit TDC artifact root was accepted")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "predictions.csv").write_text("outside", encoding="utf-8")
    (outside / "experiment_trace.json").write_text("trace", encoding="utf-8")
    (outside / "final_report.md").write_text("report", encoding="utf-8")
    current = workspace / "artifacts" / "current"
    current.mkdir(parents=True)
    (current / "predictions.csv").symlink_to(outside / "predictions.csv")
    (current / "experiment_trace.json").write_text("trace", encoding="utf-8")
    (current / "final_report.md").write_text("report", encoding="utf-8")
    monkeypatch.setenv("AUTORESEARCHCLAW_ARTIFACT_ROOT", str(current))
    try:
        module.patch_workspace_handoff(workspace)
    except SystemExit as exc:
        assert "symlinks" in str(exc)
    else:
        raise AssertionError("TDC symlink artifact was accepted")

    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()
    for name in ("predictions.csv", "experiment_trace.json", "final_report.md"):
        (outside_root / name).write_text(name, encoding="utf-8")
    monkeypatch.setenv("AUTORESEARCHCLAW_ARTIFACT_ROOT", str(outside_root))
    try:
        module.patch_workspace_handoff(workspace)
    except SystemExit as exc:
        assert "inside the current workspace" in str(exc)
    else:
        raise AssertionError("TDC outside canonical artifact root was accepted")

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from real_eval.adapters.psydefdetect import patch_autoresearchclaw

ROOT = Path(__file__).parents[3]
ADAPTER = ROOT / "real_eval/adapters/psydefdetect/patch_autoresearchclaw.py"


def apply_adapter(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER), str(workspace)],
        capture_output=True,
        text=True,
        check=False,
    )


def copy_workspace(destination: Path) -> None:
    shutil.copytree(ROOT / "AutoResearchClaw", destination)


def test_main_rejects_missing_workspace_argument() -> None:
    with pytest.raises(SystemExit, match="usage: patch_autoresearchclaw.py WORKSPACE"):
        patch_autoresearchclaw.main([])


def test_source_compatibility_matches_fresh_workspace(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)

    assert patch_autoresearchclaw.check_version_compatibility(workspace)
    assert "source compatibility warning" not in caplog.text


def test_source_compatibility_warns_without_blocking(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)
    surveyor = workspace / "researchclaw/agents/benchmark_agent/surveyor.py"
    surveyor.write_text(
        surveyor.read_text(encoding="utf-8").replace(
            "        domain_ids = self._match_domains(topic)\n"
            "        if hypothesis:\n"
            "            domain_ids = list(dict.fromkeys(\n"
            "                domain_ids + self._match_domains(hypothesis)\n"
            "            ))",
            "        legacy_domain_ids = self._match_domains(topic)",
        ),
        encoding="utf-8",
    )

    assert not patch_autoresearchclaw.check_version_compatibility(workspace)
    assert "source compatibility warning" in caplog.text


def test_patch_source_contains_every_replace_marker() -> None:
    tree = ast.parse(patch_autoresearchclaw.PATCH_SOURCE)
    old_values = [
        assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "old"
            for target in assignment.targets
        )
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
    ]

    assert len(old_values) == 28
    assert all(old_values)
    assert all(
        marker.strip().splitlines()[0] in patch_autoresearchclaw.PATCH_SOURCE
        for marker in old_values
    )


PATCH_FUNCTION_MARKERS = {
    "patch_surveyor_domain_routing": (
        "psydefdetect_topic = \"psydefdetect\" in topic.lower()",
    ),
    "patch_experiment_design_validation": (
        "def _psydefdetect_plan_errors",
        "_max_conditions = 2",
    ),
    "patch_code_generation_validation": (
        "PsyDefDetect framework-owned delivery is incomplete",
    ),
    "patch_literature_collection": (
        "PsyDefDetect candidate projection: selected",
    ),
    "patch_stage12_handoff": (
        "PsyDefDetect framework handoff is invalid",
        "psydefdetect_handoff_validation.json",
    ),
    "patch_stage13_no_refine": (
        "additional refinement runs are not authorized",
    ),
}


@pytest.mark.parametrize(
    ("patch_name", "markers"),
    PATCH_FUNCTION_MARKERS.items(),
    ids=PATCH_FUNCTION_MARKERS,
)
def test_patch_function_marker_is_embedded(
    patch_name: str, markers: tuple[str, ...]
) -> None:
    assert patch_name in PATCH_FUNCTION_MARKERS
    assert all(marker in patch_autoresearchclaw.PATCH_SOURCE for marker in markers)


PATCH_APPLICATIONS = {
    "patch_surveyor_domain_routing": (
        "researchclaw/agents/benchmark_agent/surveyor.py",
        "psydefdetect_topic = \"psydefdetect\" in topic.lower()",
    ),
    "patch_experiment_design_validation": (
        "researchclaw/pipeline/stage_impls/_experiment_design.py",
        "def _psydefdetect_plan_errors",
    ),
    "patch_code_generation_validation": (
        "researchclaw/pipeline/code_agent.py",
        "PsyDefDetect framework-owned delivery is incomplete",
    ),
    "patch_literature_collection": (
        "researchclaw/pipeline/stage_impls/_literature.py",
        "PsyDefDetect candidate projection: selected",
    ),
    "patch_stage12_handoff": (
        "researchclaw/pipeline/stage_impls/_execution.py",
        "PsyDefDetect framework handoff is invalid",
    ),
    "patch_stage13_no_refine": (
        "researchclaw/pipeline/stage_impls/_execution.py",
        "additional refinement runs are not authorized",
    ),
}


@pytest.mark.parametrize(
    ("patch_name", "relative_path", "marker"),
    ((name, *application) for name, application in PATCH_APPLICATIONS.items()),
    ids=PATCH_APPLICATIONS,
)
def test_patch_function_applies_to_fresh_workspace(
    tmp_path: Path, patch_name: str, relative_path: str, marker: str
) -> None:
    workspace = tmp_path / patch_name
    copy_workspace(workspace)

    result = apply_adapter(workspace)

    assert result.returncode == 0, result.stderr
    assert marker in (workspace / relative_path).read_text(encoding="utf-8")

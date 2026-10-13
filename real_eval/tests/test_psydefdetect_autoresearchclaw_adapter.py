from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
ADAPTER = ROOT / "real_eval/adapters/psydefdetect/patch_autoresearchclaw.py"
HANDOFF = ROOT / "real_eval/scripts/lib_autoresearchclaw_handoff.sh"


def copy_workspace(destination: Path) -> None:
    shutil.copytree(ROOT / "AutoResearchClaw", destination)


def apply_adapter(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER), str(workspace)],
        capture_output=True,
        text=True,
    )


def test_adapter_applies_current_native_source_when_workspace_is_fresh(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)

    result = apply_adapter(workspace)

    assert result.returncode == 0, result.stderr
    design = (workspace / "researchclaw/pipeline/stage_impls/_experiment_design.py").read_text(
        encoding="utf-8"
    )
    code_agent = (workspace / "researchclaw/pipeline/code_agent.py").read_text(
        encoding="utf-8"
    )
    execution = (workspace / "researchclaw/pipeline/stage_impls/_execution.py").read_text(
        encoding="utf-8"
    )
    assert "def _psydefdetect_plan_errors" in design
    assert "compute_budget.total_runs must equal 2" in design
    assert "PsyDefDetect framework-owned delivery" in code_agent
    assert "PsyDefDetect framework handoff is invalid" in execution
    assert "additional refinement runs are not authorized" in execution


def test_adapter_rejects_changed_native_insertion_point_when_source_drifts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)
    surveyor = workspace / "researchclaw/agents/benchmark_agent/surveyor.py"
    surveyor.write_text(
        surveyor.read_text(encoding="utf-8").replace(
            "domain_ids = self._match_domains(topic)",
            "legacy_domain_ids = self._match_domains(topic)",
        ),
        encoding="utf-8",
    )

    result = apply_adapter(workspace)

    assert result.returncode != 0
    assert "benchmark-domain routing insertion point not found" in result.stderr


def test_adapter_keeps_native_scorer_trace_and_handoff_contracts() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    for marker in (
        "/workspace/automation/scripts/run_psydefdetect_local_score.py",
        "subprocess.run(..., check=True)",
        "experiment_trace.json must contain exactly two experiments",
        "framework_native_execution",
        "selected_experiment_id",
        "psydefdetect_handoff_validation.json",
        "additional refinement runs are not authorized",
    ):
        assert marker in source


def test_stage8_adapter_writes_framework_owned_idea_lock_when_topic_is_psydefdetect(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    copy_workspace(workspace)

    result = subprocess.run(
        [
            "bash",
            "-lc",
            f"source {HANDOFF}; apply_autoresearchclaw_stage8_idea_lock_adapter {workspace}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    synthesis = (workspace / "researchclaw/pipeline/stage_impls/_synthesis.py").read_text(
        encoding="utf-8"
    )
    assert "def _framework_stage8_idea_fields" in synthesis
    assert "research_idea_lock_event.json" in synthesis
    assert '"writer": "AutoResearchClaw"' in synthesis

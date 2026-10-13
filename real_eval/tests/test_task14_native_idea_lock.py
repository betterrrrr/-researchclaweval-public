from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "real_eval/scripts/lib_autoresearchclaw_handoff.sh"
ACTIVE_TOPICS = ("arc_wbe_2026", "babylm", "tdc_admet_tox", "psydefdetect")
WRAPPERS = {
    "arc_wbe_2026": ROOT / "real_eval/scripts/04_autoresearchclaw_arc_wbe_2026_fullrun.sh",
    "babylm": ROOT / "real_eval/scripts/04_autoresearchclaw_babylm_gpt_fullrun.sh",
    "tdc_admet_tox": ROOT / "real_eval/scripts/04_autoresearchclaw_tdc_admet_tox_fullrun.sh",
    "psydefdetect": ROOT / "real_eval/scripts/04_autoresearchclaw_psydefdetect_fullrun.sh",
}


@pytest.mark.parametrize("topic", ACTIVE_TOPICS)
def test_active_wrapper_installs_native_stage8_without_host_idea_generation(topic: str) -> None:
    source = WRAPPERS[topic].read_text(encoding="utf-8")

    assert "apply_autoresearchclaw_stage8_idea_lock_adapter \"/workspace\"" in source
    assert "generate_research_idea_json" not in source


def test_stage8_adapter_is_topic_independent_and_schema_named() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert 'if "psydefdetect" in config.research.topic.lower()' not in source
    for field in ("method_rationale", "comparison_logic", "source_artifact", "locked_at"):
        assert field in source
    assert "artifact_sha256" in source
    assert "first_experiment_started_at" in source


@pytest.mark.parametrize("topic", ACTIVE_TOPICS)
def test_schema_gate_accepts_framework_stage8_fixture(tmp_path: Path, topic: str) -> None:
    workspace = tmp_path / topic
    workspace.mkdir()
    idea = {
        "framework": "AutoResearchClaw",
        "topic": topic,
        "source_artifact": "stage-08/hypotheses.md",
        "hypothesis": "Framework-generated hypothesis",
        "method_rationale": "Framework-generated rationale",
        "expected_failure_modes": "Framework-generated failure modes",
        "comparison_logic": "Framework-generated comparison logic",
        "idea_locked_before_experiments": True,
        "lock_event_id": "stage-08-research-idea-fixture",
        "locked_at": "2026-08-12T12:00:00+00:00",
    }
    idea_path = workspace / "research_idea.json"
    idea_path.write_text(json.dumps(idea, indent=2) + "\n", encoding="utf-8")
    event = {
        "event": "research_idea_locked",
        "event_id": idea["lock_event_id"],
        "owner": "framework",
        "writer": "AutoResearchClaw",
        "artifact": "research_idea.json",
        "source_artifact": idea["source_artifact"],
        "timestamp": idea["locked_at"],
        "artifact_sha256": hashlib.sha256(idea_path.read_bytes()).hexdigest(),
    }
    (workspace / "research_idea_lock_event.json").write_text(
        json.dumps(event, indent=2) + "\n", encoding="utf-8"
    )
    trace = {
        "idea_artifact": "research_idea.json",
        "idea_locked_before_experiments": True,
        "first_experiment_started_at": "2026-08-12T12:01:00+00:00",
    }
    trace_path = workspace / "experiment_trace.json"
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    idea_path.touch()
    trace_path.touch()

    result = subprocess.run(
        ["bash", "-lc", f"source {HANDOFF}; verify_framework_research_idea_json {workspace}"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

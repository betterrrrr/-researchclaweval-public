from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from real_eval.scripts.validate_framework_run import validate

EXPECTED = {
    "01": ("real_eval/scripts/01_ai_researcher_arc_wbe_2026_smoke.sh", "AI-Researcher/benchmark/final/arc_wbe_2026/arc_wbe_2026.json"),
    "02": ("real_eval/scripts/02_ai_scientist_v2_arc_wbe_2026_smoke.sh", "AI-Scientist-v2/ai_scientist/ideas/arc_wbe_2026_topic.md"),
    "03": ("real_eval/scripts/03_aris_arc_wbe_2026_smoke.sh", "Auto-claude-code-research-in-sleep/ARC_WBE_2026_BRIEF.md"),
    "04": ("real_eval/scripts/04_autoresearchclaw_arc_wbe_2026_smoke.sh", "AutoResearchClaw/config.arc.yaml"),
    "05": ("real_eval/scripts/05_deepscientist_arc_wbe_2026_smoke.sh", "DeepScientist/DEEPSCIENTIST_BRIEF.md"),
    "06": ("real_eval/scripts/06_drclaw_arc_wbe_2026_smoke.sh", "dr-claw/research_brief.json"),
    "07": ("real_eval/scripts/07_evoscientist_arc_wbe_2026_smoke.sh", "EvoScientist/EVOSCIENTIST_BRIEF.md"),
}


def test_arc_smoke_requires_topic_contract_evidence(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    brief = run_root / "repo" / "ARC_WBE_2026_BRIEF.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("ARC-WBE-2026\n/data/arc_white_box_estimation_2026\n", encoding="utf-8")
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    (run_root / "logs" / "smoke.log").write_text("ok\n", encoding="utf-8")
    (run_root / "smoke_manifest.json").write_text(
        json.dumps(
            {
                "framework": "test",
                "dataset_root": "/data/arc_white_box_estimation_2026",
                "contract_file": "/repo/automation/arc_white_box_estimation_2026_contract.md",
                "topic_evidence": "repo/ARC_WBE_2026_BRIEF.md",
                "checks": {"topic_evidence_exists": True},
                "all_passed": True,
            }
        ),
        encoding="utf-8",
    )

    result = validate("arc_wbe_2026_smoke", run_root)

    assert result.status == "finished"
    assert result.evidence["topic_evidence"] == "repo/ARC_WBE_2026_BRIEF.md"


def test_arc_smoke_fails_without_topic_contract_evidence(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    (run_root / "logs" / "smoke.log").write_text("ok\n", encoding="utf-8")
    (run_root / "smoke_manifest.json").write_text(
        json.dumps(
            {
                "framework": "test",
                "checks": {"topic_evidence_exists": False},
                "all_passed": True,
            }
        ),
        encoding="utf-8",
    )

    result = validate("arc_wbe_2026_smoke", run_root)

    assert result.status == "failed_validation"
    assert result.warnings == ["missing_topic_evidence"]


def test_arc_smoke_wrappers_exist_and_stay_topic_evidence_oriented() -> None:
    for wrapper_rel, evidence_rel in EXPECTED.values():
        wrapper = ROOT / wrapper_rel
        assert wrapper.exists(), f"missing wrapper: {wrapper_rel}"
        text = wrapper.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "generate_arc_wbe_2026_native_inputs.py" in text
        assert evidence_rel in text
        assert "smoke_manifest.json" in text
        assert "smoke.log" in text
        assert "docker run" not in lowered
        assert "systemd-run" not in lowered
        assert "gave2" not in lowered
        assert "babylm" not in lowered

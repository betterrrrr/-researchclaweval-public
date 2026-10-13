from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "real_eval/scripts/validate_framework_run.py"
WRAPPERS = {
    "01": ROOT / "real_eval/scripts/01_ai_researcher_arc_wbe_2026_fullrun.sh",
    "02": ROOT / "real_eval/scripts/02_ai_scientist_v2_arc_wbe_2026_fullrun.sh",
    "03": ROOT / "real_eval/scripts/03_aris_arc_wbe_2026_fullrun.sh",
    "04": ROOT / "real_eval/scripts/04_autoresearchclaw_arc_wbe_2026_fullrun.sh",
    "05": ROOT / "real_eval/scripts/05_deepscientist_arc_wbe_2026_fullrun.sh",
    "06": ROOT / "real_eval/scripts/06_drclaw_arc_wbe_2026_fullrun.sh",
    "07": ROOT / "real_eval/scripts/07_evoscientist_arc_wbe_2026_fullrun.sh",
}
SHARED_RUNNER = ROOT / "real_eval/scripts/arc_framework_fullrun.sh"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_framework_run", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load validator module from {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def valid_arc_trace() -> dict:
    return {
        "framework_native_execution": True,
        "consumed_topic_input": True,
        "workspace_trace_root": "/workspace",
        "framework_internal_model": "gpt-5.4",
        "framework_internal_api_base_url": "https://dts.deepexi.com/v1",
        "experiments": [
            {"experiment_id": "exp-1"},
            {"experiment_id": "exp-2"},
        ],
        "selected_experiment_id": "exp-2",
        "idea_artifact": "research_idea.json",
        "idea_locked_before_experiments": True,
    }


def test_arc_trace_integrity_requires_selected_experiment_and_expanded_provider() -> None:
    module = load_validator_module()
    trace = valid_arc_trace()
    trace["selected_experiment_id"] = "missing"
    trace["framework_internal_model"] = "${OPENAI_MODEL}"
    trace["framework_internal_api_base_url"] = "${OPENAI_BASE_URL}"

    ok, failures, evidence = module.arc_trace_integrity(
        trace,
        {
            "evaluation_model": "gpt-5.4",
            "provider_base_url": "https://dts.deepexi.com/v1",
        },
    )

    assert ok is False
    assert "selected_experiment_not_in_trace" in failures
    assert "unexpanded_framework_internal_model" in failures
    assert "unexpanded_framework_internal_api_base_url" in failures
    assert evidence["experiment_count"] == 2


def test_arc_trace_integrity_accepts_complete_native_trace() -> None:
    module = load_validator_module()

    ok, failures, evidence = module.arc_trace_integrity(
        valid_arc_trace(),
        {
            "evaluation_model": "gpt-5.4",
            "provider_base_url": "https://dts.deepexi.com/v1/",
        },
    )

    assert ok is True
    assert failures == []
    assert evidence["selected_experiment_id"] == "exp-2"


def test_arc_topic_wrappers_route_framework_models_through_real_eval_env() -> None:
    ai_researcher = WRAPPERS["01"].read_text(encoding="utf-8")
    ai_scientist = WRAPPERS["02"].read_text(encoding="utf-8")
    evoscientist = WRAPPERS["07"].read_text(encoding="utf-8")

    assert "AI_RESEARCHER_COMPLETION_MODEL" in ai_researcher
    assert "AI_RESEARCHER_CHEAP_MODEL" in ai_researcher
    assert "--model $AI_RESEARCHER_COMPLETION_MODEL" in ai_researcher
    assert "-e COMPLETION_MODEL=$AI_RESEARCHER_COMPLETION_MODEL" in ai_researcher
    assert "-e CHEEP_MODEL=$AI_RESEARCHER_CHEAP_MODEL" in ai_researcher

    assert (
        'AI_SCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"'
        in ai_scientist
    )
    assert "--model $AI_SCIENTIST_MODEL" in ai_scientist

    assert (
        'EVOSCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"'
        in evoscientist
    )
    assert "model: ${EVOSCIENTIST_MODEL}" in evoscientist


@pytest.mark.parametrize(
    "score_source",
    [
        "local_official_eval",
        "local_official_eval_adjusted_final_layer_score",
        "local_official_eval_reconstructed_from_per_mlp",
        "local_official_eval_stdout",
    ],
)
def test_arc_fullrun_keeps_legacy_local_official_eval_out_of_official_finished(
    tmp_path: Path,
    score_source: str,
) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (run_root / "workspace").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "AI-Researcher"})
    write_json(run_root / "state.json", {"status": "finished_degraded"})
    (run_root / "logs/e2e.log").write_text(
        "python run_infer_idea.py --category arc_wbe_2026\n", encoding="utf-8"
    )
    (run_root / "workspace/final_report.md").write_text("# report\n", encoding="utf-8")
    write_json(
        run_root / "workspace/score.json",
        {"score": 0.42, "score_source": score_source, "score_artifact": "workspace/score.json"},
    )
    write_json(
        run_root / "workspace/submission.json",
        {
            "framework_native_execution": True,
            "consumed_topic_input": True,
            "workspace_trace_root": "workspace",
        },
    )

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "finished_degraded"
    assert result.evidence["official_comparable"] is False
    assert result.evidence["score_artifact"] == "workspace/score.json"
    assert result.evidence["submission_artifact"] == "workspace/submission.json"


def test_arc_fullrun_marks_finished_only_for_official_adapter_score(tmp_path: Path) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (run_root / "workspace").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "ARIS"})
    write_json(run_root / "state.json", {"status": "finished"})
    (run_root / "logs/e2e.log").write_text("finished\n", encoding="utf-8")
    (run_root / "workspace/final_report.md").write_text("# ARC report\n", encoding="utf-8")
    write_json(
        run_root / "workspace/score.json",
        {
            "score": 0.42,
            "score_source": "official_adapter_whest_run",
            "score_artifact": "workspace/score.json",
        },
    )
    write_json(run_root / "workspace/submission.json", {"submission_id": "demo"})

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "finished"
    assert result.evidence["official_comparable"] is True


def test_arc_fullrun_keeps_diagnostic_local_score_out_of_official_finished(tmp_path: Path) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (run_root / "workspace").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "DeepScientist"})
    write_json(run_root / "state.json", {"status": "finished_degraded"})
    (run_root / "logs/e2e.log").write_text("codex exec arc_wbe_2026\n", encoding="utf-8")
    (run_root / "workspace/final_report.md").write_text("# ARC report\n", encoding="utf-8")
    write_json(
        run_root / "workspace/score.json",
        {"score": 9.9, "score_source": "local_parquet_eval_final_layer_mse_multiplier_assumed_1.0"},
    )
    write_json(
        run_root / "workspace/submission.json",
        {
            "framework_native_execution": True,
            "consumed_topic_input": True,
            "workspace_trace_root": "workspace",
        },
    )

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "finished_degraded"
    assert result.evidence["official_comparable"] is False


def test_arc_fullrun_is_blocked_when_only_submission_exists(tmp_path: Path) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (run_root / "workspace").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "AI-Scientist-v2"})
    write_json(
        run_root / "state.json",
        {"status": "blocked", "summary": "real framework execution not integrated"},
    )
    (run_root / "logs/e2e.log").write_text("blocked\n", encoding="utf-8")
    (run_root / "workspace/final_report.md").write_text("# report\n", encoding="utf-8")
    write_json(run_root / "workspace/submission.json", {"submission_id": "demo"})

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "failed_validation"
    assert result.evidence["score_artifact"] is None
    assert result.evidence["submission_artifact"] == "workspace/submission.json"


def test_arc_fullrun_marks_finished_degraded_when_native_execution_evidence_exists(
    tmp_path: Path,
) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (run_root / "workspace").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "AI-Researcher"})
    write_json(
        run_root / "state.json",
        {"status": "finished_degraded", "summary": "native execution completed without score"},
    )
    (run_root / "logs/e2e.log").write_text(
        "python run_infer_idea.py --category arc_wbe_2026\n", encoding="utf-8"
    )
    (run_root / "workspace/final_report.md").write_text("# report\n", encoding="utf-8")
    write_json(
        run_root / "workspace/submission.json",
        {
            "framework_native_execution": True,
            "consumed_topic_input": True,
            "workspace_trace_root": "workspace",
        },
    )

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "finished_degraded"
    assert result.evidence["submission_artifact"] == "workspace/submission.json"
    assert result.evidence["score_artifact"] is None


def test_arc_fullrun_marks_finished_degraded_for_non_ai_researcher_native_logs(
    tmp_path: Path,
) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (run_root / "workspace").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "ARIS"})
    write_json(
        run_root / "state.json",
        {"status": "finished_degraded", "summary": "native execution completed without score"},
    )
    (run_root / "logs/e2e.log").write_text(
        'codex exec --yolo -C /workspace "execute arc_wbe_2026 workflow"\n',
        encoding="utf-8",
    )
    (run_root / "workspace/final_report.md").write_text("# report\n", encoding="utf-8")
    write_json(
        run_root / "workspace/submission.json",
        {
            "framework_native_execution": True,
            "consumed_topic_input": True,
            "workspace_trace_root": "workspace",
        },
    )

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "finished_degraded"


def test_arc_fullrun_ignores_nested_non_arc_submission_and_report_artifacts(tmp_path: Path) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (
        run_root / "workspace/AI-Researcher/paper_agent/babylm_contract/target_sections/babylm-10m"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )
    (run_root / "workspace/AI-Researcher/tuned-lens/.github/ISSUE_TEMPLATE").mkdir(
        parents=True, exist_ok=True
    )
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "AI-Researcher"})
    write_json(
        run_root / "state.json",
        {"status": "running", "summary": "Launching AI-Researcher ARC native execution"},
    )
    (run_root / "logs/e2e.log").write_text(
        "python run_infer_idea.py --category arc_wbe_2026\n", encoding="utf-8"
    )
    write_json(
        run_root
        / "workspace/AI-Researcher/paper_agent/babylm_contract/target_sections/babylm-10m/collated_submission.json",
        {"topic_label": "BabyLM-10M"},
    )
    (
        run_root / "workspace/AI-Researcher/tuned-lens/.github/ISSUE_TEMPLATE/bug_report.md"
    ).write_text("# not an ARC final report\n", encoding="utf-8")

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "failed_validation"
    assert result.evidence["final_report"] is None
    assert result.evidence["submission_artifact"] is None
    assert result.warnings == ["missing_submission_or_score"]


def test_arc_snapshot_purges_stale_physical_workspace_topic_state(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "ai_scientist/ideas").mkdir(parents=True)
    (src / ".aris-codex-project").mkdir(parents=True)
    (src / "keep").mkdir(parents=True)
    (src / "ai_scientist/ideas/arc_wbe_2026_topic.md").write_text("ARC topic\n", encoding="utf-8")
    (src / "ai_scientist/ideas/my_research_topic.md").write_text(
        "old generic topic\n", encoding="utf-8"
    )
    (src / "RESEARCH_BRIEF.md").write_text("GAVE2 brief\n", encoding="utf-8")
    (src / "benchmark/process/dataset_candidate/psydefdetect").mkdir(parents=True)
    (src / "benchmark/process/dataset_candidate/psydefdetect/reference.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (src / "tdc_admet_tox_old").mkdir()
    (src / "tdc_admet_tox_old/predictions.csv").write_text("row\n", encoding="utf-8")
    (src / "config.project4.yaml").write_text("path: /legacy/path/old\n", encoding="utf-8")
    (src / ".env.project01").write_text("SECRET=old\n", encoding="utf-8")
    (src / "provider.env").write_text("OPENAI_API_KEY=old\n", encoding="utf-8")
    (src / ".aris-codex-project/state.json").write_text('{"topic":"BabyLM"}\n', encoding="utf-8")
    (src / "keep/ARC_WBE_2026_BRIEF.md").write_text("ARC-WBE-2026 brief\n", encoding="utf-8")

    cmd = f"""
set -euo pipefail
source {ROOT}/real_eval/scripts/lib_real_eval.sh
real_eval_rsync_repo {src} {dst}
real_eval_purge_cross_topic_residue {dst} arc_wbe_2026
"""
    subprocess.run(["bash", "-lc", cmd], check=True)

    assert (dst / "ai_scientist/ideas/arc_wbe_2026_topic.md").exists()
    assert (dst / "keep/ARC_WBE_2026_BRIEF.md").exists()
    assert not (dst / "ai_scientist/ideas/my_research_topic.md").exists()
    assert not (dst / "RESEARCH_BRIEF.md").exists()
    assert not (dst / "benchmark/process/dataset_candidate/psydefdetect").exists()
    assert not (dst / "tdc_admet_tox_old").exists()
    assert not (dst / "config.project4.yaml").exists()
    assert not (dst / ".env.project01").exists()
    assert not (dst / "provider.env").exists()
    assert not (dst / ".aris-codex-project").exists()


def test_arc_snapshot_cross_topic_guard_rejects_unpurged_residue(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "benchmark/process/dataset_candidate/psydefdetect").mkdir(parents=True)

    result = subprocess.run(
        [
            "bash",
            "-lc",
            f"source {ROOT}/real_eval/scripts/lib_real_eval.sh; "
            f"real_eval_assert_no_cross_topic_residue {workspace} arc_wbe_2026",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "cross-topic residue remains after purge" in result.stderr


def test_arc_fullrun_rejects_cross_topic_final_report(tmp_path: Path) -> None:
    module = load_validator_module()
    run_root = tmp_path / "run"
    (run_root / "workspace").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    write_json(run_root / "fullrun_manifest.json", {"framework": "EvoScientist"})
    write_json(
        run_root / "state.json",
        {"status": "finished_degraded", "summary": "native execution completed without score"},
    )
    (run_root / "logs/e2e.log").write_text("evoscientist arc_wbe_2026\n", encoding="utf-8")
    (run_root / "workspace/final_report.md").write_text("# BabyLM Proxy Report\n", encoding="utf-8")
    write_json(
        run_root / "workspace/submission.json",
        {
            "framework_native_execution": True,
            "consumed_topic_input": True,
            "workspace_trace_root": "workspace",
        },
    )

    result = module.validate("arc_wbe_2026_fullrun", run_root)

    assert result.status == "failed_validation"
    assert result.warnings == ["cross_topic_report_pollution"]


def test_arc_fullrun_wrappers_emit_consistent_run_artifacts_without_fake_score_claims() -> None:
    required_markers = [
        "fullrun_manifest.json",
        "state.json",
        "logs/e2e.log",
        "submission_artifact",
        "final_report.md",
        "generate_arc_wbe_2026_native_inputs.py",
    ]
    forbidden_markers = [
        '"score_source": "official_eval"',
        '"score_source": "official"',
    ]

    for wrapper in WRAPPERS.values():
        text = wrapper.read_text(encoding="utf-8")
        combined = text + "\n" + SHARED_RUNNER.read_text(encoding="utf-8")
        for marker in required_markers:
            assert marker in combined, (
                f"{wrapper.name} is missing required fullrun marker: {marker}"
            )
        for marker in forbidden_markers:
            assert marker not in combined, (
                f"{wrapper.name} should not hard-code fake official score claims"
            )


def test_arc_non_ai_researcher_fullrun_wrappers_use_shared_real_runtime_runner() -> None:
    for framework_id in ("02", "03", "04", "05", "06", "07"):
        wrapper = WRAPPERS[framework_id]
        text = wrapper.read_text(encoding="utf-8")
        assert 'exec "$ROOT"/real_eval/scripts/arc_framework_fullrun.sh' in text
        assert 'FRAMEWORK_RUNTIME_KIND="docker"' in text
        assert "FRAMEWORK_RUNTIME_COMMAND=" in text
        assert "lightweight_arc_wbe_2026_fullrun_wrapper" not in text
        assert "real framework-specific ARC execution path is integrated yet" not in text


def test_ai_scientist_v2_arc_fullrun_wrapper_uses_recorded_degraded_ideation_path() -> None:
    text = WRAPPERS["02"].read_text(encoding="utf-8")

    assert "ai_scientist/perform_ideation_temp_free.py" in text
    assert "arc_wbe_2026_topic.json" in text
    assert "AI_SCIENTIST_V2_ARC_IDEATION_TIMEOUT_SECONDS" in text


def test_ai_researcher_arc_wrapper_matches_the_current_dataset_and_docker_templates() -> None:
    text = WRAPPERS["01"].read_text(encoding="utf-8")

    assert 'source_path = f"../benchmark/process/dataset_candidate/{category}"' in text
    assert 'gpu_cmd = ["--gpus", GPUS] if GPUS else []' in text


def test_ai_researcher_arc_fullrun_wrapper_uses_framework_native_execution() -> None:
    wrapper = WRAPPERS["01"]
    text = wrapper.read_text(encoding="utf-8")

    for marker in [
        "run_infer_idea.py",
        "arc_wbe_2026",
        "framework_native_execution",
        "benchmark/process/dataset_candidate/arc_wbe_2026/metaprompt.py",
        "RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT",
    ]:
        assert marker in text, (
            f"{wrapper.name} should contain native AI-Researcher ARC execution marker: {marker}"
        )

    assert 'real_eval_purge_cross_topic_residue "$REPO" "arc_wbe_2026"' in text


def test_ai_researcher_arc_fullrun_wrapper_accepts_nested_workplace_trace_root() -> None:
    text = WRAPPERS["01"].read_text(encoding="utf-8")

    assert "workplace/workplace" in text
    assert 'find "$REPO/research_agent"' in text


def test_shared_arc_runner_falls_back_to_generated_inputs_for_repo_prefixed_paths() -> None:
    text = SHARED_RUNNER.read_text(encoding="utf-8")

    assert 'input_override="$INPUT_ROOT/$rel"' in text
    assert 'if [[ -f "$input_override" ]]; then' in text


def test_shared_arc_runner_extracts_provider_base_url_from_toml_quotes() -> None:
    text = SHARED_RUNNER.read_text(encoding="utf-8")

    assert 'base_url[[:space:]]*=[[:space:]]*"' in text


def test_shared_arc_runner_purges_cross_topic_residue_for_arc() -> None:
    text = SHARED_RUNNER.read_text(encoding="utf-8")

    assert 'real_eval_purge_cross_topic_residue "$WORKSPACE" "arc_wbe_2026"' in text


def test_evoscientist_arc_wrapper_cleans_nested_workspace_residue() -> None:
    text = WRAPPERS["07"].read_text(encoding="utf-8")

    assert "rm -rf /workspace/workspace /workspace/verify_workspace /workspace/babylm_proxy" in text


def test_arc_kimi_fullrun_requires_framework_native_handoff_and_does_not_synthesize_it() -> None:
    text = SHARED_RUNNER.read_text(encoding="utf-8")

    for artifact in [
        "estimator.py",
        "submission.json",
        "score.json",
        "experiment_trace.json",
        "final_report.md",
    ]:
        assert artifact in text
    assert '"framework_internal_model"' in text
    assert '"framework_internal_api_base_url"' in text
    assert 'score.get("score_source") != "official_adapter_whest_run"' in text
    assert "from arc_fullrun_postprocess import write_postprocess_outputs" not in text
    assert "automation/scripts/run_arc_wbe_2026_local_score.py" in text


def test_evoscientist_arc_wrapper_has_bounded_foreground_kimi_execution() -> None:
    text = WRAPPERS["07"].read_text(encoding="utf-8")

    assert "default_mode: run" in text
    assert "enable_async_subagents: false" in text
    assert "EVOSCIENTIST_ARC_TIMEOUT_SECONDS" in text
    assert "arc_wbe_2026_execution_budget.md" in text

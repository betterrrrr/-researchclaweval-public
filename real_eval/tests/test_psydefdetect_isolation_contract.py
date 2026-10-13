from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "real_eval/scripts/lib_real_eval.sh"
VALIDATOR = ROOT / "real_eval/scripts/validate_framework_run.py"
NATIVE_MANIFEST = {
    "framework_orchestration": True,
    "native_entrypoint": "framework native cli",
    "provider_injection": "injected GPT provider",
    "native_log_marker": "PSYDEFDETECT_NATIVE_TEST",
    "executor_kind": "framework_cli",
    "evaluation_model": "gpt-5.4",
    "provider_base_url": "https://provider.example/v1",
}
NATIVE_LOG = "PsyDefDetect fullrun\nnative_entrypoint=framework native cli\nPSYDEFDETECT_NATIVE_TEST\n"


def test_psydefdetect_snapshot_purges_cross_topic_and_stale_outputs(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "keep").mkdir(parents=True)
    (src / "ai_scientist/ideas").mkdir(parents=True)
    (src / "artifacts").mkdir(parents=True)
    (src / "outputs").mkdir(parents=True)
    (src / "automation").mkdir(parents=True)
    (src / ".runtime-home").mkdir(parents=True)
    (src / "keep/psydefdetect_topic.md").write_text("PsyDefDetect contract", encoding="utf-8")
    (src / "automation/psydefdetect_contract.md").write_text("PsyDefDetect", encoding="utf-8")
    (src / "ai_scientist/ideas/babylm_10m_strict_small_topic.md").write_text("old", encoding="utf-8")
    (src / "old_arc_wbe_2026_result.json").write_text("{}", encoding="utf-8")
    (src / "gave2_task2_summary.md").write_text("old", encoding="utf-8")
    (src / "final_report.md").write_text("stale report", encoding="utf-8")
    (src / "submission.csv").write_text("id,label\n", encoding="utf-8")
    (src / "predictions.jsonl").write_text("{}\n", encoding="utf-8")
    (src / ".runtime-home/config.toml").write_text("secret", encoding="utf-8")

    cmd = f"""
set -euo pipefail
source {LIB}
real_eval_rsync_repo {src} {dst}
real_eval_purge_cross_topic_residue {dst} psydefdetect
"""
    subprocess.run(["bash", "-lc", cmd], check=True)

    assert (dst / "keep/psydefdetect_topic.md").exists()
    assert (dst / "automation/psydefdetect_contract.md").exists()
    assert not (dst / "ai_scientist/ideas/babylm_10m_strict_small_topic.md").exists()
    assert not (dst / "old_arc_wbe_2026_result.json").exists()
    assert not (dst / "gave2_task2_summary.md").exists()
    assert not (dst / "final_report.md").exists()
    assert not (dst / "submission.csv").exists()
    assert not (dst / "predictions.jsonl").exists()
    assert not (dst / ".runtime-home").exists()


def test_psydefdetect_validators_accept_topic_artifacts(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    logs = run_root / "logs"
    workspace.mkdir(parents=True)
    logs.mkdir()
    (run_root / "smoke_manifest.json").write_text(
        json.dumps({"all_passed": True, "checks": {"topic": True}, "framework": "ARIS"}),
        encoding="utf-8",
    )
    (run_root / "fullrun_manifest.json").write_text(json.dumps(NATIVE_MANIFEST) + "\n", encoding="utf-8")
    (run_root / "state.json").write_text('{"status": "finished", "summary": "ok"}\n', encoding="utf-8")
    (logs / "smoke.log").write_text("PsyDefDetect smoke\n", encoding="utf-8")
    (logs / "e2e.log").write_text(NATIVE_LOG, encoding="utf-8")
    (workspace / "final_report.md").write_text("PsyDefDetect final report\n", encoding="utf-8")
    (workspace / "predictions.jsonl").write_text('{"id":"x","label":1}\n', encoding="utf-8")
    (workspace / "score.json").write_text('{"macro_f1_positive": 0.1}\n', encoding="utf-8")
    (workspace / "experiment_trace.json").write_text(
        json.dumps(
            {
                "framework_native_execution": True,
                "consumed_topic_input": True,
                "workspace_trace_root": "workspace",
                "selected_experiment_id": "exp-2",
                "experiments": [{"id": "exp-1"}, {"id": "exp-2"}],
                "framework_internal_model": "gpt-5.4",
                "framework_internal_api_base_url": "https://provider.example/v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    smoke = subprocess.run(
        ["python3", str(VALIDATOR), "--framework", "psydefdetect_smoke", "--run-root", str(run_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    fullrun = subprocess.run(
        ["python3", str(VALIDATOR), "--framework", "psydefdetect_fullrun", "--run-root", str(run_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(smoke.stdout)["status"] == "finished"
    fullrun_payload = json.loads(fullrun.stdout)
    assert fullrun_payload["status"] == "finished"
    assert fullrun_payload["evidence"]["prediction_artifact"] == "workspace/predictions.jsonl"


def test_psydefdetect_validator_accepts_framework_metric_score_files(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    logs = run_root / "logs"
    workspace.mkdir(parents=True)
    logs.mkdir()
    (run_root / "fullrun_manifest.json").write_text(json.dumps(NATIVE_MANIFEST) + "\n", encoding="utf-8")
    (run_root / "state.json").write_text('{"status": "finished", "summary": "ok"}\n', encoding="utf-8")
    (logs / "e2e.log").write_text(NATIVE_LOG, encoding="utf-8")
    (workspace / "final_report.md").write_text("PsyDefDetect final report\n", encoding="utf-8")
    (workspace / "predictions.jsonl").write_text('{"id":"x","label":1}\n', encoding="utf-8")
    (workspace / "experiment_trace.json").write_text(
        json.dumps(
            {
                "framework_native_execution": True,
                "consumed_topic_input": True,
                "workspace_trace_root": "workspace",
                "selected_experiment_id": "exp-2",
                "experiments": [{"id": "exp-1"}, {"id": "exp-2"}],
                "framework_internal_model": "gpt-5.4",
                "framework_internal_api_base_url": "https://provider.example/v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (workspace / "score_metrics.json").write_text(
        json.dumps(
            {
                "official_metric_implemented": "macro-F1 over labels 1-8, excluding label 0",
                "test_metrics": {
                    "macro_f1_positive_1_8": 0.1675,
                    "macro_f1_all_0_8": 0.2301,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    fullrun = subprocess.run(
        ["python3", str(VALIDATOR), "--framework", "psydefdetect_fullrun", "--run-root", str(run_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(fullrun.stdout)
    assert payload["status"] == "finished"
    assert payload["evidence"]["score_artifact"] == "workspace/score_metrics.json"
    assert payload["evidence"]["psydefdetect_score"] == 0.1675


def test_psydefdetect_validator_accepts_negated_cross_topic_scope_guard_and_nested_metrics(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    nested = workspace / "psydefdetect_native_20260710T041025Z"
    logs = run_root / "logs"
    nested.mkdir(parents=True)
    logs.mkdir()
    (run_root / "fullrun_manifest.json").write_text(json.dumps(NATIVE_MANIFEST) + "\n", encoding="utf-8")
    (run_root / "state.json").write_text('{"status": "finished", "summary": "ok"}\n', encoding="utf-8")
    (logs / "e2e.log").write_text(NATIVE_LOG, encoding="utf-8")
    (workspace / "final_report.md").write_text(
        "# PsyDefDetect Final Report\n\n"
        "- Scope guard: no ARC-WBE, GAVE2, BabyLM, or prior-output workspace was used.\n",
        encoding="utf-8",
    )
    (workspace / "submission.csv").write_text("id,label\nx,1\n", encoding="utf-8")
    (workspace / "experiment_trace.json").write_text(
        json.dumps(
            {
                "framework_native_execution": True,
                "consumed_topic_input": True,
                "workspace_trace_root": "workspace/psydefdetect_native_20260710T041025Z",
                "selected_experiment_id": "exp-2",
                "experiments": [{"id": "exp-1"}, {"id": "exp-2"}],
                "framework_internal_model": "gpt-5.4",
                "framework_internal_api_base_url": "https://provider.example/v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (nested / "metrics.json").write_text(
        json.dumps({"eval_metrics": {"macro_f1_positive_1_8": 0.175873}}) + "\n",
        encoding="utf-8",
    )

    fullrun = subprocess.run(
        ["python3", str(VALIDATOR), "--framework", "psydefdetect_fullrun", "--run-root", str(run_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(fullrun.stdout)
    assert payload["status"] == "finished"
    assert payload["evidence"]["score_artifact"] == "workspace/psydefdetect_native_20260710T041025Z/metrics.json"
    assert payload["evidence"]["psydefdetect_score"] == 0.175873


def test_psydefdetect_validator_rejects_prediction_and_report_without_trace_and_score(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    logs = run_root / "logs"
    workspace.mkdir(parents=True)
    logs.mkdir()
    (run_root / "fullrun_manifest.json").write_text("{}\n", encoding="utf-8")
    (run_root / "state.json").write_text('{"status": "finished", "summary": "ok"}\n', encoding="utf-8")
    (logs / "e2e.log").write_text("PsyDefDetect fullrun\n", encoding="utf-8")
    (workspace / "final_report.md").write_text("PsyDefDetect final report\n", encoding="utf-8")
    (workspace / "predictions.jsonl").write_text('{"id":"x","label":1}\n', encoding="utf-8")

    fullrun = subprocess.run(
        ["python3", str(VALIDATOR), "--framework", "psydefdetect_fullrun", "--run-root", str(run_root)],
        capture_output=True,
        text=True,
    )

    assert fullrun.returncode != 0
    payload = json.loads(fullrun.stdout)
    assert payload["status"] == "failed_validation"
    assert "score, or experiment-trace evidence is incomplete" in payload["summary"]


def test_template_artifact_snapshot_detects_new_forbidden_outputs(tmp_path: Path) -> None:
    src = tmp_path / "framework"
    before = tmp_path / "before.txt"
    src.mkdir()
    (src / "README.md").write_text("clean", encoding="utf-8")

    clean_cmd = f"""
set -euo pipefail
source {LIB}
real_eval_snapshot_forbidden_artifacts {src} {before}
real_eval_assert_no_new_forbidden_artifacts {src} {before}
"""
    subprocess.run(["bash", "-lc", clean_cmd], check=True)

    (src / "final_report.md").write_text("pollution", encoding="utf-8")
    dirty_cmd = f"""
set -euo pipefail
source {LIB}
real_eval_assert_no_new_forbidden_artifacts {src} {before}
"""
    proc = subprocess.run(["bash", "-lc", dirty_cmd], capture_output=True, text=True)
    assert proc.returncode == 14
    assert "Framework template source gained forbidden artifacts" in proc.stderr

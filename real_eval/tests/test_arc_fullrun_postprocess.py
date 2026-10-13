from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "real_eval" / "scripts" / "arc_fullrun_postprocess.py"


def load_module():
    spec = importlib.util.spec_from_file_location("arc_fullrun_postprocess", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_postprocess_keeps_run_alive_when_workspace_report_is_not_rewritable(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    report_path = workspace / "final_report.md"
    report_path.write_text("old report\n", encoding="utf-8")
    report_path.chmod(0o444)

    original_unlink = module.Path.unlink

    def fake_unlink(self: Path, *args, **kwargs):
        if self == report_path:
            raise PermissionError("simulated unlink failure")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(module.Path, "unlink", fake_unlink)

    written = module.write_report_with_fallback(
        workspace=workspace,
        artifacts_dir=artifacts_dir,
        content="# rewritten\n",
    )

    assert written == artifacts_dir / "final_report.md"
    assert written.read_text(encoding="utf-8") == "# rewritten\n"
    assert report_path.read_text(encoding="utf-8") == "old report\n"


def test_postprocess_marks_only_official_arc_scores_as_finished(tmp_path: Path) -> None:
    module = load_module()
    score_path = tmp_path / "score.json"
    score_path.write_text(
        json.dumps(
            {
                "score": 0.123,
                "score_source": "local_official_eval_adjusted_final_layer_score",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    state = module.build_state_payload(run_rc=0, score_payload=json.loads(score_path.read_text(encoding="utf-8")))
    assert state["status"] == "finished_degraded"
    assert "without local official scoring" in state["summary"]

    official = module.build_state_payload(
        run_rc=0,
        score_payload={
            "score": 0.123,
            "score_source": "official_adapter_whest_run",
        },
    )
    assert official["status"] == "finished"
    assert "official score evidence" in official["summary"]


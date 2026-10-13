from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]


def test_arc_registry_dry_run_generates_seven_rows_per_mode(tmp_path: Path) -> None:
    script = ROOT / "real_eval/scripts/run_registry_serial_dry_run.py"

    for mode in ("input_pack", "smoke", "fullrun"):
        run_root = tmp_path / mode
        result = subprocess.run(
            [
                "python3",
                str(script),
                "--topic",
                "arc_wbe_2026",
                "--mode",
                mode,
                "--run-root",
                str(run_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads((run_root / "serial_status.json").read_text(encoding="utf-8"))
        assert payload["topic"] == "arc_wbe_2026"
        assert payload["mode"] == mode
        assert len(payload["rows"]) == 7
        assert {row["status"] for row in payload["rows"]} == {"dry_run"}


def test_arc_preflight_points_to_dataset_preparation_script_when_dataset_is_missing(tmp_path: Path) -> None:
    script = ROOT / "real_eval/scripts/preflight_seven_serial_arc_wbe_2026.sh"
    missing_dataset = tmp_path / "missing-dataset"

    result = subprocess.run(
        [
            "bash",
            str(script),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RESEARCHCLAWEVAL_ROOT": str(ROOT),
            "ARC_WBE_2026_DATASET_ROOT": str(missing_dataset),
        },
    )

    assert result.returncode == 3
    assert "prepare_arc_wbe_2026_dataset.py" in result.stderr

from __future__ import annotations

import json
from pathlib import Path

from researchclaweval.cli import main


def test_registry_list_is_dynamic(capsys) -> None:
    assert main(["registry", "list", "--kind", "topics", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    topic_ids = [row["id"] for row in payload["topics"]]
    assert "babylm" in topic_ids
    assert "arc_wbe_2026" in topic_ids
    assert "psydefdetect" in topic_ids
    assert "tdc_admet_tox" in topic_ids


def test_matrix_renders_current_topic_not_a_hardcoded_subset(capsys) -> None:
    assert (
        main(
            [
                "registry",
                "matrix",
                "--topic",
                "psydefdetect",
                "--mode",
                "fullrun",
                "--format",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["rows"]) >= 5
    assert {row["topic_id"] for row in payload["rows"]} == {"psydefdetect"}


def test_registry_export_rejects_an_unmapped_mode(capsys) -> None:
    assert main(["registry", "export", "--topic", "babylm", "--mode", "smoke"]) == 2
    assert "does not support mode" in capsys.readouterr().err


def test_dry_run_writes_plan_without_launching_framework(tmp_path: Path, capsys) -> None:
    output = tmp_path / "plan"
    assert (
        main(
            [
                "dry-run",
                "--topic",
                "arc_wbe_2026",
                "--mode",
                "smoke",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "dry_run"
    assert payload["framework_count"] >= 5
    assert (output / "dry_run.json").is_file()
    assert (output / "dry_run.md").is_file()


def test_validate_run_rejects_non_native_mapping(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "validate",
                "run",
                "--topic",
                "gave2_task2",
                "--framework",
                "03",
                "--mode",
                "fullrun",
                "--run-dir",
                str(tmp_path),
            ]
        )
        != 0
    )
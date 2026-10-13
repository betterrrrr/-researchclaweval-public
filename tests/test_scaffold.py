from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from researchclaweval.cli import main
from researchclaweval.scaffold import TOPICS, slugify
from researchclaweval.validation import _schema_errors

ROOT = Path(__file__).resolve().parents[1]


def _init(out_dir: Path, *extra: str) -> int:
    return main(
        [
            "adapter",
            "init",
            "--id",
            "08",
            "--name",
            "MyFramework",
            "--topics",
            "babylm,psydefdetect",
            "--upstream-url",
            "https://github.com/me/MyFramework.git",
            "--license",
            "Apache-2.0",
            "--image",
            "myframework:runtime-ready",
            "--entrypoint",
            "myframework run --chat",
            "--out-dir",
            str(out_dir),
            *extra,
        ]
    )


def test_slugify_normalises_names() -> None:
    assert slugify("My Framework") == "my_framework"
    assert slugify("Dr. Claw") == "dr_claw"
    with pytest.raises(ValueError):
        slugify("!!!")


def test_init_writes_one_wrapper_per_topic_plus_manifest(tmp_path: Path, capsys) -> None:
    assert _init(tmp_path) == 0
    capsys.readouterr()

    manifest = tmp_path / "adapters" / "08-myframework" / "manifest.json"
    assert manifest.is_file()
    for topic in ("babylm", "psydefdetect"):
        assert (tmp_path / "real_eval" / "scripts" / f"08_myframework_{topic}_fullrun.sh").is_file()


def test_generated_manifest_satisfies_adapter_schema(tmp_path: Path, capsys) -> None:
    assert _init(tmp_path) == 0
    capsys.readouterr()

    payload = json.loads((tmp_path / "adapters" / "08-myframework" / "manifest.json").read_text())
    schema = json.loads((ROOT / "schemas" / "adapter.schema.json").read_text())
    assert _schema_errors(payload, schema) == []
    assert payload["supported_topics"] == ["babylm", "psydefdetect"]


def test_generated_wrappers_are_valid_bash(tmp_path: Path, capsys) -> None:
    assert _init(tmp_path) == 0
    capsys.readouterr()

    for topic in ("babylm", "psydefdetect"):
        wrapper = tmp_path / "real_eval" / "scripts" / f"08_myframework_{topic}_fullrun.sh"
        subprocess.run(["bash", "-n", str(wrapper)], check=True)


def test_generated_wrappers_declare_the_required_interface(tmp_path: Path, capsys) -> None:
    """Every variable a runner reads with ${VAR:?} must be present."""
    assert _init(tmp_path) == 0
    capsys.readouterr()

    for topic in ("babylm", "psydefdetect"):
        text = (
            tmp_path / "real_eval" / "scripts" / f"08_myframework_{topic}_fullrun.sh"
        ).read_text()
        for var in (
            "FRAMEWORK_RUNTIME_KIND",
            "FRAMEWORK_ENTRY_PATHS",
            "FRAMEWORK_PROVIDER_INJECTION",
            "FRAMEWORK_NATIVE_LOG_MARKER",
        ):
            assert f"export {var}=" in text, (topic, var)
        # The marker must be unique per topic so it cannot be replayed.
        assert f'FRAMEWORK_NATIVE_LOG_MARKER="MYFRAMEWORK_{topic.upper()}_NATIVE"' in text
        # The wrapper must hand off to the shared runner for its topic.
        assert TOPICS[topic]["runner"] in text


def test_init_refuses_to_overwrite_without_force(tmp_path: Path, capsys) -> None:
    assert _init(tmp_path) == 0
    capsys.readouterr()
    assert _init(tmp_path) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    assert _init(tmp_path, "--force") == 0
    capsys.readouterr()


@pytest.mark.parametrize(
    ("framework_id", "topics", "expected"),
    [
        ("8", "babylm", "two digits"),
        ("08", "nosuchtopic", "unknown topic"),
        ("08", "", "at least one topic"),
    ],
)
def test_init_rejects_bad_arguments(
    tmp_path: Path, capsys, framework_id: str, topics: str, expected: str
) -> None:
    assert (
        main(
            [
                "adapter", "init", "--id", framework_id, "--name", "MyFramework",
                "--topics", topics, "--out-dir", str(tmp_path),
            ]
        )
        == 2
    )
    assert expected in capsys.readouterr().err

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BABYLM_RUNNER = ROOT / "real_eval/scripts/babylm_framework_fullrun.sh"
DEEPSCIENTIST_BABYLM_RUNNER = ROOT / "real_eval/scripts/05_deepscientist_babylm_gpt_fullrun.sh"
ARC_RUNNER = ROOT / "real_eval/scripts/arc_framework_fullrun.sh"
PSYDEFDETECT_RUNNER = ROOT / "real_eval/scripts/psydefdetect_framework_fullrun.sh"
REDACTOR = ROOT / "real_eval/scripts/redact_env_secrets.py"


def test_babylm_keeps_provider_config_out_of_writable_workspace() -> None:
    text = BABYLM_RUNNER.read_text(encoding="utf-8")

    assert 'chmod 700 "$CODEX_HOME_DIR"' in text
    assert 'chmod 600 "$CODEX_HOME_DIR/config.toml"' in text
    assert ".provider_config.toml" not in text

    deepscientist_text = DEEPSCIENTIST_BABYLM_RUNNER.read_text(encoding="utf-8")
    assert "/workspace/.provider_config.toml" not in deepscientist_text
    assert 'DEEPSCIENTIST_SOURCE_CODEX_CONFIG="${CODEX_HOME:?CODEX_HOME is required}/config.toml"' in deepscientist_text


def test_arc_keeps_provider_config_out_of_writable_workspace() -> None:
    text = ARC_RUNNER.read_text(encoding="utf-8")

    assert 'chmod 700 "$CODEX_HOME_DIR"' in text
    assert 'chmod 600 "$CODEX_HOME_DIR/config.toml"' in text
    assert ".provider_config.toml" not in text


def test_psydefdetect_keeps_provider_config_out_of_writable_workspace() -> None:
    text = PSYDEFDETECT_RUNNER.read_text(encoding="utf-8")

    assert 'chmod 700 "$CODEX_HOME_DIR"' in text
    assert 'chmod 600 "$CODEX_HOME_DIR/config.toml"' in text
    assert ".provider_config.toml" not in text


def test_framework04_native_logs_are_redacted_before_persistence() -> None:
    for runner in (BABYLM_RUNNER, ARC_RUNNER, PSYDEFDETECT_RUNNER):
        text = runner.read_text(encoding="utf-8")

        assert "redact_env_secrets.py" in text
        assert '--env-file "$PROVIDER_ENV" --env-file "$SEMANTIC_ENV"' in text


def test_redactor_removes_provider_secret_from_native_output(tmp_path: Path) -> None:
    provider_env = tmp_path / "provider.env"
    protected_value = "test-only-provider-secret"
    provider_env.write_text(f"OPENAI_API_KEY={protected_value}\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(REDACTOR), "--env-file", str(provider_env)],
        input=f"native output {protected_value}\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert protected_value not in result.stdout
    assert result.stdout == "native output [REDACTED]\n"

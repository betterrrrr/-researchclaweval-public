from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "real_eval" / "scripts" / "tdc_admet_tox_framework_smoke.sh"
WRAPPER = ROOT / "real_eval" / "scripts" / "01_ai_researcher_tdc_admet_tox_smoke.sh"
CONFIG = ROOT / "real_eval" / "config" / "seven_tdc_admet_tox_gpt_smoke_frameworks.json"
VALIDATOR = ROOT / "real_eval" / "scripts" / "validate_framework_run.py"
LOCAL_PREFLIGHT = ROOT / "real_eval" / "scripts" / "preflight_ai_researcher_tdc_admet_tox_local.sh"
REDACTOR = ROOT / "real_eval" / "scripts" / "redact_env_secrets.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tdc_smoke_uses_blocking_codex_and_strict_mounts() -> None:
    text = read(HELPER)

    assert 'BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"' in text
    assert 'real_eval_require_clean_dir "$BASE"' in text
    assert 'real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"' in text
    assert 'real_eval_purge_cross_topic_residue "$WORKSPACE" tdc_admet_tox' in text
    assert "codex exec --yolo" in text
    assert "--ephemeral --skip-git-repo-check" in text
    assert "--cpus 4" in text
    assert "--memory 16g" in text
    assert 'docker network create --internal "$NETWORK_NAME"' in text
    assert '--network "$NETWORK_NAME"' in text
    assert 'CLIENT_RELAY_BASE_URL="http://tdc-gpt-relay:8787/v1"' in text
    assert '-v "$WORKSPACE":/workspace' in text
    assert '-v "$INPUT_ROOT":/input:ro' in text
    assert '-v "$DATASET_ROOT":/data/tdc_admet_tox:ro' in text
    assert '-v "$HOST_NODE_ROOT":$CONTAINER_NODE_ROOT:ro' in text
    assert '-e FRAMEWORK_NATIVE_ENTRYPOINT_FILE="$FRAMEWORK_NATIVE_ENTRYPOINT_FILE"' in text
    assert 'chmod 700 "$CODEX_HOME_DIR"' in text
    assert 'chmod 600 "$CODEX_HOME_DIR/config.toml"' in text
    assert "Never print environment variable values or credential values" in text
    assert "credentials_absent_from_log" in text
    assert "redact_env_secrets.py" in text
    assert "TDC_ADMET_TOX_HIDDEN_LABELS_ROOT" not in text
    assert '-v "$ROOT":' not in text
    assert "run_tdc_admet_tox_host_score.py" not in text
    assert "run_tdc_admet_tox_validation_score.py" in text
    assert "predictions.csv" in text
    assert "score.json" in text
    assert '"project_id": "tdc_admet_tox"' in text


def test_ai_researcher_tdc_smoke_wrapper_uses_official_entrypoint() -> None:
    text = read(WRAPPER)

    assert 'real_eval_resolve_framework_source "$ROOT" 01' in text
    assert 'FRAMEWORK_RUNTIME_IMAGE="ai-researcher:runtime-ready"' in text
    assert 'FRAMEWORK_NATIVE_ENTRYPOINT="research_agent/run_infer_idea.py"' in text
    assert "tdc_admet_tox_framework_smoke.sh" in text


def test_tdc_gpt_smoke_config_covers_seven_frameworks() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert payload["topic_id"] == "tdc_admet_tox"
    assert payload["evaluation_variant"] == "gpt"
    assert [row["id"] for row in payload["frameworks"]] == [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
    ]
    assert all(row["validator"] == "tdc_admet_tox_smoke" for row in payload["frameworks"])
    assert all("tdc_admet_tox" in row["wrapper"] for row in payload["frameworks"])


def test_local_preflight_is_no_network_and_cannot_claim_smoke() -> None:
    text = read(LOCAL_PREFLIGHT)

    assert "--network none" in text
    assert '"llm_invoked": False' in text
    assert '"phase": "local_preflight"' in text
    assert '"status": "preflight_passed" if passed else "preflight_failed"' in text
    assert "codex exec" not in text
    assert "provider.env" not in text
    assert "execution_kind=local_preflight_no_llm" in text
    assert "patch_ai_researcher.py" in text
    assert '"native_imports": all(callable(tool) for tool in required_tools)' in text
    for module in ("plan_agent", "ml_agent", "judge_agent", "run_infer_idea"):
        assert module in text
    assert 'echo "network=none"' in text
    assert "print(json.dumps(payload, ensure_ascii=True, sort_keys=True))" in text
    assert 'tee -a "$LOG_FILE"' in text


def test_tdc_smoke_validator_accepts_complete_host_evidence(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    (run_root / "logs").mkdir(parents=True)
    checks = {
        "codex_exit_zero": True,
        "native_entrypoint_present": True,
        "public_file_set_exact": True,
        "labeled_schema": True,
        "test_schema_unlabeled": True,
        "endpoint_sets_exact": True,
        "cross_topic_paths_absent": True,
        "credentials_absent_from_log": True,
        "agent_evidence": True,
        "no_final_outputs": True,
    }
    (run_root / "smoke_manifest.json").write_text(
        json.dumps(
            {
                "topic_id": "tdc_admet_tox",
                "framework": "AI-Researcher",
                "native_entrypoint": "research_agent/run_infer_idea.py",
                "checks": checks,
                "all_passed": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"status": "finished"}) + "\n", encoding="utf-8"
    )
    (run_root / "logs" / "smoke.log").write_text("codex smoke passed\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--framework",
            "tdc_admet_tox_smoke",
            "--run-root",
            str(run_root),
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["status"] == "finished"


def test_tdc_public_materialization_has_no_test_label_column() -> None:
    public_root = ROOT / "data" / "tdc_admet_tox" / "public"

    assert (public_root / "dataset_manifest.json").is_file()
    assert (public_root / "train.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "sample_id,endpoint,smiles,label"
    )
    assert (public_root / "validation.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "sample_id,endpoint,smiles,label"
    )
    assert (public_root / "test.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "sample_id,endpoint,smiles"
    )
    assert not list(public_root.glob("*label*"))


def test_secret_redactor_replaces_values_anywhere_in_stream(tmp_path: Path) -> None:
    env_file = tmp_path / "provider.env"
    env_file.write_text(
        "OPENAI_API_KEY=client-token-123456\nOPENAI_MODEL=gpt-5.4\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(REDACTOR), "--env-file", str(env_file)],
        input='OPENAI_API_KEY=client-token-123456 json={"key":"client-token-123456"}\n',
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert proc.stdout == 'OPENAI_API_KEY=[REDACTED] json={"key":"[REDACTED]"}\n'

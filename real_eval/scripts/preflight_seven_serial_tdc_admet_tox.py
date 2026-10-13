#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

try:
    import tomllib as toml_parser
except ModuleNotFoundError:
    import toml as toml_parser

FRAMEWORK_IDS = ["01", "02", "03", "04", "05", "06", "07"]
FORBIDDEN_TOPICS = ("babylm", "gave2", "arc_wbe_2026", "arc-wbe-2026", "psydefdetect")
ALLOWED_VARIANTS = ("gpt", "ds", "kimi", "gpt56luna")
EXPECTED_MODELS = {
    "gpt": "gpt-5.4",
    "ds": "deepseek-v4-flash",
    "kimi": "kimi-k2.6",
    "gpt56luna": "gpt-5.6-luna",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight the Topic 5 campaign (gpt or ds).")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "fullrun"), required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, required=True)
    parser.add_argument("--hidden-labels-root", type=Path)
    parser.add_argument("--smoke-gate-root", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    config_path = args.config.resolve()
    dataset_root = args.dataset_root.resolve()
    errors: list[str] = []
    checks: dict[str, object] = {}

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"cannot read framework config: {exc}")
    rows = config.get("frameworks") if isinstance(config, dict) else None
    checks["topic_id"] = config.get("topic_id") if isinstance(config, dict) else None
    checks["evaluation_variant"] = (
        config.get("evaluation_variant") if isinstance(config, dict) else None
    )
    if checks["topic_id"] != "tdc_admet_tox":
        errors.append("wrong_topic_id")
    variant = checks["evaluation_variant"]
    if variant not in ALLOWED_VARIANTS:
        errors.append("wrong_evaluation_variant")
    recovery_of = config.get("recovery_of") if isinstance(config, dict) else None
    checks["recovery_of"] = recovery_of
    row_ids = [row.get("id") for row in rows] if isinstance(rows, list) else []
    if recovery_of:
        valid_recovery_subset = (
            isinstance(recovery_of, str)
            and bool(recovery_of.strip())
            and bool(row_ids)
            and len(row_ids) == len(set(row_ids))
            and all(framework_id in FRAMEWORK_IDS for framework_id in row_ids)
            and row_ids == [framework_id for framework_id in FRAMEWORK_IDS if framework_id in row_ids]
        )
        checks["recovery_subset_valid"] = valid_recovery_subset
        if not valid_recovery_subset:
            errors.append("framework_recovery_subset_invalid")
            rows = []
    elif row_ids != FRAMEWORK_IDS:
        errors.append("framework_matrix_not_seven_ordered")
        rows = []

    missing_paths: list[str] = []
    missing_images: list[str] = []
    polluted_wrappers: list[str] = []
    generic_codex_owners: list[str] = []
    missing_native_process_evidence: list[str] = []
    for row in rows:
        wrapper = str(row.get("wrapper", ""))
        wrapper_path = root / wrapper
        if not wrapper_path.is_file():
            missing_paths.append(wrapper)
            continue
        lower_wrapper = wrapper.lower()
        text = wrapper_path.read_text(encoding="utf-8", errors="ignore")
        if "tdc_admet_tox" not in lower_wrapper or any(
            marker in lower_wrapper for marker in FORBIDDEN_TOPICS
        ):
            polluted_wrappers.append(wrapper)
        explicitly_not_dispatched = any(
            status in text
            for status in ("unsupported_native_entrypoint", "blocked_benchmark_authorization")
        )
        official_skill_host = all(
            marker in text
            for marker in (
                'FRAMEWORK_EXECUTOR_KIND="official_framework_skill"',
                "skills/skills-codex/",
                "install_aris_codex.sh",
                "research-pipeline",
            )
        )
        if (
            args.mode == "fullrun"
            and "codex exec" in text
            and not explicitly_not_dispatched
            and not official_skill_host
        ):
            generic_codex_owners.append(wrapper)
        if args.mode == "fullrun" and not explicitly_not_dispatched:
            required_evidence_markers = (
                "FRAMEWORK_NATIVE_PROCESS_MARKERS",
                "PS4='NATIVE_CMD> '",
                "set -x",
            )
            if any(marker not in text for marker in required_evidence_markers):
                missing_native_process_evidence.append(wrapper)
        for required_path in row.get("required_paths", []):
            if not (root / required_path).exists():
                missing_paths.append(required_path)
        for image in row.get("required_images", []):
            result = subprocess.run(
                ["docker", "image", "inspect", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                missing_images.append(image)
    relay_image = os.environ.get(
        "TDC_ADMET_TOX_GPT_RELAY_IMAGE", "researchclaweval/codex-kimi-relay:test"
    )
    relay_result = subprocess.run(
        ["docker", "image", "inspect", relay_image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if relay_result.returncode != 0:
        missing_images.append(relay_image)
    checks["missing_paths"] = sorted(set(missing_paths))
    checks["missing_images"] = sorted(set(missing_images))
    checks["polluted_wrappers"] = polluted_wrappers
    checks["generic_codex_fullrun_owners"] = generic_codex_owners
    checks["missing_native_process_evidence"] = missing_native_process_evidence
    if missing_paths:
        errors.append("missing_paths")
    if missing_images:
        errors.append("missing_images")
    if polluted_wrappers:
        errors.append("cross_topic_wrapper")
    if generic_codex_owners:
        errors.append("generic_codex_fullrun_owner")
    if missing_native_process_evidence:
        errors.append("native_process_evidence_missing")

    expected_public = {"train.csv", "validation.csv", "test.csv", "dataset_manifest.json"}
    actual_public = (
        {path.name for path in dataset_root.iterdir() if path.is_file()}
        if dataset_root.is_dir()
        else set()
    )
    checks["public_file_set_exact"] = actual_public == expected_public
    if actual_public != expected_public:
        errors.append("public_dataset_file_set")

    try:
        provider = toml_parser.loads(args.provider_config.read_text(encoding="utf-8"))
        provider_name = provider["model_provider"]
        provider_row = provider["model_providers"][provider_name]
        checks["provider_model"] = provider.get("model")
        checks["provider_wire_api"] = provider_row.get("wire_api")
        checks["provider_key_present"] = bool(provider_row.get("experimental_bearer_token"))
    except Exception:
        checks["provider_model"] = None
        checks["provider_wire_api"] = None
        checks["provider_key_present"] = False
    if (
        variant not in EXPECTED_MODELS
        or checks["provider_model"] != EXPECTED_MODELS[variant]
        or checks["provider_wire_api"] != "responses"
    ):
        errors.append("provider_model_mismatch_for_variant")
    if not checks["provider_key_present"]:
        errors.append("provider_key_missing")

    if args.mode == "fullrun":
        hidden_root = args.hidden_labels_root.resolve() if args.hidden_labels_root else None
        hidden_file = hidden_root / "test_labels.csv" if hidden_root else None
        checks["hidden_labels_host_only"] = bool(
            hidden_root
            and hidden_file
            and hidden_file.is_file()
            and hidden_root != dataset_root
            and dataset_root not in hidden_root.parents
            and hidden_root not in dataset_root.parents
        )
        if not checks["hidden_labels_host_only"]:
            errors.append("hidden_labels_not_separate_host_root")
        gate_root = args.smoke_gate_root.resolve() if args.smoke_gate_root else None
        gate_status = None
        if gate_root and (gate_root / "serial_status.json").is_file():
            try:
                gate_status = json.loads(
                    (gate_root / "serial_status.json").read_text(encoding="utf-8")
                )
            except Exception:
                gate_status = None
        gate_rows = gate_status.get("rows") if isinstance(gate_status, dict) else None
        checks["smoke_gate_variant_consistent"] = bool(
            gate_root
            and f"-{variant}-smoke-" in gate_root.name
        )
        if not checks["smoke_gate_variant_consistent"]:
            errors.append("smoke_gate_variant_mismatch")
        checks["smoke_gate_passed"] = bool(
            isinstance(gate_rows, list)
            and len(gate_rows) == 7
            and [row.get("id") for row in gate_rows] == FRAMEWORK_IDS
            and all(
                row.get("validator_rc") == 0 and row.get("status") == "finished"
                for row in gate_rows
            )
        )
        if not checks["smoke_gate_passed"]:
            errors.append("seven_framework_smoke_gate_missing")

    payload = {
        "task_id": "tdc_admet_tox",
        "evaluation_variant": variant,
        "mode": args.mode,
        "status": "passed" if not errors else "failed",
        "checks": checks,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if not errors else 13


if __name__ == "__main__":
    raise SystemExit(main())

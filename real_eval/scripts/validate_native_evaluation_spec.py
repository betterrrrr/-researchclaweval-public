#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])).expanduser()
STANDARD_PATH = ROOT / "real_eval/standards/native_evaluation_standard.v1.json"


@dataclass
class ValidationReport:
    spec: str
    stage: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    admitted: list[str] = field(default_factory=list)
    terminal: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "passed" if self.ok else "failed",
            "spec": self.spec,
            "stage": self.stage,
            "admitted_frameworks": self.admitted,
            "terminal_frameworks": self.terminal,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def repo_path(root: Path, value: object) -> Path | None:
    if not nonempty_string(value):
        return None
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def repo_relative_key(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def require_keys(
    value: object, keys: list[str], label: str, report: ValidationReport
) -> dict[str, Any]:
    if not isinstance(value, dict):
        report.errors.append(f"{label}_must_be_object")
        return {}
    for key in keys:
        if key not in value:
            report.errors.append(f"{label}_missing_{key}")
    return value


def require_existing_file(root: Path, value: object, label: str, report: ValidationReport) -> None:
    path = repo_path(root, value)
    if path is None or not path.is_file():
        report.errors.append(f"{label}_missing_file:{value}")


def validate_campaign(
    spec: dict[str, Any], standard: dict[str, Any], report: ValidationReport
) -> None:
    campaign = require_keys(
        spec.get("campaign"),
        [
            "campaign_id",
            "comparison_mode",
            "recovery_policy",
            "primary_attempt_policy",
            "freeze_manifest",
            "framework_ids",
            "experiment_budget",
            "timeout_seconds",
            "fresh_run_root_required",
        ],
        "campaign",
        report,
    )
    if campaign.get("comparison_mode") != "synchronized_primary":
        report.errors.append("campaign_comparison_mode_must_be_synchronized_primary")
    if campaign.get("recovery_policy") != "separate_campaign":
        report.errors.append("campaign_recovery_must_be_separate")
    if campaign.get("primary_attempt_policy") != "one_fresh_attempt_per_framework":
        report.errors.append("campaign_primary_attempt_policy_must_be_one_fresh_attempt")
    if campaign.get("framework_ids") != standard["framework_ids"]:
        report.errors.append("campaign_framework_ids_must_be_ordered_01_to_07")
    if campaign.get("fresh_run_root_required") is not True:
        report.errors.append("campaign_fresh_run_root_required")
    timeout = campaign.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        report.errors.append("campaign_timeout_seconds_must_be_positive_integer")

    budget = require_keys(
        campaign.get("experiment_budget"), ["minimum", "maximum"], "budget", report
    )
    minimum = budget.get("minimum")
    maximum = budget.get("maximum")
    standard_budget = standard["experiment_budget"]
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int)
        or not isinstance(maximum, int)
        or minimum < standard_budget["minimum"]
        or maximum > standard_budget["maximum"]
        or minimum > maximum
    ):
        report.errors.append("campaign_experiment_budget_must_be_between_2_and_4")


def validate_topic_adapter(
    root: Path, spec: dict[str, Any], standard: dict[str, Any], report: ValidationReport
) -> None:
    topic = require_keys(
        spec.get("topic_adapter"),
        [
            "topic_id",
            "contract_file",
            "dataset_env",
            "framework_dataset_mount",
            "input_generator",
            "official_scorer",
            "run_validator",
            "selection_score_policy",
            "official_score_owner",
            "primary_metric",
            "required_trace_fields",
            "required_framework_artifacts",
            "official_score_artifact",
            "host_only_inputs",
            "framework_visible_inputs",
            "shared_prompt_sources",
        ],
        "topic_adapter",
        report,
    )
    for key in ("contract_file", "input_generator", "official_scorer", "run_validator"):
        require_existing_file(root, topic.get(key), f"topic_adapter_{key}", report)
    if not nonempty_string(topic.get("dataset_env")):
        report.errors.append("topic_adapter_dataset_env_required")
    mount = topic.get("framework_dataset_mount")
    if not nonempty_string(mount) or not str(mount).startswith("/data/"):
        report.errors.append("topic_adapter_framework_dataset_mount_must_be_under_data")
    if topic.get("official_score_owner") != "host":
        report.errors.append("topic_adapter_official_score_owner_must_be_host")
    if topic.get("selection_score_policy") != "framework_visible_validation_only":
        report.errors.append("topic_adapter_selection_must_use_visible_validation_only")
    if not nonempty_string(topic.get("primary_metric")):
        report.errors.append("topic_adapter_primary_metric_required")
    if topic.get("required_trace_fields") != standard["required_trace_fields"]:
        report.errors.append("topic_adapter_trace_fields_must_match_standard")
    artifacts = topic.get("required_framework_artifacts")
    if not isinstance(artifacts, list):
        report.errors.append("topic_adapter_required_artifacts_must_be_list")
    else:
        missing = sorted(set(standard["required_framework_artifacts"]) - set(artifacts))
        if missing:
            report.errors.append("topic_adapter_missing_required_artifacts:" + ",".join(missing))
    if topic.get("official_score_artifact") in set(artifacts or []):
        report.errors.append("host_score_artifact_must_not_be_framework_authored")
    if not isinstance(topic.get("host_only_inputs"), list):
        report.errors.append("topic_adapter_host_only_inputs_must_be_list")
    visible_inputs = topic.get("framework_visible_inputs")
    if not isinstance(visible_inputs, list) or not visible_inputs:
        report.errors.append("topic_adapter_framework_visible_inputs_required")
    elif set(topic.get("host_only_inputs", [])) & set(visible_inputs):
        report.errors.append("topic_adapter_host_only_inputs_exposed_to_framework")
    shared_prompt_sources = topic.get("shared_prompt_sources")
    if not isinstance(shared_prompt_sources, list) or not shared_prompt_sources:
        report.errors.append("topic_adapter_shared_prompt_sources_required")
    else:
        for index, value in enumerate(shared_prompt_sources):
            require_existing_file(
                root,
                value,
                f"topic_adapter_shared_prompt_source_{index}",
                report,
            )


def validate_model_adapter(
    root: Path, spec: dict[str, Any], standard: dict[str, Any], report: ValidationReport
) -> None:
    model = require_keys(
        spec.get("model_adapter"),
        [
            "variant",
            "model_id",
            "provider_config",
            "wire_protocol",
            "container_base_url",
            "required_env",
            "relay_preflight",
            "public_provider_forbidden",
            "effective_model_evidence_required",
            "runtime_policy",
        ],
        "model_adapter",
        report,
    )
    require_existing_file(
        root, model.get("provider_config"), "model_adapter_provider_config", report
    )
    require_existing_file(
        root, model.get("relay_preflight"), "model_adapter_relay_preflight", report
    )
    if model.get("required_env") != standard["required_model_env"]:
        report.errors.append("model_adapter_required_env_must_match_standard")
    if model.get("public_provider_forbidden") is not True:
        report.errors.append("model_adapter_public_provider_must_be_forbidden")
    if model.get("effective_model_evidence_required") is not True:
        report.errors.append("model_adapter_effective_model_evidence_required")
    base_url = str(model.get("container_base_url", "")).lower()
    if not base_url.startswith(("http://", "https://")):
        report.errors.append("model_adapter_container_base_url_required")
    if any(marker in base_url for marker in standard["public_provider_markers"]):
        report.errors.append("model_adapter_public_provider_url_forbidden")
    if model.get("wire_protocol") not in {"responses", "chat_completions"}:
        report.errors.append("model_adapter_wire_protocol_unsupported")

    provider_path = repo_path(root, model.get("provider_config"))
    if provider_path and provider_path.is_file():
        text = provider_path.read_text(encoding="utf-8", errors="ignore")

        def toml_string(key: str) -> str | None:
            match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
            return match.group(1) if match else None

        if toml_string("model") != model.get("model_id"):
            report.errors.append("model_adapter_provider_model_mismatch")
        if toml_string("base_url") != model.get("container_base_url"):
            report.errors.append("model_adapter_provider_base_url_mismatch")
        if toml_string("wire_api") != model.get("wire_protocol"):
            report.errors.append("model_adapter_provider_wire_protocol_mismatch")

    runtime_policy = require_keys(
        model.get("runtime_policy"),
        [
            "compact_experiment_ledger_required",
            "runtime_package_install_forbidden",
            "remote_request_budget",
            "minimum_batch_size",
        ],
        "model_adapter_runtime_policy",
        report,
    )
    if runtime_policy.get("compact_experiment_ledger_required") is not True:
        report.errors.append("model_adapter_compact_ledger_required")
    if runtime_policy.get("runtime_package_install_forbidden") is not True:
        report.errors.append("model_adapter_runtime_package_install_must_be_forbidden")
    for key in ("remote_request_budget", "minimum_batch_size"):
        value = runtime_policy.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            report.errors.append(f"model_adapter_{key}_must_be_positive_or_null")


def validate_ownership(
    spec: dict[str, Any], standard: dict[str, Any], report: ValidationReport
) -> None:
    ownership = require_keys(
        spec.get("ownership"),
        [
            "framework_responsibilities",
            "host_responsibilities",
            "host_artifact_backfill_forbidden",
        ],
        "ownership",
        report,
    )
    if (
        ownership.get("framework_responsibilities")
        != standard["required_framework_responsibilities"]
    ):
        report.errors.append("ownership_framework_responsibilities_must_match_standard")
    host = ownership.get("host_responsibilities")
    if not isinstance(host, list) or not set(host).issubset(
        set(standard["allowed_host_responsibilities"])
    ):
        report.errors.append("ownership_host_responsibilities_exceed_standard")
    if ownership.get("host_artifact_backfill_forbidden") is not True:
        report.errors.append("ownership_host_artifact_backfill_must_be_forbidden")


def validate_ideation(
    spec: dict[str, Any], standard: dict[str, Any], report: ValidationReport
) -> None:
    policy = require_keys(
        spec.get("ideation_policy"),
        [
            "framework_owns_method_choice",
            "host_method_prescription_forbidden",
            "prescribed_methods",
            "idea_artifact",
            "idea_locked_before_experiments",
            "allowed_host_constraints",
            "forbidden_host_constraints",
        ],
        "ideation_policy",
        report,
    )
    expected = standard["ideation_policy"]
    for key in (
        "framework_owns_method_choice",
        "host_method_prescription_forbidden",
        "idea_artifact",
        "idea_locked_before_experiments",
        "allowed_host_constraints",
        "forbidden_host_constraints",
    ):
        if policy.get(key) != expected[key]:
            report.errors.append(f"ideation_policy_{key}_must_match_standard")
    if policy.get("prescribed_methods") != []:
        report.errors.append("ideation_policy_prescribed_methods_must_be_empty")


def validate_workspace(
    spec: dict[str, Any], standard: dict[str, Any], report: ValidationReport
) -> None:
    workspace = require_keys(
        spec.get("workspace_policy"),
        [
            "runtime_workspace",
            "fresh_physical_workspace_required",
            "dataset_read_only",
            "contract_read_only",
            "repository_root_writable_mount_forbidden",
        ],
        "workspace_policy",
        report,
    )
    expected = standard["workspace_policy"]
    for key in (
        "runtime_workspace",
        "fresh_physical_workspace_required",
        "dataset_read_only",
        "contract_read_only",
        "repository_root_writable_mount_forbidden",
    ):
        if workspace.get(key) != expected[key]:
            report.errors.append(f"workspace_policy_{key}_must_match_standard")


def validate_framework_adapters(
    root: Path,
    spec: dict[str, Any],
    standard: dict[str, Any],
    report: ValidationReport,
) -> None:
    adapters = spec.get("framework_adapters")
    if not isinstance(adapters, list):
        report.errors.append("framework_adapters_must_be_list")
        return
    ids = [item.get("framework_id") for item in adapters if isinstance(item, dict)]
    if ids != standard["framework_ids"]:
        report.errors.append("framework_adapters_must_be_ordered_01_to_07")
        return

    required_env = spec.get("model_adapter", {}).get("required_env")
    forbidden_tokens = standard["forbidden_native_entrypoint_tokens"]
    terminal_statuses = set(standard["dispatch_terminal_statuses"])
    valid_statuses = set(standard["adaptation_statuses"])
    for item in adapters:
        framework_id = item["framework_id"]
        label = f"framework_{framework_id}"
        status = item.get("status")
        if status not in valid_statuses:
            report.errors.append(f"{label}_invalid_status:{status}")
            continue
        if status in terminal_statuses:
            if not nonempty_string(item.get("blocker")):
                report.errors.append(f"{label}_{status}_requires_blocker")
            report.terminal[framework_id] = status
            continue

        for key in (
            "native_entrypoint",
            "entrypoint_source",
            "fullrun_wrapper",
            "runtime_image",
            "executor_kind",
            "provider_injection",
            "native_log_marker",
            "same_image_smoke",
        ):
            if not nonempty_string(item.get(key)):
                report.errors.append(f"{label}_missing_{key}")
        entrypoint = str(item.get("native_entrypoint", "")).lower()
        allowed_codex_kinds = set(
            standard.get("allowed_codex_native_executor_kinds", ["official_framework_skill"])
        )
        official_skill_executor = item.get("executor_kind") in allowed_codex_kinds
        if any(token in entrypoint for token in forbidden_tokens) and not official_skill_executor:
            report.errors.append(f"{label}_generic_codex_native_entrypoint_forbidden")
        if item.get("provider_env") != required_env:
            report.errors.append(f"{label}_provider_env_must_match_model_adapter")
        for key in ("entrypoint_source", "fullrun_wrapper", "same_image_smoke"):
            require_existing_file(root, item.get(key), f"{label}_{key}", report)
        prompt_sources = item.get("prompt_sources")
        if not isinstance(prompt_sources, list) or not prompt_sources:
            report.errors.append(f"{label}_prompt_sources_required")
        else:
            for index, value in enumerate(prompt_sources):
                require_existing_file(
                    root, value, f"{label}_prompt_source_{index}", report
                )
        wrapper = repo_path(root, item.get("fullrun_wrapper"))
        if wrapper and wrapper.is_file():
            wrapper_text = wrapper.read_text(encoding="utf-8", errors="ignore").lower()
            if any(token in wrapper_text for token in forbidden_tokens) and not official_skill_executor:
                report.errors.append(f"{label}_generic_codex_fullrun_forbidden")

        if report.stage in {"freeze", "dispatch"}:
            if status != "admitted":
                report.errors.append(f"{label}_must_be_admitted_or_terminal_for_dispatch")
                continue
            if not nonempty_string(item.get("runtime_image_digest")):
                report.errors.append(f"{label}_missing_runtime_image_digest")
                continue
            prompt_audit = repo_path(root, item.get("prompt_audit"))
            if prompt_audit is None or not prompt_audit.is_file():
                report.errors.append(f"{label}_missing_prompt_audit")
                continue
            try:
                audit = load_json(prompt_audit)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                report.errors.append(f"{label}_invalid_prompt_audit:{exc}")
                continue
            source_values = [
                *spec.get("topic_adapter", {}).get("shared_prompt_sources", []),
                *item.get("prompt_sources", []),
            ]
            expected_prompt_files = {}
            for value in source_values:
                path = repo_path(root, value)
                if path is None or not path.is_file():
                    continue
                key = repo_relative_key(root, path)
                expected_prompt_files[key] = sha256_file(path)
            actual_prompt_files = {
                entry.get("path"): entry.get("sha256")
                for entry in audit.get("prompt_files", [])
                if isinstance(entry, dict)
            }
            expected_audit = {
                "standard_version": standard.get("standard_version"),
                "framework_id": framework_id,
                "status": "passed",
                "method_choice_owned_by_framework": True,
                "prescribed_methods": [],
                "reviewed_host_constraints": standard["ideation_policy"][
                    "allowed_host_constraints"
                ],
            }
            audit_mismatches = [
                key for key, value in expected_audit.items() if audit.get(key) != value
            ]
            if audit_mismatches or actual_prompt_files != expected_prompt_files:
                report.errors.append(f"{label}_prompt_audit_does_not_match_sources")
                continue
            evidence = repo_path(root, item.get("admission_evidence"))
            if evidence is None or not evidence.is_file():
                report.errors.append(f"{label}_missing_admission_evidence")
                continue
            try:
                payload = load_json(evidence)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                report.errors.append(f"{label}_invalid_admission_evidence:{exc}")
                continue
            expected = {
                "framework_id": framework_id,
                "status": "passed",
                "model_id": spec.get("model_adapter", {}).get("model_id"),
                "container_base_url": spec.get("model_adapter", {}).get("container_base_url"),
                "runtime_image": item.get("runtime_image"),
                "runtime_image_digest": item.get("runtime_image_digest"),
            }
            mismatches = [key for key, value in expected.items() if payload.get(key) != value]
            required_checks = {
                "native_entrypoint",
                "relay_request",
                "topic_inputs",
                "workspace_write",
                "scorer_dependencies",
            }
            checks = payload.get("checks")
            if (
                mismatches
                or not isinstance(checks, dict)
                or not all(checks.get(key) is True for key in required_checks)
            ):
                report.errors.append(f"{label}_admission_evidence_does_not_match_runtime")
                continue
            report.admitted.append(framework_id)
        elif status == "admitted":
            report.warnings.append(f"{label}_admission_evidence_not_checked_until_dispatch")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_paths(root: Path, spec_path: Path, spec: dict[str, Any]) -> list[Path]:
    topic = spec.get("topic_adapter", {})
    model = spec.get("model_adapter", {})
    values: list[object] = [
        spec_path,
        STANDARD_PATH,
        topic.get("contract_file"),
        topic.get("input_generator"),
        topic.get("official_scorer"),
        topic.get("run_validator"),
        model.get("provider_config"),
        model.get("relay_preflight"),
        *topic.get("shared_prompt_sources", []),
    ]
    for item in spec.get("framework_adapters", []):
        if not isinstance(item, dict) or item.get("status") in {"unsupported", "blocked"}:
            continue
        values.extend(
            [
                item.get("entrypoint_source"),
                item.get("fullrun_wrapper"),
                item.get("same_image_smoke"),
                item.get("admission_evidence"),
                item.get("prompt_audit"),
                *item.get("prompt_sources", []),
            ]
        )
    paths: list[Path] = []
    for value in values:
        if isinstance(value, Path):
            path = value
        else:
            path = repo_path(root, value)
        if path is not None and path.is_file() and path not in paths:
            paths.append(path)
    return paths


def freeze_payload(root: Path, spec_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    files = {}
    for path in frozen_paths(root, spec_path, spec):
        key = repo_relative_key(root, path)
        files[key] = sha256_file(path)
    images = {
        item["framework_id"]: {
            "runtime_image": item.get("runtime_image"),
            "runtime_image_digest": item.get("runtime_image_digest"),
        }
        for item in spec.get("framework_adapters", [])
        if isinstance(item, dict) and item.get("status") == "admitted"
    }
    return {
        "standard_version": spec.get("spec_version"),
        "campaign_id": spec.get("campaign", {}).get("campaign_id"),
        "files": files,
        "framework_images": images,
    }


def validate_freeze(
    root: Path,
    spec_path: Path,
    spec: dict[str, Any],
    report: ValidationReport,
) -> None:
    if report.stage != "dispatch":
        return
    manifest_path = repo_path(root, spec.get("campaign", {}).get("freeze_manifest"))
    if manifest_path is None or not manifest_path.is_file():
        report.errors.append("campaign_freeze_manifest_missing")
        return
    try:
        actual = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report.errors.append(f"campaign_freeze_manifest_invalid:{exc}")
        return
    expected = freeze_payload(root, spec_path, spec)
    if actual != expected:
        report.errors.append("campaign_freeze_manifest_does_not_match_current_inputs")


def validate_reporting(
    spec: dict[str, Any], standard: dict[str, Any], report: ValidationReport
) -> None:
    reporting = require_keys(
        spec.get("reporting"),
        [
            "outcome_dimensions",
            "result_views",
            "missing_score_value",
            "separate_model_tables",
            "recovery_runs_labeled",
            "idea_evaluation",
        ],
        "reporting",
        report,
    )
    if reporting.get("outcome_dimensions") != standard["required_outcome_dimensions"]:
        report.errors.append("reporting_outcome_dimensions_must_match_standard")
    if reporting.get("result_views") != standard["required_result_views"]:
        report.errors.append("reporting_result_views_must_match_standard")
    if reporting.get("missing_score_value") != "N/A":
        report.errors.append("reporting_missing_score_must_be_NA")
    if reporting.get("separate_model_tables") is not True:
        report.errors.append("reporting_models_must_be_separate")
    if reporting.get("recovery_runs_labeled") is not True:
        report.errors.append("reporting_recovery_runs_must_be_labeled")
    idea = reporting.get("idea_evaluation")
    expected_idea = {
        "enabled": True,
        "artifact": standard["ideation_policy"]["idea_artifact"],
        "blind_to_framework_identity": True,
        "judge_sees_experiment_results": False,
        "separate_from_task_score": True,
        "dimensions": standard["ideation_policy"]["idea_quality_dimensions"],
    }
    if idea != expected_idea:
        report.errors.append("reporting_idea_evaluation_must_match_standard")


def validate_spec(
    spec_path: Path, *, root: Path = ROOT, stage: str = "adaptation"
) -> ValidationReport:
    report = ValidationReport(spec=str(spec_path), stage=stage)
    try:
        standard = load_json(STANDARD_PATH)
        spec = load_json(spec_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report.errors.append(f"invalid_json:{exc}")
        return report
    if spec.get("spec_version") != standard.get("standard_version"):
        report.errors.append("spec_version_mismatch")
    validate_campaign(spec, standard, report)
    validate_topic_adapter(root, spec, standard, report)
    validate_model_adapter(root, spec, standard, report)
    validate_ownership(spec, standard, report)
    validate_ideation(spec, standard, report)
    validate_workspace(spec, standard, report)
    validate_framework_adapters(root, spec, standard, report)
    validate_reporting(spec, standard, report)
    validate_freeze(root, spec_path, spec, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a native framework evaluation adaptation or dispatch spec."
    )
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument(
        "--stage", choices=["adaptation", "freeze", "dispatch"], default="adaptation"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root.expanduser()
    spec_path = args.spec.expanduser()
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    report = validate_spec(spec_path, root=root, stage=args.stage)
    rendered = json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

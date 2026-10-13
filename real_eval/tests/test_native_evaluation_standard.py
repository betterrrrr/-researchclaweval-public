from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "real_eval/scripts/validate_native_evaluation_spec.py"
TEMPLATE_PATH = ROOT / "real_eval/templates/native_evaluation_spec.v1.json"
STANDARD_PATH = ROOT / "real_eval/standards/native_evaluation_standard.v1.json"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_native_evaluation_spec", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


def write(path: Path, content: str = "fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_spec(root: Path, *, status: str = "pending") -> tuple[Path, dict]:
    critical_files = [
        "automation/topic_contract.md",
        "automation/scripts/generate_topic_inputs.py",
        "automation/scripts/run_topic_score.py",
        "automation/scripts/validate_topic_run.py",
        "api/model_container.toml",
        "real_eval/scripts/preflight_model_relay.sh",
    ]
    for name in critical_files:
        write(root / name)
    write(
        root / "api/model_container.toml",
        'model = "test-model"\n'
        'base_url = "http://host.docker.internal:9999/v1"\n'
        'wire_api = "responses"\n',
    )

    framework_adapters = []
    for framework_id in ["01", "02", "03", "04", "05", "06", "07"]:
        source = f"frameworks/{framework_id}/README.md"
        wrapper = f"real_eval/scripts/{framework_id}_topic_fullrun.sh"
        smoke = f"real_eval/scripts/{framework_id}_topic_smoke.sh"
        evidence = f"admission/{framework_id}.json"
        prompt_audit = f"admission/{framework_id}.prompt-audit.json"
        write(root / source)
        write(root / wrapper, "#!/usr/bin/env bash\nnative-framework run\n")
        write(root / smoke, "#!/usr/bin/env bash\nnative-framework smoke\n")
        runtime_image = f"framework-{framework_id}:runtime-ready"
        runtime_image_digest = f"sha256:{framework_id * 32}"
        if status == "admitted":
            write(
                root / evidence,
                json.dumps(
                    {
                        "framework_id": framework_id,
                        "status": "passed",
                        "model_id": "test-model",
                        "container_base_url": "http://host.docker.internal:9999/v1",
                        "runtime_image": runtime_image,
                        "runtime_image_digest": runtime_image_digest,
                        "checks": {
                            "native_entrypoint": True,
                            "relay_request": True,
                            "topic_inputs": True,
                            "workspace_write": True,
                            "scorer_dependencies": True,
                        },
                    }
                )
                + "\n",
            )
            prompt_files = []
            for prompt_path in [
                "automation/topic_contract.md",
                "automation/scripts/generate_topic_inputs.py",
                wrapper,
            ]:
                prompt_files.append(
                    {
                        "path": prompt_path,
                        "sha256": VALIDATOR.sha256_file(root / prompt_path),
                    }
                )
            write(
                root / prompt_audit,
                json.dumps(
                    {
                        "standard_version": "1.0",
                        "framework_id": framework_id,
                        "status": "passed",
                        "method_choice_owned_by_framework": True,
                        "prescribed_methods": [],
                        "reviewed_host_constraints": [
                            "topic_question",
                            "data_visibility",
                            "train_validation_split",
                            "official_metric",
                            "compute_budget",
                            "wall_clock_budget",
                            "request_budget",
                            "experiment_count_range",
                            "available_dependencies",
                            "network_policy",
                            "safety_policy",
                            "output_schema",
                        ],
                        "prompt_files": prompt_files,
                    }
                )
                + "\n",
            )
        framework_adapters.append(
            {
                "framework_id": framework_id,
                "status": status,
                "native_entrypoint": "native-framework run",
                "entrypoint_source": source,
                "fullrun_wrapper": wrapper,
                "runtime_image": runtime_image,
                "runtime_image_digest": runtime_image_digest if status == "admitted" else None,
                "executor_kind": "framework_cli",
                "provider_injection": (
                    "native client reads OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
                ),
                "provider_env": [
                    "OPENAI_BASE_URL",
                    "OPENAI_API_KEY",
                    "OPENAI_MODEL",
                ],
                "native_log_marker": f"FRAMEWORK_{framework_id}_NATIVE",
                "same_image_smoke": smoke,
                "prompt_sources": [wrapper],
                "prompt_audit": prompt_audit if status == "admitted" else None,
                "admission_evidence": evidence if status == "admitted" else None,
                "blocker": None,
            }
        )

    payload = {
        "spec_version": "1.0",
        "campaign": {
            "campaign_id": "test-topic-model-synchronized-v1",
            "comparison_mode": "synchronized_primary",
            "recovery_policy": "separate_campaign",
            "primary_attempt_policy": "one_fresh_attempt_per_framework",
            "freeze_manifest": "real_eval/config/test.freeze.json",
            "framework_ids": ["01", "02", "03", "04", "05", "06", "07"],
            "experiment_budget": {"minimum": 2, "maximum": 2},
            "timeout_seconds": 3600,
            "fresh_run_root_required": True,
        },
        "topic_adapter": {
            "topic_id": "test_topic",
            "contract_file": "automation/topic_contract.md",
            "dataset_env": "TEST_TOPIC_DATASET_ROOT",
            "framework_dataset_mount": "/data/test_topic",
            "input_generator": "automation/scripts/generate_topic_inputs.py",
            "official_scorer": "automation/scripts/run_topic_score.py",
            "run_validator": "automation/scripts/validate_topic_run.py",
            "selection_score_policy": "framework_visible_validation_only",
            "official_score_owner": "host",
            "primary_metric": "test_score",
            "required_trace_fields": [
                "framework_native_execution",
                "consumed_topic_input",
                "workspace_trace_root",
                "framework_internal_model",
                "framework_internal_api_base_url",
                "experiments",
                "selected_experiment_id",
                "idea_artifact",
                "idea_locked_before_experiments",
            ],
            "required_framework_artifacts": [
                "predictions.jsonl",
                "research_idea.json",
                "experiment_trace.json",
                "final_report.md",
            ],
            "official_score_artifact": "score.json",
            "host_only_inputs": [],
            "framework_visible_inputs": ["dataset", "contract", "validation_scorer"],
            "shared_prompt_sources": [
                "automation/topic_contract.md",
                "automation/scripts/generate_topic_inputs.py",
            ],
        },
        "model_adapter": {
            "variant": "test",
            "model_id": "test-model",
            "provider_config": "api/model_container.toml",
            "wire_protocol": "responses",
            "container_base_url": "http://host.docker.internal:9999/v1",
            "required_env": [
                "OPENAI_BASE_URL",
                "OPENAI_API_KEY",
                "OPENAI_MODEL",
            ],
            "relay_preflight": "real_eval/scripts/preflight_model_relay.sh",
            "public_provider_forbidden": True,
            "effective_model_evidence_required": True,
            "runtime_policy": {
                "compact_experiment_ledger_required": True,
                "runtime_package_install_forbidden": True,
                "remote_request_budget": None,
                "minimum_batch_size": None,
            },
        },
        "ownership": {
            "framework_responsibilities": [
                "planning",
                "experiment_design",
                "experiment_execution",
                "comparison",
                "selection",
                "analysis",
                "final_artifact_delivery",
            ],
            "host_responsibilities": [
                "input_projection",
                "lifecycle_management",
                "official_scoring",
                "output_validation",
                "packaging",
            ],
            "host_artifact_backfill_forbidden": True,
        },
        "ideation_policy": {
            "framework_owns_method_choice": True,
            "host_method_prescription_forbidden": True,
            "prescribed_methods": [],
            "idea_artifact": "research_idea.json",
            "idea_locked_before_experiments": True,
            "allowed_host_constraints": [
                "topic_question",
                "data_visibility",
                "train_validation_split",
                "official_metric",
                "compute_budget",
                "wall_clock_budget",
                "request_budget",
                "experiment_count_range",
                "available_dependencies",
                "network_policy",
                "safety_policy",
                "output_schema",
            ],
            "forbidden_host_constraints": [
                "algorithm_family",
                "feature_representation",
                "model_architecture",
                "hyperparameters",
                "experiment_sequence",
                "selected_method",
            ],
        },
        "workspace_policy": {
            "runtime_workspace": "/workspace",
            "fresh_physical_workspace_required": True,
            "dataset_read_only": True,
            "contract_read_only": True,
            "repository_root_writable_mount_forbidden": True,
        },
        "framework_adapters": framework_adapters,
        "reporting": {
            "outcome_dimensions": [
                "native_compliance",
                "research_completed",
                "scored",
                "contract_complete",
                "engineering_complete",
            ],
            "result_views": ["synchronized_primary", "best_completed_native"],
            "missing_score_value": "N/A",
            "separate_model_tables": True,
            "recovery_runs_labeled": True,
            "idea_evaluation": {
                "enabled": True,
                "artifact": "research_idea.json",
                "blind_to_framework_identity": True,
                "judge_sees_experiment_results": False,
                "separate_from_task_score": True,
                "dimensions": [
                    "novelty",
                    "hypothesis_clarity",
                    "technical_soundness",
                    "feasibility",
                    "experimental_discrimination",
                ],
            },
        },
    }
    spec_path = root / "real_eval/config/test_native_spec.json"
    write(spec_path, json.dumps(payload, indent=2) + "\n")
    return spec_path, payload


def test_standard_and_template_are_versioned_and_cover_all_frameworks() -> None:
    standard = json.loads(STANDARD_PATH.read_text(encoding="utf-8"))
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert standard["standard_version"] == template["spec_version"] == "1.0"
    assert standard["framework_ids"] == ["01", "02", "03", "04", "05", "06", "07"]
    assert [item["framework_id"] for item in template["framework_adapters"]] == standard[
        "framework_ids"
    ]


def test_adaptation_accepts_complete_pending_adapters(tmp_path: Path) -> None:
    spec_path, _ = build_spec(tmp_path)
    report = VALIDATOR.validate_spec(spec_path, root=tmp_path, stage="adaptation")
    assert report.ok, report.errors


def test_adaptation_rejects_missing_framework_and_generic_codex(tmp_path: Path) -> None:
    spec_path, payload = build_spec(tmp_path)
    payload["framework_adapters"][0]["native_entrypoint"] = "codex exec --yolo"
    payload["framework_adapters"].pop()
    write(spec_path, json.dumps(payload, indent=2) + "\n")

    report = VALIDATOR.validate_spec(spec_path, root=tmp_path, stage="adaptation")
    assert not report.ok
    assert "framework_adapters_must_be_ordered_01_to_07" in report.errors


def test_dispatch_requires_matching_admission_and_frozen_inputs(tmp_path: Path) -> None:
    spec_path, payload = build_spec(tmp_path, status="admitted")
    freeze = VALIDATOR.freeze_payload(tmp_path, spec_path, payload)
    freeze_path = tmp_path / payload["campaign"]["freeze_manifest"]
    write(freeze_path, json.dumps(freeze, indent=2) + "\n")

    report = VALIDATOR.validate_spec(spec_path, root=tmp_path, stage="dispatch")
    assert report.ok, report.errors
    assert report.admitted == ["01", "02", "03", "04", "05", "06", "07"]

    wrapper = tmp_path / payload["framework_adapters"][0]["fullrun_wrapper"]
    write(wrapper, "#!/usr/bin/env bash\nnative-framework changed\n")
    changed_report = VALIDATOR.validate_spec(spec_path, root=tmp_path, stage="dispatch")
    assert not changed_report.ok
    assert "campaign_freeze_manifest_does_not_match_current_inputs" in changed_report.errors


def test_adaptation_rejects_generic_codex_wrapper(tmp_path: Path) -> None:
    spec_path, payload = build_spec(tmp_path)
    wrapper = tmp_path / payload["framework_adapters"][2]["fullrun_wrapper"]
    write(wrapper, "#!/usr/bin/env bash\ncodex exec --yolo 'imitate framework'\n")

    report = VALIDATOR.validate_spec(spec_path, root=tmp_path, stage="adaptation")
    assert not report.ok
    assert "framework_03_generic_codex_fullrun_forbidden" in report.errors


def test_adaptation_accepts_documented_official_codex_skill(tmp_path: Path) -> None:
    spec_path, payload = build_spec(tmp_path)
    adapter = payload["framework_adapters"][2]
    adapter["native_entrypoint"] = "official experiment-bridge skill -> codex exec"
    adapter["executor_kind"] = "official_framework_skill"
    wrapper = tmp_path / adapter["fullrun_wrapper"]
    write(wrapper, "#!/usr/bin/env bash\ncodex exec --yolo '/experiment-bridge'\n")
    write(spec_path, json.dumps(payload, indent=2) + "\n")

    report = VALIDATOR.validate_spec(spec_path, root=tmp_path, stage="adaptation")
    assert report.ok, report.errors


def test_adaptation_rejects_prescribed_methods(tmp_path: Path) -> None:
    spec_path, payload = build_spec(tmp_path)
    payload["ideation_policy"]["prescribed_methods"] = ["TF-IDF + LogisticRegression"]
    write(spec_path, json.dumps(payload, indent=2) + "\n")

    report = VALIDATOR.validate_spec(spec_path, root=tmp_path, stage="adaptation")
    assert not report.ok
    assert "ideation_policy_prescribed_methods_must_be_empty" in report.errors

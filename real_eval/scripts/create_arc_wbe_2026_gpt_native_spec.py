#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])).expanduser()
FRAMEWORKS = [
    {
        "id": "01",
        "name": "AI-Researcher",
        "slug": "01_ai_researcher",
        "source_dir": "AI-Researcher",
        "native_entrypoint": "python research_agent/run_infer_idea.py",
        "native_probe_paths": ["research_agent/run_infer_idea.py"],
        "runtime_image": "ai-researcher:runtime-ready",
        "entrypoint_source": "AI-Researcher/README.md",
        "executor_kind": "framework_cli",
    },
    {
        "id": "02",
        "name": "AI-Scientist-v2",
        "slug": "02_ai_scientist_v2",
        "source_dir": "AI-Scientist-v2",
        "native_entrypoint": "python ai_scientist/perform_ideation_temp_free.py; python launch_scientist_bfts.py",
        "native_probe_paths": [
            "ai_scientist/perform_ideation_temp_free.py",
            "launch_scientist_bfts.py",
        ],
        "runtime_image": "ai-scientist-v2:runtime-ready",
        "entrypoint_source": "AI-Scientist-v2/README.md",
        "executor_kind": "framework_cli",
    },
    {
        "id": "03",
        "name": "ARIS",
        "slug": "03_aris",
        "source_dir": "Auto-claude-code-research-in-sleep",
        "native_entrypoint": "ARIS /experiment-bridge official skill",
        "native_probe_paths": ["skills/skills-codex/experiment-bridge/SKILL.md"],
        "runtime_image": "aris:runtime-ready",
        "entrypoint_source": "Auto-claude-code-research-in-sleep/README.md",
        "executor_kind": "official_framework_skill",
    },
    {
        "id": "04",
        "name": "AutoResearchClaw",
        "slug": "04_autoresearchclaw",
        "source_dir": "AutoResearchClaw",
        "native_entrypoint": "python -m researchclaw.cli run",
        "native_probe_paths": ["researchclaw/cli.py"],
        "runtime_image": "autoresearchclaw:runtime-ready",
        "entrypoint_source": "AutoResearchClaw/README.md",
        "executor_kind": "framework_cli",
    },
    {
        "id": "05",
        "name": "DeepScientist",
        "slug": "05_deepscientist",
        "source_dir": "DeepScientist",
        "native_entrypoint": "ds init; ds new; ds run experiment --runner codex",
        "native_probe_paths": ["src/deepscientist/cli.py"],
        "runtime_image": "deepscientist:runtime-ready",
        "entrypoint_source": "DeepScientist/README.md",
        "executor_kind": "framework_cli",
    },
    {
        "id": "06",
        "name": "Dr. Claw",
        "slug": "06_drclaw",
        "source_dir": "dr-claw",
        "native_entrypoint": "node server/cli.js chat --model gpt-5.4",
        "native_probe_paths": ["server/cli.js"],
        "runtime_image": "dr-claw:runtime-ready",
        "entrypoint_source": "dr-claw/README.md",
        "executor_kind": "framework_cli",
    },
    {
        "id": "07",
        "name": "EvoScientist",
        "slug": "07_evoscientist",
        "source_dir": "EvoScientist",
        "native_entrypoint": "evoscientist --use-cwd --auto-mode",
        "native_probe_paths": ["EvoScientist/__main__.py"],
        "runtime_image": "evoscientist:runtime-ready",
        "entrypoint_source": "EvoScientist/README.md",
        "executor_kind": "framework_cli",
    },
]

REQUIRED_TRACE_FIELDS = [
    "framework_native_execution",
    "consumed_topic_input",
    "workspace_trace_root",
    "framework_internal_model",
    "framework_internal_api_base_url",
    "experiments",
    "selected_experiment_id",
    "idea_artifact",
    "idea_locked_before_experiments",
]

MODEL_ID = "gpt-5.4"
PROVIDER_CONFIG = "api/codex_gpt54_shubiaobiao.toml"
CONTAINER_BASE_URL = "https://dts.deepexi.com"
RELAY_PREFLIGHT = "real_eval/scripts/preflight_arc_wbe_2026_gpt.sh"


def framework_config(campaign_id: str, spec_rel: str, freeze_rel: str) -> dict:
    rows = []
    for item in FRAMEWORKS:
        wrapper = f"real_eval/scripts/{item['slug']}_arc_wbe_2026_fullrun.sh"
        rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "run_dir": f"{item['slug']}_arc_wbe_2026_fullrun",
                "wrapper": wrapper,
                "validator": "arc_wbe_2026_fullrun",
                "required_paths": [item["source_dir"], "automation"],
                "required_images": [item["runtime_image"]],
                "source_dir": item["source_dir"],
                "native_probe_paths": item["native_probe_paths"],
                "native_entrypoint": item["native_entrypoint"],
                "provider_injection": "OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated GPT-5.4 provider",
                "kimi_injection": "OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated GPT-5.4 provider",
            }
        )
    return {
        "topic_id": "arc_wbe_2026",
        "evaluation_variant": "gpt",
        "comparison_mode": "native_framework_orchestration",
        "campaign_id": campaign_id,
        "campaign_spec": spec_rel,
        "campaign_freeze_manifest": freeze_rel,
        "model": MODEL_ID,
        "frameworks": rows,
    }


def smoke_config(campaign_id: str) -> dict:
    rows = []
    for item in FRAMEWORKS:
        rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "run_dir": f"{item['slug']}_arc_wbe_2026_smoke",
                "wrapper": f"real_eval/scripts/{item['slug']}_arc_wbe_2026_smoke.sh",
                "validator": "arc_wbe_2026_smoke",
                "required_paths": [item["source_dir"], "automation"],
                "required_images": [item["runtime_image"]],
            }
        )
    return {
        "topic_id": "arc_wbe_2026",
        "evaluation_variant": "gpt",
        "mode": "smoke",
        "campaign_id": campaign_id,
        "model": MODEL_ID,
        "frameworks": rows,
    }


def campaign_spec(campaign_id: str, freeze_rel: str) -> dict:
    adapters = []
    for item in FRAMEWORKS:
        wrapper = f"real_eval/scripts/{item['slug']}_arc_wbe_2026_fullrun.sh"
        smoke = f"real_eval/scripts/{item['slug']}_arc_wbe_2026_smoke.sh"
        adapters.append(
            {
                "framework_id": item["id"],
                "status": "pending",
                "native_entrypoint": item["native_entrypoint"],
                "entrypoint_source": item["entrypoint_source"],
                "fullrun_wrapper": wrapper,
                "runtime_image": item["runtime_image"],
                "runtime_image_digest": None,
                "executor_kind": item["executor_kind"],
                "provider_injection": "native client reads OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL from the isolated GPT-5.4 provider adapter",
                "provider_env": ["OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"],
                "native_log_marker": {
                    "01": "AI_RESEARCHER_NATIVE_INFER_IDEA",
                    "02": "AI_SCIENTIST_V2_NATIVE_BFTS",
                    "03": "ARIS_NATIVE_EXPERIMENT_BRIDGE",
                    "04": "AUTORESEARCHCLAW_NATIVE_RUN",
                    "05": "DEEPSCIENTIST_NATIVE_CODEX_RUNNER",
                    "06": "DRCLAW_NATIVE_CHAT",
                    "07": "EVOSCIENTIST_NATIVE_CLI",
                }[item["id"]],
                "same_image_smoke": smoke,
                "prompt_sources": [wrapper],
                "prompt_audit": None,
                "admission_evidence": None,
                "blocker": None,
            }
        )

    return {
        "spec_version": "1.0",
        "campaign": {
            "campaign_id": campaign_id,
            "comparison_mode": "synchronized_primary",
            "recovery_policy": "separate_campaign",
            "primary_attempt_policy": "one_fresh_attempt_per_framework",
            "freeze_manifest": freeze_rel,
            "framework_ids": [f"{index:02d}" for index in range(1, 8)],
            "experiment_budget": {"minimum": 2, "maximum": 4},
            "timeout_seconds": 7200,
            "fresh_run_root_required": True,
        },
        "topic_adapter": {
            "topic_id": "arc_wbe_2026",
            "contract_file": "automation/arc_white_box_estimation_2026_contract.md",
            "dataset_env": "ARC_WBE_2026_DATASET_ROOT",
            "framework_dataset_mount": "/data/arc_wbe_2026",
            "input_generator": "automation/scripts/generate_arc_wbe_2026_native_inputs.py",
            "official_scorer": "automation/scripts/run_arc_wbe_2026_local_score.py",
            "run_validator": "real_eval/scripts/validate_framework_run.py",
            "selection_score_policy": "framework_visible_validation_only",
            "official_score_owner": "host",
            "primary_metric": "adjusted_final_layer_score_minimize",
            "required_trace_fields": REQUIRED_TRACE_FIELDS,
            "required_framework_artifacts": [
                "research_idea.json",
                "estimator.py",
                "submission.json",
                "experiment_trace.json",
                "final_report.md",
            ],
            "official_score_artifact": "score.json",
            "host_only_inputs": ["official_labels", "official_score_runtime"],
            "framework_visible_inputs": [
                "projected_weights_schema",
                "contract",
                "input_manifest",
                "validation_policy",
            ],
            "shared_prompt_sources": [
                "automation/arc_white_box_estimation_2026_contract.md",
                "automation/arc_wbe_2026_execution_budget.md",
                "automation/scripts/generate_arc_wbe_2026_native_inputs.py",
                "automation/scripts/generate_arc_wbe_2026_weights_only_dataset.py",
            ],
        },
        "model_adapter": {
            "variant": "gpt",
            "model_id": MODEL_ID,
            "provider_config": PROVIDER_CONFIG,
            "wire_protocol": "responses",
            "container_base_url": CONTAINER_BASE_URL,
            "required_env": ["OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"],
            "relay_preflight": RELAY_PREFLIGHT,
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
        "framework_adapters": adapters,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--framework-config", type=Path, required=True)
    parser.add_argument("--smoke-config", type=Path, required=True)
    args = parser.parse_args()

    spec_path = args.spec.expanduser()
    config_path = args.framework_config.expanduser()
    smoke_config_path = args.smoke_config.expanduser()
    if not spec_path.is_absolute():
        spec_path = ROOT / spec_path
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not smoke_config_path.is_absolute():
        smoke_config_path = ROOT / smoke_config_path
    freeze_path = ROOT / "real_eval/config" / f"{args.campaign_id}.freeze.json"
    spec_rel = str(spec_path.relative_to(ROOT))
    freeze_rel = str(freeze_path.relative_to(ROOT))
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    smoke_config_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        json.dumps(campaign_spec(args.campaign_id, freeze_rel), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            framework_config(args.campaign_id, spec_rel, freeze_rel), ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    smoke_config_path.write_text(
        json.dumps(smoke_config(args.campaign_id), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "spec": str(spec_path),
                "framework_config": str(config_path),
                "smoke_config": str(smoke_config_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ID = "topic1-babylm-gpt-method-free-20260810-v1"
TOPIC_ID = "babylm"
DATASET_ENV = "BABYLM_DATASET_ROOT"
MODEL = "gpt-5.4"
PROVIDER_CONFIG = "api/codex_gpt54_shubiaobiao.toml"
CONTAINER_BASE_URL = "http://host.docker.internal:8788/v1"
CONTRACT_FILE = "automation/babylm_contract.md"
RELAY_PREFLIGHT = "real_eval/scripts/preflight_babylm_gpt_relay.sh"

FRAMEWORKS = [
    {
        "id": "01",
        "name": "AI-Researcher",
        "slug": "01_ai_researcher_real_babylm",
        "source_dir": "AI-Researcher",
        "native_entrypoint": "python research_agent/run_infer_idea.py",
        "entrypoint_source": "AI-Researcher/README.md",
        "probe_paths": ["research_agent/run_infer_idea.py"],
        "runtime_image": "ai-researcher:runtime-ready",
        "executor_kind": "framework_cli",
        "fullrun_wrapper": "01_ai_researcher_real_babylm.sh",
        "native_log_marker": "AI_RESEARCHER_NATIVE_INFER_IDEA",
    },
    {
        "id": "02",
        "name": "AI-Scientist-v2",
        "slug": "02_ai_scientist_v2_real_babylm",
        "source_dir": "AI-Scientist-v2",
        "native_entrypoint": "python ai_scientist/perform_ideation_temp_free.py; python launch_scientist_bfts.py",
        "entrypoint_source": "AI-Scientist-v2/README.md",
        "probe_paths": ["ai_scientist/perform_ideation_temp_free.py", "launch_scientist_bfts.py"],
        "runtime_image": "ai-scientist-v2:runtime-ready",
        "executor_kind": "framework_cli",
        "fullrun_wrapper": "02_ai_scientist_v2_real_babylm.sh",
        "native_log_marker": "AI_SCIENTIST_V2_NATIVE_BFTS",
    },
    {
        "id": "03",
        "name": "ARIS",
        "slug": "03_aris_real_babylm",
        "source_dir": "Auto-claude-code-research-in-sleep",
        "native_entrypoint": "ARIS /experiment-bridge official skill",
        "entrypoint_source": "Auto-claude-code-research-in-sleep/README.md",
        "probe_paths": ["skills/skills-codex/experiment-bridge/SKILL.md"],
        "runtime_image": "aris:runtime-ready",
        "executor_kind": "official_framework_skill",
        "fullrun_wrapper": "03_aris_real_babylm.sh",
        "native_log_marker": "ARIS_NATIVE_EXPERIMENT_BRIDGE",
    },
    {
        "id": "04",
        "name": "AutoResearchClaw",
        "slug": "04_autoresearchclaw_real_babylm",
        "source_dir": "AutoResearchClaw",
        "native_entrypoint": "python -m researchclaw.cli run",
        "entrypoint_source": "AutoResearchClaw/README.md",
        "probe_paths": ["researchclaw/cli.py"],
        "runtime_image": "autoresearchclaw:runtime-ready",
        "executor_kind": "framework_cli",
        "fullrun_wrapper": "04_autoresearchclaw_real_babylm.sh",
        "native_log_marker": "AUTORESEARCHCLAW_NATIVE_RUN",
    },
    {
        "id": "05",
        "name": "DeepScientist",
        "slug": "05_deepscientist_real_babylm",
        "source_dir": "DeepScientist",
        "native_entrypoint": "ds init; ds new; ds run run-experiment --runner codex",
        "entrypoint_source": "DeepScientist/README.md",
        "probe_paths": ["src/deepscientist/cli.py"],
        "runtime_image": "deepscientist:runtime-ready",
        "executor_kind": "framework_cli",
        "fullrun_wrapper": "05_deepscientist_real_babylm.sh",
        "native_log_marker": "DEEPSCIENTIST_NATIVE_CODEX_RUNNER",
    },
    {
        "id": "06",
        "name": "Dr. Claw",
        "slug": "06_drclaw_real_babylm",
        "source_dir": "dr-claw",
        "native_entrypoint": "node server/cli.js chat --model gpt-5.4",
        "entrypoint_source": "dr-claw/README.md",
        "probe_paths": ["server/cli.js"],
        "runtime_image": "dr-claw:runtime-ready",
        "executor_kind": "framework_cli",
        "fullrun_wrapper": "06_drclaw_real_babylm.sh",
        "native_log_marker": "DRCLAW_NATIVE_CHAT",
    },
    {
        "id": "07",
        "name": "EvoScientist",
        "slug": "07_evoscientist_real_babylm",
        "source_dir": "EvoScientist",
        "native_entrypoint": "evoscientist --use-cwd --auto-mode",
        "entrypoint_source": "EvoScientist/README.md",
        "probe_paths": ["EvoScientist/__main__.py"],
        "runtime_image": "evoscientist:runtime-ready",
        "executor_kind": "framework_cli",
        "fullrun_wrapper": "07_evoscientist_auto_blackwell_babylm.sh",
        "native_log_marker": "EVOSCIENTIST_NATIVE_CLI",
    },
]


def framework_config(fw: dict) -> dict:
    return {
        "id": fw["id"],
        "name": fw["name"],
        "run_dir": fw["slug"],
        "wrapper": f"real_eval/scripts/{fw['fullrun_wrapper']}",
        "validator": {
            "01": "ai_researcher_real",
            "02": "ai_scientist_v2",
            "03": "aris",
            "04": "autoresearchclaw_resume",
            "05": "deepscientist",
            "06": "drclaw",
            "07": "evoscientist_auto",
        }[fw["id"]],
        "required_paths": [fw["source_dir"]],
        "required_images": [
            fw["runtime_image"],
            *(["nvcr.io/nvidia/pytorch:25.11-py3"] if fw["id"] == "07" else []),
        ],
        "source_dir": fw["source_dir"],
        "native_probe_paths": fw["probe_paths"],
        "native_entrypoint": fw["native_entrypoint"],
        "provider_injection": "OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL resolve to the isolated deepseek-v4-flash relay",
    }


def campaign_spec() -> dict:
    return {
        "spec_version": "1.0",
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "comparison_mode": "synchronized_primary",
            "recovery_policy": "separate_campaign",
            "primary_attempt_policy": "one_fresh_attempt_per_framework",
            "freeze_manifest": f"real_eval/config/{CAMPAIGN_ID}.freeze.json",
            "framework_ids": [fw["id"] for fw in FRAMEWORKS],
            "experiment_budget": {"minimum": 2, "maximum": 4},
            "timeout_seconds": 14400,
            "fresh_run_root_required": True,
        },
        "topic_adapter": {
            "topic_id": TOPIC_ID,
            "contract_file": CONTRACT_FILE,
            "dataset_env": DATASET_ENV,
            "framework_dataset_mount": "/data/BabyLM-2026-Strict-Small",
            "input_generator": "automation/scripts/generate_babylm_native_inputs.py",
            "official_scorer": "automation/scripts/run_babylm_score.py",
            "run_validator": "real_eval/scripts/validate_framework_run.py",
            "selection_score_policy": "framework_visible_validation_only",
            "official_score_owner": "host",
            "primary_metric": "babylm_strict_small_perplexity_minimize",
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
                "research_idea.json",
                "experiment_trace.json",
                "final_report.md",
                "submission_artifacts",
            ],
            "official_score_artifact": "score.json",
            "host_only_inputs": ["official_labels", "official_score_runtime"],
            "framework_visible_inputs": ["dataset_layout", "contract", "input_manifest", "validation_policy"],
            "shared_prompt_sources": [CONTRACT_FILE],
        },
        "model_adapter": {
            "variant": "gpt",
            "model_id": MODEL,
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
                "planning", "experiment_design", "experiment_execution",
                "comparison", "selection", "analysis", "final_artifact_delivery",
            ],
            "host_responsibilities": [
                "input_projection", "lifecycle_management",
                "official_scoring", "output_validation", "packaging",
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
                "topic_question", "data_visibility", "train_validation_split",
                "official_metric", "compute_budget", "wall_clock_budget",
                "request_budget", "experiment_count_range",
                "available_dependencies", "network_policy", "safety_policy", "output_schema",
            ],
            "forbidden_host_constraints": [
                "algorithm_family", "feature_representation", "model_architecture",
                "hyperparameters", "experiment_sequence", "selected_method",
            ],
        },
        "workspace_policy": {
            "runtime_workspace": "/workspace",
            "fresh_physical_workspace_required": True,
            "dataset_read_only": True,
            "contract_read_only": True,
            "repository_root_writable_mount_forbidden": True,
        },
        "framework_adapters": [
            {
                "framework_id": fw["id"],
                "status": "pending",
                "native_entrypoint": fw["native_entrypoint"],
                "entrypoint_source": fw["entrypoint_source"],
                "fullrun_wrapper": f"real_eval/scripts/{fw['fullrun_wrapper']}",
                "runtime_image": fw["runtime_image"],
                "executor_kind": fw["executor_kind"],
                "provider_injection": "native client reads OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL from the isolated GPT provider adapter",
                "provider_env": ["OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"],
                "native_log_marker": fw["native_log_marker"],
                "prompt_sources": [f"real_eval/scripts/{fw['fullrun_wrapper']}"],
                "blocker": None,
            }
            for fw in FRAMEWORKS
        ],
        "reporting": {
            "outcome_dimensions": [
                "native_compliance", "research_completed", "scored",
                "contract_complete", "engineering_complete",
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
                    "novelty", "hypothesis_clarity", "technical_soundness",
                    "feasibility", "experimental_discrimination",
                ],
            },
        },
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create BabyLM GPT native evaluation spec")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "real_eval" / "config")
    parser.add_argument("--timestamp", default=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    campaign = campaign_spec()
    campaign_path = output_dir / f"{CAMPAIGN_ID}.json"
    write_json(campaign_path, campaign)
    print(f"Wrote campaign spec: {campaign_path}")

    frameworks = [framework_config(fw) for fw in FRAMEWORKS]
    frameworks_config = {
        "topic_id": TOPIC_ID,
        "evaluation_variant": "deepseek",
        "comparison_mode": "native_framework_orchestration",
        "campaign_id": CAMPAIGN_ID,
        "campaign_spec": f"real_eval/config/{CAMPAIGN_ID}.json",
        "campaign_freeze_manifest": f"real_eval/config/{CAMPAIGN_ID}.freeze.json",
        "model": MODEL,
        "frameworks": frameworks,
    }
    frameworks_path = output_dir / f"seven_babylm_method_free_gpt_{args.timestamp.replace('-', '')}_frameworks.json"
    write_json(frameworks_path, frameworks_config)
    print(f"Wrote framework config: {frameworks_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

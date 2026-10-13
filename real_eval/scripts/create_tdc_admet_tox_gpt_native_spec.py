#!/usr/bin/env python3
"""Create the frozen-admission input for a Topic 5 GPT campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ADAPTERS = {
    "01": ("AI-Researcher", "python research_agent/run_infer_idea.py", "AI-Researcher/README.md", "ai-researcher:runtime-ready", "framework_cli", "real_eval/scripts/01_ai_researcher_tdc_admet_tox_fullrun.sh", "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh", "AI_RESEARCHER_TDC_IMPORT_GATE_OK"),
    "02": ("AI-Scientist-v2", "python3 launch_scientist_bfts.py", "AI-Scientist-v2/README.md", "ai-scientist-v2:runtime-ready", "framework_cli", "real_eval/scripts/02_ai_scientist_v2_tdc_admet_tox_fullrun.sh", "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh", "AI_SCIENTIST_V2_NATIVE"),
    "03": ("ARIS", "install_aris_codex.sh -> /research-pipeline", "Auto-claude-code-research-in-sleep/skills/skills-codex/README.md", "aris:runtime-ready", "official_framework_skill", "real_eval/scripts/03_aris_tdc_admet_tox_fullrun.sh", "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh", "ARIS_CODEX_NATIVE_RESEARCH_PIPELINE_TDC"),
    "04": ("AutoResearchClaw", "python3 -m researchclaw.cli run", "AutoResearchClaw/README.md", "autoresearchclaw:runtime-ready", "framework_cli", "real_eval/scripts/04_autoresearchclaw_tdc_admet_tox_fullrun.sh", "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh", "AUTORESEARCHCLAW_NATIVE"),
    "05": ("DeepScientist", "ds --home /workspace/.deepscientist run run-experiment --runner codex", "DeepScientist/README.md", "deepscientist:tdc-runtime-ready", "framework_internal_codex_runner", "real_eval/scripts/05_deepscientist_tdc_admet_tox_fullrun.sh", "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh", "DEEPSCIENTIST_NATIVE_CODEX_RUNNER_TDC"),
    "06": ("Dr. Claw", "node server/cli.js chat --model gpt-5.4", "dr-claw/README.md", "dr-claw:runtime-ready", "framework_cli", "real_eval/scripts/06_drclaw_tdc_admet_tox_fullrun.sh", "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh", "DRCLAW_NATIVE_CHAT_TDC"),
    "07": ("EvoScientist", "evoscientist --use-cwd --auto-mode", "EvoScientist/README.md", "evoscientist:runtime-ready", "framework_cli", "real_eval/scripts/07_evoscientist_tdc_admet_tox_fullrun.sh", "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh", "EVOSCIENTIST_NATIVE"),
}


def build(
    campaign_id: str,
    *,
    variant: str = "gpt",
    model: str = "gpt-5.4",
    provider_config: str = "api/codex_gpt54_shubiaobiao.toml",
    container_base_url: str = "https://dts.deepexi.com",
    wire_protocol: str = "responses",
    smoke_runner: str = "real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh",
) -> dict[str, object]:
    adapters = []
    legacy_frameworks = []
    run_dirs = {
        "01": "01_ai_researcher_tdc_admet_tox_fullrun",
        "02": "02_ai_scientist_v2_tdc_admet_tox_fullrun",
        "03": "03_aris_tdc_admet_tox_fullrun",
        "04": "04_autoresearchclaw_tdc_admet_tox_fullrun",
        "05": "05_deepscientist_tdc_admet_tox_fullrun",
        "06": "06_drclaw_tdc_admet_tox_fullrun",
        "07": "07_evoscientist_tdc_admet_tox_fullrun",
    }
    source_prefixes = {
        "01": "AI-Researcher",
        "02": "AI-Scientist-v2",
        "03": "Auto-claude-code-research-in-sleep",
        "04": "AutoResearchClaw",
        "05": "DeepScientist",
        "06": "dr-claw",
        "07": "EvoScientist",
    }
    for framework_id in [f"{i:02d}" for i in range(1, 8)]:
        name, entrypoint, source, image, executor, wrapper, smoke, marker = ADAPTERS[framework_id]
        if framework_id == "06" and entrypoint.startswith("node server/cli.js chat"):
            entrypoint = f"node server/cli.js chat --model {model}"
        smoke = smoke_runner
        provider_injection = "native framework client reads the isolated OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
        if framework_id == "03":
            provider_injection = "ARIS documented Codex-native skill reads the isolated /codex-home/config.toml"
        if framework_id == "05":
            provider_injection = "DeepScientist official CodexRunner reads the isolated /codex-home/config.toml"
        adapters.append(
            {
                "framework_id": framework_id,
                "status": "pending",
                "native_entrypoint": entrypoint,
                "entrypoint_source": source,
                "fullrun_wrapper": wrapper,
                "runtime_image": image,
                "runtime_image_digest": None,
                "executor_kind": executor,
                "provider_injection": provider_injection,
                "provider_env": ["OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"],
                "native_log_marker": marker,
                "same_image_smoke": smoke,
                "prompt_sources": [wrapper],
                "prompt_audit": None,
                "admission_evidence": None,
                "blocker": None,
            }
        )
        legacy_frameworks.append(
            {
                "id": framework_id,
                "name": name,
                "run_dir": run_dirs[framework_id],
                "wrapper": wrapper,
                "validator": "tdc_admet_tox_fullrun",
                "required_paths": [source_prefixes[framework_id], "docs", "automation"],
                "required_images": [] if framework_id == "06" else [image],
            }
        )
    return {
        "spec_version": "1.0",
        "topic_id": "tdc_admet_tox",
        "evaluation_variant": variant,
        "model": model,
        "comparison_mode": "native_framework_orchestration",
        "frameworks": legacy_frameworks,
        "campaign": {
            "campaign_id": campaign_id,
            "comparison_mode": "synchronized_primary",
            "recovery_policy": "separate_campaign",
            "primary_attempt_policy": "one_fresh_attempt_per_framework",
            "freeze_manifest": f"real_eval/config/{campaign_id}.freeze.json",
            "framework_ids": [f"{i:02d}" for i in range(1, 8)],
            "experiment_budget": {"minimum": 2, "maximum": 4},
            "timeout_seconds": 7200,
            "fresh_run_root_required": True,
        },
        "topic_adapter": {
            "topic_id": "tdc_admet_tox",
            "contract_file": "automation/tdc_admet_tox_contract.md",
            "dataset_env": "TDC_ADMET_TOX_DATASET_ROOT",
            "framework_dataset_mount": "/data/tdc_admet_tox",
            "input_generator": "automation/scripts/generate_tdc_admet_tox_native_inputs.py",
            "official_scorer": "automation/scripts/run_tdc_admet_tox_host_score.py",
            "run_validator": "real_eval/scripts/validate_framework_run.py",
            "selection_score_policy": "framework_visible_validation_only",
            "official_score_owner": "host",
            "primary_metric": "macro_average_auroc",
            "required_trace_fields": ["framework_native_execution", "consumed_topic_input", "workspace_trace_root", "framework_internal_model", "framework_internal_api_base_url", "experiments", "selected_experiment_id", "idea_artifact", "idea_locked_before_experiments"],
            "required_framework_artifacts": ["research_idea.json", "experiment_trace.json", "final_report.md"],
            "official_score_artifact": "score.json",
            "host_only_inputs": ["TDC_ADMET_TOX_HIDDEN_LABELS_ROOT"],
            "framework_visible_inputs": ["dataset", "contract", "input_manifest", "validation_scorer"],
            "shared_prompt_sources": ["automation/tdc_admet_tox_contract.md", "automation/scripts/generate_tdc_admet_tox_native_inputs.py"],
        },
        "model_adapter": {
            "variant": variant,
            "model_id": model,
            "provider_config": provider_config,
            "wire_protocol": wire_protocol,
            "container_base_url": container_base_url,
            "required_env": ["OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"],
            "relay_preflight": "real_eval/scripts/preflight_seven_serial_tdc_admet_tox.py",
            "public_provider_forbidden": True,
            "effective_model_evidence_required": True,
            "runtime_policy": {"compact_experiment_ledger_required": True, "runtime_package_install_forbidden": True, "remote_request_budget": None, "minimum_batch_size": None},
        },
        "ownership": {
            "framework_responsibilities": ["planning", "experiment_design", "experiment_execution", "comparison", "selection", "analysis", "final_artifact_delivery"],
            "host_responsibilities": ["input_projection", "lifecycle_management", "official_scoring", "output_validation", "packaging"],
            "host_artifact_backfill_forbidden": True,
        },
        "ideation_policy": {
            "framework_owns_method_choice": True,
            "host_method_prescription_forbidden": True,
            "prescribed_methods": [],
            "idea_artifact": "research_idea.json",
            "idea_locked_before_experiments": True,
            "allowed_host_constraints": ["topic_question", "data_visibility", "train_validation_split", "official_metric", "compute_budget", "wall_clock_budget", "request_budget", "experiment_count_range", "available_dependencies", "network_policy", "safety_policy", "output_schema"],
            "forbidden_host_constraints": ["algorithm_family", "feature_representation", "model_architecture", "hyperparameters", "experiment_sequence", "selected_method"],
        },
        "workspace_policy": {"runtime_workspace": "/workspace", "fresh_physical_workspace_required": True, "dataset_read_only": True, "contract_read_only": True, "repository_root_writable_mount_forbidden": True},
        "framework_adapters": adapters,
        "reporting": {"outcome_dimensions": ["native_compliance", "research_completed", "scored", "contract_complete", "engineering_complete"], "result_views": ["synchronized_primary", "best_completed_native"], "missing_score_value": "N/A", "separate_model_tables": True, "recovery_runs_labeled": True, "idea_evaluation": {"enabled": True, "artifact": "research_idea.json", "blind_to_framework_identity": True, "judge_sees_experiment_results": False, "separate_from_task_score": True, "dimensions": ["novelty", "hypothesis_clarity", "technical_soundness", "feasibility", "experimental_discrimination"]}},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--variant", default="gpt")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--provider-config", default="api/codex_gpt54_shubiaobiao.toml")
    parser.add_argument("--container-base-url", default="https://dts.deepexi.com")
    parser.add_argument("--wire-protocol", default="responses")
    parser.add_argument(
        "--smoke-runner",
        default="real_eval/scripts/run_seven_serial_tdc_admet_tox_gpt_smoke.sh",
    )
    args = parser.parse_args()
    spec = build(
        args.campaign_id,
        variant=args.variant,
        model=args.model,
        provider_config=args.provider_config,
        container_base_url=args.container_base_url,
        wire_protocol=args.wire_protocol,
        smoke_runner=args.smoke_runner,
    )
    args.output.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

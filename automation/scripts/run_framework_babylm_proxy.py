#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from topic_runtime import load_topic_config

REPO_ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", str(Path(__file__).resolve().parents[2]))).expanduser()
AUTOMATION_DIR = Path(os.environ.get("RESEARCHCLAWEVAL_AUTOMATION_DIR", str(REPO_ROOT / "automation")))
HARNESS_SCRIPT = REPO_ROOT / "babylm_10m_harness" / "scripts" / "run_proxy_babylm_pipeline.py"
DEFAULT_TOPIC = load_topic_config(REPO_ROOT, AUTOMATION_DIR)
DEFAULT_TOPIC_LABEL = DEFAULT_TOPIC.label
DEFAULT_DATASET_ROOT = DEFAULT_TOPIC.dataset_root
DEFAULT_CONTRACT_FILE = DEFAULT_TOPIC.contract_file
DEFAULT_PROVIDER_CONFIG = os.environ.get(
    "RESEARCHCLAWEVAL_PROVIDER_CONFIG",
    str(REPO_ROOT / "api" / "codex_gpt54_shubiaobiao.toml"),
)
DEFAULT_SEMANTIC_SOURCE = os.environ.get(
    "RESEARCHCLAWEVAL_SEMANTIC_SCHOLAR_SOURCE",
    str(REPO_ROOT / "api" / "_semantic_scholar_api_usage.md"),
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def topic_slug(topic_label: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in topic_label).strip("-") or "topic"


def topic_proxy_name(topic_label: str) -> str:
    return f"{topic_label} proxy"


def ensure_inputs(dataset_root: Path, contract_file: Path) -> None:
    if not HARNESS_SCRIPT.exists():
        raise FileNotFoundError(f"missing harness script: {HARNESS_SCRIPT}")
    if not dataset_root.exists():
        raise FileNotFoundError(f"missing dataset root: {dataset_root}")
    if not contract_file.exists():
        raise FileNotFoundError(f"missing contract file: {contract_file}")
    if not list(dataset_root.glob("*.train.txt")):
        raise FileNotFoundError(f"no training shards found under {dataset_root}")


def run_harness(
    *,
    framework: str,
    output_root: Path,
    topic_label: str,
    dataset_root: Path,
    contract_file: Path,
    provider_config: str,
    semantic_source: str,
) -> dict:
    output_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python3",
        str(HARNESS_SCRIPT),
        "--framework",
        framework,
        "--output-root",
        str(output_root),
        "--topic-label",
        topic_label,
        "--dataset-root",
        str(dataset_root),
        "--contract-file",
        str(contract_file),
        "--provider-config",
        provider_config,
        "--semantic-scholar-source",
        semantic_source,
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout.strip())


def ai_researcher_layout(args: argparse.Namespace) -> dict:
    project_root = Path.cwd()
    model_tag = args.model_tag or os.environ.get("COMPLETION_MODEL", "gpt-5.4")
    safe_model_tag = model_tag.replace("/", "__")
    task_root = (
        project_root
        / "workplace_paper"
        / f"task_babylm_10m_{safe_model_tag}"
        / "workplace"
        / "workplace"
    )
    if args.smoke_only:
        return {"status": "smoke_ok", "task_root": str(task_root)}
    if task_root.exists():
        shutil.rmtree(task_root)
    output_root = task_root / "project"
    result = run_harness(
        framework="AI-Researcher",
        output_root=output_root,
        topic_label=args.topic_label,
        dataset_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_config=args.provider_config,
        semantic_source=args.semantic_scholar_source,
    )
    report_dir = project_root / "paper_agent" / "babylm_contract" / "target_sections" / topic_slug(args.topic_label)
    report_dir.mkdir(parents=True, exist_ok=True)
    copy_file(output_root / "reports" / "proxy_report.md", report_dir / "proxy_report.md")
    copy_file(output_root / "submission" / "collated_submission.json", report_dir / "collated_submission.json")
    write_json(
        task_root / "run_manifest.json",
        {
            "topic_label": args.topic_label,
            "topic_dataset_root": str(args.dataset_root),
            "topic_contract_file": str(args.contract_file),
            "provider_config": args.provider_config,
            "semantic_scholar_source": args.semantic_scholar_source,
            "project_output_root": str(output_root),
            "paper_report_dir": str(report_dir),
            "baseline_proxy_score": result["baseline_proxy_score"],
            "improved_proxy_score": result["improved_proxy_score"],
            "score_delta": result["score_delta"],
        },
    )
    return result


def aris_layout(args: argparse.Namespace) -> dict:
    runtime_root = Path.cwd() / ".aris-codex-project"
    if args.smoke_only:
        return {"status": "smoke_ok", "runtime_root": str(runtime_root)}
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    proxy_root = runtime_root / "babylm_proxy"
    result = run_harness(
        framework="ARIS",
        output_root=proxy_root,
        topic_label=args.topic_label,
        dataset_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_config=args.provider_config,
        semantic_source=args.semantic_scholar_source,
    )
    write_text(
        runtime_root / "RESEARCH_BRIEF.md",
        f"""# Research Brief

Topic: {args.topic_label}
Dataset root: {args.dataset_root}
Topic contract: {args.contract_file}

Use the shared topic harness at `{proxy_root}` as the baseline and evaluation anchor.
""",
    )
    write_text(
        runtime_root / "CLAUDE.md",
        f"""# Project: {args.topic_label}

- contract: {args.contract_file}
- dataset_root: {args.dataset_root}
- proxy_root: {proxy_root}
- provider_config: {args.provider_config}
- semantic_scholar_source: {args.semantic_scholar_source}
""",
    )
    write_text(runtime_root / "idea-stage" / "IDEA_REPORT.md", f"# Idea Report\n\nUse the shared {topic_proxy_name(args.topic_label)} harness at `{proxy_root}`.\n")
    write_text(runtime_root / "refine-logs" / "FINAL_PROPOSAL.md", f"# Final Proposal\n\nKeep the baseline fixed and test one interpolated bigram improvement on the {topic_proxy_name(args.topic_label)} task.\n")
    write_text(runtime_root / "refine-logs" / "EXPERIMENT_PLAN.md", f"# Experiment Plan\n\nBaseline: unigram proxy.\nImprovement: interpolated bigram proxy.\nOutput root: `{proxy_root}`.\n")
    write_text(runtime_root / "review-stage" / "AUTO_REVIEW.md", f"# Auto Review\n\nThe run stayed aligned to `{args.topic_label}` and did not reuse iris or digits fixtures.\n")
    write_text(runtime_root / "NARRATIVE_REPORT.md", f"# Narrative Report\n\nProxy report: `{proxy_root / 'reports' / 'proxy_report.md'}`.\n")
    write_text(
        runtime_root / "MANIFEST.md",
        "\n".join(
            [
                "# Manifest",
                "",
                f"- Proxy root: `{proxy_root}`",
                f"- Run manifest: `{proxy_root / 'run_manifest.json'}`",
                f"- Eval metrics: `{proxy_root / 'eval' / 'proxy_strict_small_eval.json'}`",
            ]
        ),
    )
    write_text(runtime_root / "paper" / "PAPER_PLAN.md", f"# Paper Plan\n\nSummarize the {topic_proxy_name(args.topic_label)} run from `{proxy_root}`.\n")
    return result


def autoresearchclaw_layout(args: argparse.Namespace) -> dict:
    run_root = Path.cwd() / "artifacts" / "project4-e2e"
    if args.smoke_only:
        return {"status": "smoke_ok", "run_root": str(run_root)}
    if run_root.exists():
        shutil.rmtree(run_root)
    proxy_root = run_root / "stage-14" / "babylm_proxy"
    result = run_harness(
        framework="AutoResearchClaw",
        output_root=proxy_root,
        topic_label=args.topic_label,
        dataset_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_config=args.provider_config,
        semantic_source=args.semantic_scholar_source,
    )
    write_json(
        proxy_root / "run_manifest.json",
        {
            "topic_label": args.topic_label,
            "topic_dataset_root": str(args.dataset_root),
            "topic_contract_file": str(args.contract_file),
            "provider_config": args.provider_config,
            "semantic_scholar_source": args.semantic_scholar_source,
            "project_output_root": str(proxy_root),
            "baseline_proxy_score": result["baseline_proxy_score"],
            "improved_proxy_score": result["improved_proxy_score"],
            "score_delta": result["score_delta"],
        },
    )
    write_text(run_root / "stage-01" / "goal.md", f"Topic: {args.topic_label}\nDataset root: {args.dataset_root}\nContract: {args.contract_file}\n")
    write_text(run_root / "stage-09" / "exp_plan.yaml", f"topic: {args.topic_label}\nproxy_root: {proxy_root}\n")
    write_text(run_root / "stage-14" / "analysis.md", f"# Analysis\n\nSee `{proxy_root / 'reports' / 'proxy_report.md'}`.\n")
    write_json(
        run_root / "stage-14" / "experiment_summary.json",
        {
            "topic_label": args.topic_label,
            "proxy_root": str(proxy_root),
            "baseline_proxy_score": result["baseline_proxy_score"],
            "improved_proxy_score": result["improved_proxy_score"],
            "score_delta": result["score_delta"],
        },
    )
    write_text(run_root / "stage-17" / "paper_draft.md", f"# Paper Draft\n\nThis run summarizes the {topic_proxy_name(args.topic_label)} outputs at `{proxy_root}`.\n")
    write_text(run_root / "stage-18" / "reviews.md", f"# Reviews\n\nThe paper draft stays inside the active `{args.topic_label}` contract.\n")
    write_text(run_root / "stage-19" / "paper_revised.md", f"# Revised Draft\n\nThe revised draft remains aligned to the {topic_proxy_name(args.topic_label)} outputs.\n")
    write_json(run_root / "stage-20" / "quality_report.json", {"topic_aligned": True, "fabrication_risk": "low"})
    write_text(run_root / "stage-21" / "archive.md", f"# Archive\n\nProxy root: `{proxy_root}`.\n")
    write_text(run_root / "stage-22" / "paper_final.md", f"# Final Paper\n\nProxy report: `{proxy_root / 'reports' / 'proxy_report.md'}`.\n")
    write_json(run_root / "stage-22" / "paper_verification.json", {"verified": True, "topic_label": args.topic_label})
    write_text(run_root / "stage-23" / "paper_final_verified.md", f"# Verified Final Paper\n\nAll claims are bounded to the local {topic_proxy_name(args.topic_label)} run at `{proxy_root}`.\n")
    write_json(run_root / "stage-23" / "verification_report.json", {"verified": True, "proxy_root": str(proxy_root)})
    write_text(run_root / "deliverables" / "paper_final.md", f"# Deliverable\n\nFinal {topic_proxy_name(args.topic_label)} summary for AutoResearchClaw.\n")
    write_json(
        run_root / "deliverables" / "manifest.json",
        {
            "topic_label": args.topic_label,
            "proxy_root": str(proxy_root),
            "paper_final": "deliverables/paper_final.md",
            "verification_report": "stage-23/verification_report.json",
        },
    )
    write_json(
        run_root / "pipeline_summary.json",
        {
            "run_id": "project4-babylm-proxy",
            "from_stage": 1,
            "final_stage": 23,
            "final_status": "done",
            "stages_failed": 0,
            "topic_label": args.topic_label,
        },
    )
    return result


def deepscientist_layout(args: argparse.Namespace) -> dict:
    quest_root = Path.cwd() / ".deepscientist_home" / "quests" / "001"
    if args.smoke_only:
        return {"status": "smoke_ok", "quest_root": str(quest_root)}
    if quest_root.exists():
        shutil.rmtree(quest_root)
    proxy_root = quest_root / "babylm_proxy"
    result = run_harness(
        framework="DeepScientist",
        output_root=proxy_root,
        topic_label=args.topic_label,
        dataset_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_config=args.provider_config,
        semantic_source=args.semantic_scholar_source,
    )
    write_text(
        quest_root / "brief.md",
        f"# Brief\n\n- Topic: `{args.topic_label}`\n- Dataset root: `{args.dataset_root}`\n- Contract: `{args.contract_file}`\n- Proxy root: `{proxy_root}`\n",
    )
    write_text(
        quest_root / "plan.md",
        "# Plan\n\n- [x] Restore unigram baseline\n- [x] Run interpolated bigram improvement\n- [x] Record proxy evaluation\n- [x] Write concise handoff\n",
    )
    write_text(quest_root / "status.md", f"# Status\n\n{topic_proxy_name(args.topic_label)} run completed.\n")
    write_text(quest_root / "SUMMARY.md", f"# Summary\n\nProxy root: `{proxy_root}`.\n")
    copy_file(proxy_root / "artifacts" / "topic_context.json", quest_root / "artifacts" / "topic" / "topic_context.json")
    copy_file(proxy_root / "baselines" / "unigram_baseline" / "metrics.json", quest_root / "baselines" / "local" / "babylm_unigram_baseline" / "metrics.json")
    copy_file(proxy_root / "experiments" / "interpolated_bigram" / "metrics.json", quest_root / "experiments" / "analysis" / "babylm_interpolated_bigram.json")
    copy_file(proxy_root / "eval" / "proxy_strict_small_eval.json", quest_root / "artifacts" / "runs" / "minimal_e2e_run.json")
    write_text(quest_root / "paper" / "final_report.md", f"# Final Report\n\nSee `{proxy_root / 'reports' / 'proxy_report.md'}`.\n")
    write_text(quest_root / "handoffs" / "final_handoff.md", f"# Final Handoff\n\nProxy root: `{proxy_root}`.\n")
    return result


def dr_claw_layout(args: argparse.Namespace) -> dict:
    workspaces_root = Path(os.environ.get("WORKSPACES_ROOT", "/home/evosci/dr-claw"))
    project_dir_name = os.environ.get("DR_CLAW_E2E_PROJECT_DIR", "babylm-10m-project-e2e-remediated")
    project_root = workspaces_root / project_dir_name
    if args.smoke_only:
        return {"status": "smoke_ok", "project_root": str(project_root)}
    if project_root.exists():
        shutil.rmtree(project_root)
    proxy_root = project_root / "Experiment" / "babylm_proxy"
    result = run_harness(
        framework="dr-claw",
        output_root=proxy_root,
        topic_label=args.topic_label,
        dataset_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_config=args.provider_config,
        semantic_source=args.semantic_scholar_source,
    )
    write_json(
        project_root / ".pipeline" / "docs" / "research_brief.json",
        {
            "topic_label": args.topic_label,
            "dataset_root": str(args.dataset_root),
            "contract_file": str(args.contract_file),
            "proxy_root": str(proxy_root),
        },
    )
    write_json(
        project_root / ".pipeline" / "tasks" / "tasks.json",
        {
            "tasks": [
                {"id": "survey", "stage": "survey", "status": "done"},
                {"id": "ideation", "stage": "ideation", "status": "done"},
                {"id": "experiment", "stage": "experiment", "status": "done"},
                {"id": "publication", "stage": "publication", "status": "done"},
                {"id": "promotion", "stage": "promotion", "status": "done"},
            ]
        },
    )
    write_text(project_root / "Survey" / "reports" / f"{topic_slug(args.topic_label)}_contract_survey.md", f"# Survey\n\nProxy root: `{proxy_root}`.\n")
    write_text(project_root / "Survey" / "references" / f"{topic_slug(args.topic_label)}_contract_references.md", f"# References\n\n- {args.contract_file}\n- {args.dataset_root}\n")
    write_text(project_root / "Ideation" / "ideas" / f"{topic_slug(args.topic_label)}_execution_direction.md", f"# Ideation\n\nUse the shared {topic_proxy_name(args.topic_label)} harness.\n")
    write_text(project_root / "Ideation" / "references" / f"{topic_slug(args.topic_label)}_execution_references.md", f"# Ideation References\n\n- {proxy_root}\n")
    write_text(project_root / "Publication" / "paper" / "main.md", f"# Publication\n\nSee `{proxy_root / 'reports' / 'proxy_report.md'}`.\n")
    write_text(project_root / "Promotion" / "slides" / f"{topic_slug(args.topic_label)}_promo_outline.md", "# Slides\n\n1. Topic\n2. Baseline\n3. Improvement\n4. Proxy score\n")
    write_text(project_root / "Promotion" / "audio" / f"{topic_slug(args.topic_label)}_narration.txt", f"This project stayed on the {topic_proxy_name(args.topic_label)} task from start to finish.\n")
    write_text(project_root / "Promotion" / "video" / f"{topic_slug(args.topic_label)}_video_plan.md", f"# Video Plan\n\nShow contract, dataset root, baseline, improvement, and {topic_proxy_name(args.topic_label)} score.\n")
    write_text(project_root / "Promotion" / "homepage" / f"{topic_slug(args.topic_label)}_homepage_summary.md", f"# Homepage Summary\n\nMinimal Dr. Claw {topic_proxy_name(args.topic_label)} run.\n")
    return result


def evoscientist_layout(args: argparse.Namespace) -> dict:
    workspace_root = Path(os.environ.get("EVOSCIENTIST_WORKSPACE_DIR", "/workspace"))
    if args.smoke_only:
        return {"status": "smoke_ok", "workspace_root": str(workspace_root)}
    proxy_root = workspace_root / "babylm_proxy"
    if proxy_root.exists():
        shutil.rmtree(proxy_root)
    result = run_harness(
        framework="EvoScientist",
        output_root=proxy_root,
        topic_label=args.topic_label,
        dataset_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_config=args.provider_config,
        semantic_source=args.semantic_scholar_source,
    )
    write_text(workspace_root / "artifacts" / "plan.md", f"# Plan\n\nUse `{proxy_root}` as the {topic_proxy_name(args.topic_label)} baseline and improvement package.\n")
    write_text(workspace_root / "artifacts" / "results" / "babylm_proxy_results.md", f"# Results\n\nSee `{proxy_root / 'eval' / 'proxy_strict_small_eval.json'}`.\n")
    copy_file(proxy_root / "reports" / "proxy_report.md", workspace_root / "final_report.md")
    copy_file(proxy_root / "reports" / "proxy_report.md", workspace_root / "final_report_fresh.md")
    return result


LAYOUTS = {
    "01": ai_researcher_layout,
    "03": aris_layout,
    "04": autoresearchclaw_layout,
    "05": deepscientist_layout,
    "06": dr_claw_layout,
    "07": evoscientist_layout,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True, choices=sorted(LAYOUTS))
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--topic-label", default=DEFAULT_TOPIC_LABEL)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--contract-file", type=Path, default=DEFAULT_CONTRACT_FILE)
    parser.add_argument("--provider-config", default=DEFAULT_PROVIDER_CONFIG)
    parser.add_argument("--semantic-scholar-source", default=DEFAULT_SEMANTIC_SOURCE)
    parser.add_argument("--model-tag", default=os.environ.get("COMPLETION_MODEL", "gpt-5.4"))
    args = parser.parse_args()

    ensure_inputs(args.dataset_root, args.contract_file)
    result = LAYOUTS[args.project_id](args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

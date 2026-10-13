#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class ValidationResult:
    status: str
    summary: str
    evidence: dict
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return self.status in {
            "finished",
            "finished_degraded",
            "unsupported_native_entrypoint",
            "blocked_benchmark_authorization",
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def glob_any(root: Path, patterns: Iterable[str]) -> list[Path]:
    hits: list[Path] = []
    for pattern in patterns:
        hits.extend(sorted(root.glob(pattern)))
    seen = set()
    uniq = []
    for path in hits:
        if path not in seen and path.exists():
            seen.add(path)
            uniq.append(path)
    return uniq


def pick_latest(paths: Iterable[Path]) -> Path | None:
    paths = [p for p in paths if p.exists()]
    if not paths:
        return None
    return max(paths, key=lambda p: p.stat().st_mtime)


def file_contains(path: Path, needles: Iterable[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return all(needle in text for needle in needles)


GAVE2_METRIC_KEYS = ("vessel_dice", "av_macro_f1", "official_composite_score")


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def metric_triplet(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    if not all(is_number(data.get(key)) for key in GAVE2_METRIC_KEYS):
        return None
    return {key: float(data[key]) for key in GAVE2_METRIC_KEYS}


def find_gave2_models(data: object) -> dict[str, dict]:
    models: dict[str, dict] = {}

    if isinstance(data, dict):
        direct_metrics = metric_triplet(data.get("best_val")) or metric_triplet(data)
        if direct_metrics is not None and isinstance(data.get("name"), str):
            models[data["name"]] = direct_metrics
            return models

        captured_model_ids: set[int] = set()
        for fallback_name, value in data.items():
            if not isinstance(value, dict):
                continue
            metrics = metric_triplet(value.get("best_val"))
            if metrics is None and isinstance(value.get("name"), str):
                metrics = metric_triplet(value)
            if metrics is None:
                continue
            model_name = (
                value.get("name") if isinstance(value.get("name"), str) else str(fallback_name)
            )
            models[model_name] = metrics
            captured_model_ids.add(id(value))

        for value in data.values():
            if id(value) in captured_model_ids:
                continue
            if isinstance(value, (dict, list)):
                for name, metrics in find_gave2_models(value).items():
                    models.setdefault(name, metrics)
    elif isinstance(data, list):
        for idx, value in enumerate(data):
            if not isinstance(value, (dict, list)):
                continue
            for name, metrics in find_gave2_models(value).items():
                models.setdefault(name if name else f"model_{idx}", metrics)

    return models


def gave2_metric_json_candidates(root: Path) -> list[Path]:
    workspace = root / "workspace"
    if not workspace.exists():
        return []

    candidates: list[Path] = []
    skip_dirs = {
        ".git",
        ".nv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "site-packages",
        "dist-packages",
    }
    for dirpath, dirnames, filenames in os.walk(workspace, topdown=True, onerror=lambda _exc: None):
        dirnames[:] = [
            name for name in dirnames if name not in skip_dirs and not name.startswith(".")
        ]
        path = Path(dirpath)
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            lower = filename.lower()
            if not (
                lower.startswith("results")
                or lower.endswith("summary.json")
                or lower in {"metrics.json", "pipeline_summary.json"}
            ):
                continue
            candidates.append(path / filename)
    return sorted(candidates, key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)


def extract_gave2_metrics(root: Path) -> dict | None:
    for path in gave2_metric_json_candidates(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        models = find_gave2_models(data)
        if not models:
            continue
        best_model = max(
            models,
            key=lambda name: models[name].get("official_composite_score", float("-inf")),
        )
        return {
            "source": rel(path, root),
            "best_model": best_model,
            "best_official_composite_score": models[best_model]["official_composite_score"],
            "models": models,
        }
    return None


def json_device_values(root: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for path in root.rglob("*.json"):
        try:
            parts = path.relative_to(root).parts
        except Exception:
            parts = path.parts
        if any(part.startswith(".") for part in parts):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    if key.lower() == "device" and isinstance(value, str):
                        pairs.append((rel(path, root), value.lower()))
                    elif isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(v for v in item if isinstance(v, (dict, list)))
    return pairs


def has_cuda_evidence(root: Path) -> tuple[bool, list[tuple[str, str]]]:
    pairs = json_device_values(root)
    if any(value.startswith("cuda") for _, value in pairs):
        return True, pairs
    txt_hits = []
    for name in [
        "artifacts/logs/ngc_preflight.txt",
        "artifacts/logs/env_check.txt",
        "artifacts/logs/completed.txt",
        "logs/e2e.log",
    ]:
        p = root / name
        if p.exists():
            txt_hits.append(p)
    for path in txt_hits:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        if "device=cuda" in text or "device: cuda" in text or "cuda_available: true" in text:
            return True, pairs
    return False, pairs


def first_rel(paths: list[Path], root: Path) -> str | None:
    return rel(paths[0], root) if paths else None


def validate_ai_researcher_resume(root: Path) -> ValidationResult:
    paper_dir = root / "repo/research_agent/babylm/target_sections/babylm_10m"
    eval_json = glob_any(root, ["repo/**/pace_eval.json", "repo/**/*eval*.json"])
    report_md = glob_any(
        root, ["repo/**/main.md", "repo/**/final_report.md", "repo/**/*report*.md"]
    )
    evidence = {
        "paper_dir": rel(paper_dir, root) if paper_dir.exists() else None,
        "eval_json": first_rel(eval_json, root),
        "report": first_rel(report_md, root),
    }
    ok = paper_dir.exists() and bool(eval_json)
    if ok:
        return ValidationResult(
            "finished",
            "AI-Researcher resume produced paper sections and evaluation JSON.",
            evidence,
            [],
        )
    return ValidationResult(
        "failed_no_artifacts", "AI-Researcher resume evidence is incomplete.", evidence, []
    )


def validate_ai_researcher_real(root: Path) -> ValidationResult:
    result = validate_ai_researcher_resume(root)
    return ValidationResult(
        result.status,
        result.summary.replace("resume", "real"),
        result.evidence,
        result.warnings,
    )


def validate_ai_scientist_v2(root: Path) -> ValidationResult:
    repo = root / "repo"
    idea = repo / "ai_scientist/ideas/babylm_10m_strict_small_topic.json"
    exps = sorted([p for p in (repo / "experiments").glob("*_attempt_*") if p.is_dir()])
    exp = pick_latest(exps)
    summaries = []
    pdfs = []
    figures = []
    review_text = None
    review_json = None
    if exp is not None:
        summaries = glob_any(
            exp,
            [
                "logs/0-run/baseline_summary.json",
                "logs/0-run/ablation_summary.json",
                "logs/0-run/research_summary.json",
                "logs/0-run/draft_summary.json",
            ],
        )
        pdfs = glob_any(exp, ["*.pdf"])
        figures = glob_any(exp, ["figures/*.png", "figures/*.jpg"])
        rt = exp / "review_text.txt"
        rj = exp / "review_img_cap_ref.json"
        review_text = rt if rt.exists() else None
        review_json = rj if rj.exists() else None
    evidence = {
        "idea_json": rel(idea, root) if idea.exists() else None,
        "experiment_dir": rel(exp, root) if exp else None,
        "summary_files": [rel(p, root) for p in summaries],
        "pdf": first_rel(pdfs, root),
        "figure_count": len(figures),
        "review_text": rel(review_text, root) if review_text else None,
        "review_json": rel(review_json, root) if review_json else None,
    }
    if idea.exists() and exp and len(summaries) >= 2 and (pdfs or review_text):
        return ValidationResult(
            "finished",
            "AI-Scientist-v2 ideation, BFTS, and writeup/review artifacts are present.",
            evidence,
            [],
        )
    if idea.exists() and exp and len(summaries) >= 2:
        return ValidationResult(
            "finished_degraded",
            "AI-Scientist-v2 completed ideation and experiment summaries, but writeup/review artifacts are incomplete.",
            evidence,
            [],
        )
    return ValidationResult(
        "failed_no_artifacts",
        "AI-Scientist-v2 did not leave the expected idea and experiment evidence.",
        evidence,
        [],
    )


def validate_aris(root: Path) -> ValidationResult:
    final_report = glob_any(root, [
        "workspace/babylm_10m_harness/reports/final_report.md",
        "workspace/babylm_10m_harness/reports/report.md",
    ])
    checkpoints = glob_any(
        root,
        [
            "workspace/babylm_10m_harness/outputs/models/**/*.safetensors",
            "workspace/babylm_10m_harness/outputs/models/**/*.bin",
            "workspace/babylm_10m_harness/checkpoints/**/*.safetensors",
            "workspace/babylm_10m_harness/checkpoints/**/*.bin",
        ],
    )
    eval_json = glob_any(root, ["workspace/**/*eval*.json"])
    evidence = {
        "final_report": first_rel(final_report, root),
        "checkpoint": first_rel(checkpoints, root),
        "eval_json": first_rel(eval_json, root),
    }
    if final_report and checkpoints and eval_json:
        return ValidationResult(
            "finished",
            "ARIS produced the harness report, model checkpoint, and evaluation JSON.",
            evidence,
            [],
        )
    return ValidationResult("failed_no_artifacts", "ARIS evidence is incomplete.", evidence, [])


def validate_autoresearchclaw_resume(root: Path) -> ValidationResult:
    artifact_dirs = sorted(
        [p for p in (root / "repo/artifacts").glob("babylm-real-*") if p.is_dir()]
    )
    artifact_dir = pick_latest(artifact_dirs)
    deliverables = artifact_dir / "deliverables" if artifact_dir else None
    topic_eval = artifact_dir / "stage-02/topic_evaluation.json" if artifact_dir else None
    checkpoints = (
        glob_any(artifact_dir, ["**/*.pt", "**/*.pth", "**/*.safetensors", "**/pytorch_model.bin"])
        if artifact_dir
        else []
    )
    evidence = {
        "artifact_dir": rel(artifact_dir, root) if artifact_dir else None,
        "deliverables": rel(deliverables, root) if deliverables and deliverables.exists() else None,
        "topic_evaluation": rel(topic_eval, root) if topic_eval and topic_eval.exists() else None,
        "checkpoint": first_rel(checkpoints, root),
    }
    if (
        artifact_dir
        and deliverables
        and deliverables.exists()
        and topic_eval
        and topic_eval.exists()
    ):
        status = "finished" if checkpoints else "finished_degraded"
        summary = "AutoResearchClaw packaged deliverables and evaluation artifacts."
        if status == "finished_degraded":
            summary = "AutoResearchClaw packaged deliverables and evaluation artifacts, but no checkpoint file was found under the artifact bundle."
        return ValidationResult(status, summary, evidence, [])
    return ValidationResult(
        "failed_no_artifacts", "AutoResearchClaw resume artifacts are incomplete.", evidence, []
    )


def validate_autoresearchclaw_babylm_fullrun(root: Path) -> ValidationResult:
    run_id = root.parent.name
    workspace = root / "workspace"
    artifact_dir = workspace / "artifacts" / f"babylm-{run_id}"
    deliverables = artifact_dir / "deliverables"
    required_names = (
        "research_idea.json",
        "experiment_trace.json",
        "final_report.md",
    )
    artifact_files = [deliverables / name for name in required_names]
    handoff_files = [workspace / name for name in required_names]
    artifact_complete = (
        artifact_dir.is_dir()
        and not artifact_dir.is_symlink()
        and deliverables.is_dir()
        and not deliverables.is_symlink()
        and all(path.is_file() and not path.is_symlink() for path in artifact_files)
    )
    handoff_complete = all(
        path.is_file() and not path.is_symlink() for path in handoff_files
    )
    handoff_matches_deliverables = artifact_complete and handoff_complete and all(
        artifact.read_bytes() == handoff.read_bytes()
        for artifact, handoff in zip(artifact_files, handoff_files, strict=True)
    )
    evidence = {
        "run_id": run_id,
        "artifact_dir": rel(artifact_dir, root) if artifact_dir.is_dir() else None,
        "deliverables": rel(deliverables, root) if deliverables.is_dir() else None,
        "deliverable_files": [
            rel(path, root) for path in artifact_files if path.is_file()
        ],
        "handoff_files": [
            rel(path, root) for path in handoff_files if path.is_file()
        ],
        "handoff_matches_deliverables": handoff_matches_deliverables,
    }
    if handoff_matches_deliverables:
        return ValidationResult(
            "finished",
            "AutoResearchClaw current BabyLM full-run artifacts and handoff are complete.",
            evidence,
            [],
        )
    return ValidationResult(
        "failed_no_artifacts",
        "AutoResearchClaw current BabyLM full-run artifacts or handoff are incomplete.",
        evidence,
        [],
    )


def validate_deepscientist(root: Path) -> ValidationResult:
    report_md = glob_any(root, ["workspace/final_report.md"])
    checkpoints = glob_any(
        root,
        [
            "workspace/artifacts/checkpoints/**/*.pt",
            "workspace/artifacts/checkpoints/**/*.pth",
            "workspace/artifacts/checkpoints/**/*.safetensors",
        ],
    )
    eval_json = glob_any(
        root, ["workspace/artifacts/eval/*.json", "workspace/artifacts/eval/**/*.json"]
    )
    evidence = {
        "final_report": first_rel(report_md, root),
        "checkpoint": first_rel(checkpoints, root),
        "eval_json": first_rel(eval_json, root),
    }
    if report_md and checkpoints and eval_json:
        return ValidationResult(
            "finished",
            "DeepScientist produced checkpoints, eval JSON, and final report.",
            evidence,
            [],
        )
    return ValidationResult(
        "failed_no_artifacts", "DeepScientist evidence is incomplete.", evidence, []
    )


def validate_drclaw(root: Path) -> ValidationResult:
    checkpoints = glob_any(
        root,
        [
            "home/dr-claw/**/outputs/checkpoints/**/*.safetensors",
            "home/dr-claw/**/outputs/checkpoints/**/*.pt",
            "home/dr-claw/**/outputs/checkpoints/**/*.bin",
        ],
    )
    eval_json = glob_any(root, ["home/dr-claw/**/outputs/eval/*.json"])
    train_history = glob_any(root, ["home/dr-claw/**/outputs/logs/train_history.jsonl"])
    report_md = glob_any(root, ["home/dr-claw/**/*final_report*.md", "home/dr-claw/**/*report*.md"])
    evidence = {
        "checkpoint": first_rel(checkpoints, root),
        "eval_json": first_rel(eval_json, root),
        "train_history": first_rel(train_history, root),
        "report": first_rel(report_md, root),
    }
    if checkpoints and eval_json and train_history:
        status = "finished" if report_md else "finished_degraded"
        summary = "Dr. Claw produced real training checkpoints, eval JSON, and training history."
        if status == "finished_degraded":
            summary = "Dr. Claw produced real training checkpoints, eval JSON, and training history, but no final publication report was found."
        return ValidationResult(status, summary, evidence, [])
    return ValidationResult("failed_no_artifacts", "Dr. Claw evidence is incomplete.", evidence, [])


def validate_evoscientist(root: Path) -> ValidationResult:
    candidate_roots = []
    for sub in [
        root / "phase2/workspace",
        root / "workspace",
        root / "07_evoscientist_real_babylm_ngc_current_acceleratefix/workspace",
    ]:
        if sub.exists():
            candidate_roots.append(sub)
    candidate = candidate_roots[0] if candidate_roots else root
    report_md = glob_any(candidate, ["final_report.md"])
    checkpoints = glob_any(
        candidate,
        [
            "artifacts/checkpoints/**/*.safetensors",
            "artifacts/checkpoints/**/*.pt",
            "artifacts/checkpoints/**/*.bin",
        ],
    )
    eval_json = glob_any(
        candidate, ["artifacts/eval/*.json", "artifacts/eval/**/*.json", "artifacts/*eval*.json"]
    )
    model_stats = glob_any(candidate, ["artifacts/logs/model_stats.json"])
    cuda_ok, device_pairs = has_cuda_evidence(candidate)
    evidence = {
        "candidate_root": rel(candidate, root),
        "final_report": first_rel(report_md, root),
        "checkpoint": first_rel(checkpoints, root),
        "eval_json": first_rel(eval_json, root),
        "model_stats": first_rel(model_stats, root),
        "device_values": [{"path": p, "device": d} for p, d in device_pairs],
    }
    if report_md and checkpoints and eval_json and model_stats and cuda_ok:
        return ValidationResult(
            "finished",
            "EvoScientist produced CUDA-backed checkpoints, eval JSON, model stats, and final report.",
            evidence,
            [],
        )
    if report_md and checkpoints and eval_json and model_stats:
        return ValidationResult(
            "failed_no_artifacts",
            "EvoScientist produced files but CUDA device evidence is missing, so the run is invalid for this task.",
            evidence,
            [],
        )
    return ValidationResult(
        "failed_no_artifacts", "EvoScientist evidence is incomplete.", evidence, []
    )


def validate_gave2_input_pack(root: Path) -> ValidationResult:
    manifest_path = root / "native_pack_manifest.json"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "copied_inputs": [],
        "framework": None,
    }
    if not manifest_path.exists():
        return ValidationResult(
            "failed_no_artifacts", "GAVE2 native input pack manifest is missing.", evidence, []
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence["parse_error"] = str(exc)
        return ValidationResult(
            "failed_no_artifacts", "GAVE2 native input pack manifest is unreadable.", evidence, []
        )

    copied = manifest.get("copied_inputs", [])
    missing = [rel_path for rel_path in copied if not (root / rel_path).exists()]
    evidence["copied_inputs"] = copied
    evidence["framework"] = manifest.get("framework")
    evidence["dataset_root"] = manifest.get("dataset_root")
    evidence["contract_file"] = manifest.get("contract_file")
    if missing:
        evidence["missing_inputs"] = missing
        return ValidationResult(
            "failed_no_artifacts",
            "GAVE2 native input pack is missing copied input files.",
            evidence,
            [],
        )
    if not copied:
        return ValidationResult(
            "failed_no_artifacts",
            "GAVE2 native input pack did not record any copied inputs.",
            evidence,
            [],
        )
    return ValidationResult(
        "finished", "GAVE2 native input pack is prepared and validated.", evidence, []
    )


def validate_arc_wbe_2026_input_pack(root: Path) -> ValidationResult:
    manifest_path = root / "native_pack_manifest.json"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "copied_inputs": [],
        "framework": None,
    }
    if not manifest_path.exists():
        return ValidationResult(
            "failed_no_artifacts", "ARC native input pack manifest is missing.", evidence, []
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence["parse_error"] = str(exc)
        return ValidationResult(
            "failed_no_artifacts", "ARC native input pack manifest is unreadable.", evidence, []
        )

    copied = manifest.get("copied_inputs", [])
    missing = [rel_path for rel_path in copied if not (root / rel_path).exists()]
    evidence["copied_inputs"] = copied
    evidence["framework"] = manifest.get("framework")
    evidence["dataset_root"] = manifest.get("dataset_root")
    evidence["contract_file"] = manifest.get("contract_file")
    if missing:
        evidence["missing_inputs"] = missing
        return ValidationResult(
            "failed_no_artifacts", "ARC native input pack is missing copied input files.", evidence, []
        )
    if not copied:
        return ValidationResult(
            "failed_no_artifacts", "ARC native input pack did not record any copied inputs.", evidence, []
        )
    return ValidationResult(
        "finished", "ARC native input pack is prepared and validated.", evidence, []
    )


def validate_gave2_smoke(root: Path) -> ValidationResult:
    manifest_path = root / "smoke_manifest.json"
    log_path = root / "logs/smoke.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
        "checks": {},
    }
    if not manifest_path.exists():
        return ValidationResult(
            "failed_no_artifacts", "GAVE2 smoke manifest is missing.", evidence, []
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence["parse_error"] = str(exc)
        return ValidationResult(
            "failed_no_artifacts", "GAVE2 smoke manifest is unreadable.", evidence, []
        )

    checks = manifest.get("checks", {})
    evidence["framework"] = manifest.get("framework")
    evidence["image"] = manifest.get("image")
    evidence["checks"] = checks
    if not checks:
        return ValidationResult(
            "failed_no_artifacts", "GAVE2 smoke manifest did not record checks.", evidence, []
        )
    if not manifest.get("all_passed"):
        return ValidationResult(
            "failed_no_artifacts", "GAVE2 smoke checks did not all pass.", evidence, []
        )
    if not log_path.exists():
        return ValidationResult("failed_no_artifacts", "GAVE2 smoke log is missing.", evidence, [])
    return ValidationResult("finished", "GAVE2 smoke checks passed.", evidence, [])


def validate_arc_wbe_2026_smoke(root: Path) -> ValidationResult:
    manifest_path = root / "smoke_manifest.json"
    log_path = root / "logs/smoke.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
        "topic_evidence": None,
        "checks": {},
    }

    if not manifest_path.exists():
        return ValidationResult(
            "failed_no_artifacts", "ARC smoke manifest is missing.", evidence, []
        )
    if not log_path.exists():
        return ValidationResult("failed_no_artifacts", "ARC smoke log is missing.", evidence, [])

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence["parse_error"] = str(exc)
        return ValidationResult(
            "failed_no_artifacts", "ARC smoke manifest is unreadable.", evidence, []
        )

    evidence["checks"] = manifest.get("checks", {})
    evidence["framework"] = manifest.get("framework")
    evidence["dataset_root"] = manifest.get("dataset_root")
    evidence["contract_file"] = manifest.get("contract_file")
    evidence["manifest_topic_evidence"] = manifest.get("topic_evidence")
    if not evidence["checks"]:
        return ValidationResult(
            "failed_no_artifacts", "ARC smoke manifest did not record checks.", evidence, []
        )
    if not manifest.get("all_passed"):
        return ValidationResult(
            "failed_validation", "ARC smoke checks did not all pass.", evidence, []
        )

    topic_candidates = glob_any(
        root,
        [
            "repo/**/*ARC_WBE_2026*.md",
            "repo/**/*arc_wbe_2026*.json",
            "repo/**/topic.txt",
            "repo/**/config.arc.yaml",
            "workspace/**/*ARC_WBE_2026*.md",
            "workspace/**/*arc_wbe_2026*.json",
            "workspace/**/topic.txt",
            "workspace/**/config.arc.yaml",
            "inputs/**/*ARC_WBE_2026*.md",
            "inputs/**/*arc_wbe_2026*.json",
            "inputs/**/topic.txt",
            "inputs/**/config.arc.yaml",
        ],
    )

    accepted: list[Path] = []
    for path in topic_candidates:
        name = path.name.lower()
        if "arc_wbe_2026" in name:
            accepted.append(path)
            continue
        if name == "topic.txt" and file_contains(path, ["ARC-WBE-2026"]):
            accepted.append(path)
            continue
        if name == "config.arc.yaml" and file_contains(path, ["arc_wbe_2026", "ARC-WBE-2026"]):
            accepted.append(path)

    topic_evidence = pick_latest(accepted)
    if topic_evidence is None:
        return ValidationResult(
            "failed_validation",
            "ARC smoke did not leave topic-specific evidence.",
            evidence,
            ["missing_topic_evidence"],
        )

    evidence["topic_evidence"] = rel(topic_evidence, root)

    return ValidationResult("finished", "ARC smoke consumed the topic contract.", evidence, [])


def validate_gave2_fullrun(root: Path) -> ValidationResult:
    manifest_path = root / "fullrun_manifest.json"
    state_path = root / "state.json"
    log_path = root / "logs/e2e.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "state": rel(state_path, root) if state_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
    }
    if not manifest_path.exists() or not state_path.exists() or not log_path.exists():
        return ValidationResult(
            "failed_no_artifacts",
            "GAVE2 full-run wrapper did not leave manifest/state/log evidence.",
            evidence,
            [],
        )
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence["parse_error"] = str(exc)
        return ValidationResult(
            "failed_no_artifacts", "GAVE2 full-run state is unreadable.", evidence, []
        )
    status = state.get("status", "unknown")
    evidence["status"] = status
    evidence["summary"] = state.get("summary")
    metrics = extract_gave2_metrics(root)
    if metrics is not None:
        evidence["gave2_metrics"] = metrics
    if status in {"finished", "finished_degraded"}:
        return ValidationResult(
            status, "GAVE2 full-run wrapper finished and left state/log evidence.", evidence, []
        )
    if status == "blocked":
        return ValidationResult(
            "failed_no_artifacts",
            f"GAVE2 full-run wrapper is blocked: {state.get('summary', 'unknown blocker')}",
            evidence,
            [],
        )
    return ValidationResult(
        "failed_no_artifacts",
        f"GAVE2 full-run wrapper did not finish successfully (status={status}).",
        evidence,
        [],
    )


def read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_arc_score(root: Path) -> tuple[Path | None, dict | None]:
    candidates = [
        root / "workspace/score.json",
        root / "artifacts/score.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        if not is_number(data.get("score")) or not isinstance(data.get("score_source"), str):
            continue
        return path, data
    return None, None


OFFICIAL_ARC_SCORE_SOURCES = {
    "official_adapter_whest_run",
}


def arc_trace_integrity(
    trace: object,
    manifest: dict,
) -> tuple[bool, list[str], dict[str, object]]:
    failures: list[str] = []
    details: dict[str, object] = {}
    if not isinstance(trace, dict):
        return False, ["missing_or_unreadable_experiment_trace"], details

    details["framework_native_execution"] = trace.get("framework_native_execution")
    details["consumed_topic_input"] = trace.get("consumed_topic_input")
    details["workspace_trace_root"] = trace.get("workspace_trace_root")
    details["framework_internal_model"] = trace.get("framework_internal_model")
    details["framework_internal_api_base_url"] = trace.get("framework_internal_api_base_url")
    details["selected_experiment_id"] = trace.get("selected_experiment_id")

    if trace.get("framework_native_execution") is not True:
        failures.append("framework_native_execution_not_proven")
    if trace.get("consumed_topic_input") is not True:
        failures.append("topic_input_consumption_not_proven")
    if trace.get("workspace_trace_root") != "/workspace":
        failures.append("invalid_workspace_trace_root")

    experiments = trace.get("experiments")
    experiment_ids: list[str] = []
    if not isinstance(experiments, list) or not 2 <= len(experiments) <= 4:
        failures.append("experiment_count_outside_2_to_4")
    else:
        for row in experiments:
            experiment_id = row.get("experiment_id") or row.get("id") if isinstance(row, dict) else None
            if not isinstance(experiment_id, str) or not experiment_id.strip():
                failures.append("experiment_missing_id")
                continue
            experiment_ids.append(experiment_id.strip())
        if len(set(experiment_ids)) != len(experiment_ids):
            failures.append("duplicate_experiment_id")
    details["experiment_count"] = len(experiments) if isinstance(experiments, list) else 0
    details["experiment_ids"] = experiment_ids

    selected_id = trace.get("selected_experiment_id")
    if not isinstance(selected_id, str) or not selected_id.strip():
        failures.append("missing_selected_experiment_id")
    elif selected_id.strip() not in experiment_ids:
        failures.append("selected_experiment_not_in_trace")

    expected_model = manifest.get("evaluation_model")
    actual_model = trace.get("framework_internal_model")
    if not isinstance(expected_model, str) or not expected_model.strip():
        failures.append("manifest_missing_evaluation_model")
    elif actual_model != expected_model:
        failures.append("framework_internal_model_mismatch")

    expected_base_url = manifest.get("provider_base_url")
    actual_base_url = trace.get("framework_internal_api_base_url")
    for value, failure in (
        (actual_model, "unexpanded_framework_internal_model"),
        (actual_base_url, "unexpanded_framework_internal_api_base_url"),
    ):
        if isinstance(value, str) and re.search(r"\$\{?[A-Z_][A-Z0-9_]*\}?", value):
            failures.append(failure)
    if not isinstance(expected_base_url, str) or not expected_base_url.strip():
        failures.append("manifest_missing_provider_base_url")
    elif not isinstance(actual_base_url, str) or not actual_base_url.strip():
        failures.append("missing_framework_internal_api_base_url")
    elif actual_base_url.rstrip("/") != expected_base_url.rstrip("/"):
        failures.append("framework_internal_api_base_url_mismatch")

    if trace.get("idea_artifact") != "research_idea.json":
        failures.append("invalid_idea_artifact")
    if trace.get("idea_locked_before_experiments") is not True:
        failures.append("idea_lock_not_proven")
    return not failures, failures, details


def has_arc_native_execution_log_evidence(log_path: Path, manifest: dict | None = None) -> bool:
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if "arc_wbe_2026" not in text:
        return False
    if not isinstance(manifest, dict):
        return False
    if manifest.get("framework_orchestration") is not True:
        return False
    for key in ("native_entrypoint", "kimi_injection", "native_log_marker"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return manifest["native_log_marker"] in text and manifest["native_entrypoint"] in text


def arc_report_looks_on_topic(report_path: Path) -> bool:
    try:
        text = report_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    lower = text.lower()
    if "arc-wbe-2026" in lower or "arc_wbe_2026" in lower:
        if "babylm proxy report" in lower:
            return False
        return True
    if "babylm" in lower or "gave2" in lower or "retinal" in lower:
        return False
    return True


def validate_arc_wbe_2026_fullrun(root: Path) -> ValidationResult:
    manifest_path = root / "fullrun_manifest.json"
    state_path = root / "state.json"
    log_path = root / "logs/e2e.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "state": rel(state_path, root) if state_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
        "final_report": None,
        "score": None,
        "score_source": None,
        "score_artifact": None,
        "official_comparable": None,
        "submission_artifact": None,
    }
    if not manifest_path.exists() or not state_path.exists() or not log_path.exists():
        return ValidationResult(
            "failed_no_artifacts",
            "ARC full-run wrapper did not leave manifest/state/log evidence.",
            evidence,
            [],
        )

    state = read_json(state_path)
    if not isinstance(state, dict):
        return ValidationResult(
            "failed_no_artifacts", "ARC full-run state is unreadable.", evidence, []
        )
    evidence["status"] = state.get("status", "unknown")
    evidence["summary"] = state.get("summary")
    fullrun_manifest = read_json(manifest_path)
    if not isinstance(fullrun_manifest, dict):
        return ValidationResult(
            "failed_no_artifacts", "ARC full-run manifest is unreadable.", evidence, []
        )
    evidence["native_entrypoint"] = fullrun_manifest.get("native_entrypoint")
    evidence["kimi_injection"] = fullrun_manifest.get("kimi_injection")
    evidence["native_standard_version"] = fullrun_manifest.get("native_standard_version")

    if state.get("status") == "unsupported_native_entrypoint":
        reason = state.get(
            "summary", "Framework has no supported native noninteractive entrypoint."
        )
        return ValidationResult("unsupported_native_entrypoint", reason, evidence, [])
    final_report = pick_latest(
        [
            root / "workspace/final_report.md",
            root / "artifacts/final_report.md",
        ]
    )
    submission_artifact = pick_latest(
        [
            root / "workspace/submission.json",
            root / "artifacts/submission.json",
        ]
    )
    score_path, score_payload = extract_arc_score(root)

    if final_report is not None:
        evidence["final_report"] = rel(final_report, root)
    if submission_artifact is not None:
        evidence["submission_artifact"] = rel(submission_artifact, root)
    if score_path is not None and isinstance(score_payload, dict):
        evidence["score"] = float(score_payload["score"])
        evidence["score_source"] = score_payload["score_source"]
        evidence["score_artifact"] = rel(score_path, root)
        evidence["official_comparable"] = (
            score_payload["score_source"] in OFFICIAL_ARC_SCORE_SOURCES
        )
        if isinstance(score_payload.get("score_artifact"), str):
            evidence["score_artifact_source"] = score_payload["score_artifact"]

    submission_payload = read_json(submission_artifact) if submission_artifact is not None else None
    trace_payload = read_json(root / "workspace/experiment_trace.json")
    if isinstance(submission_payload, dict):
        evidence["submission_payload"] = submission_payload

    trace_ok, trace_failures, trace_evidence = arc_trace_integrity(trace_payload, fullrun_manifest)
    evidence.update(trace_evidence)
    evidence["trace_integrity_ok"] = trace_ok
    evidence["trace_integrity_failures"] = trace_failures

    if fullrun_manifest.get("native_standard_version") == "1.0":
        idea_path = root / "workspace/research_idea.json"
        trace_path = root / "workspace/experiment_trace.json"
        idea = read_json(idea_path)
        trace = trace_payload
        evidence["research_idea"] = rel(idea_path, root) if idea_path.is_file() else None
        evidence["experiment_trace"] = rel(trace_path, root) if trace_path.is_file() else None
        idea_fields = (
            "hypothesis",
            "method_rationale",
            "expected_failure_modes",
            "comparison_logic",
        )

        def nonempty_idea_field(value: object) -> bool:
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, list):
                return bool(value) and all(isinstance(item, str) and item.strip() for item in value)
            if isinstance(value, dict):
                return bool(value)
            return False

        valid_idea = isinstance(idea, dict) and all(
            nonempty_idea_field(
                idea.get(key)
                if key != "method_rationale"
                else (idea.get("method_rationale") or idea.get("rationale"))
            )
            for key in idea_fields
        )
        valid_trace = (
            isinstance(trace, dict)
            and trace.get("idea_artifact") == "research_idea.json"
            and trace.get("idea_locked_before_experiments") is True
        )
        if not valid_idea or not valid_trace:
            return ValidationResult(
                "failed_validation",
                "ARC native-standard run lacks a valid pre-experiment research idea and lock evidence.",
                evidence,
                ["missing_or_invalid_research_idea_evidence"],
            )

    if not trace_ok:
        return ValidationResult(
            "failed_validation",
            "ARC full-run experiment trace failed native, experiment-selection, or provider integrity checks.",
            evidence,
            trace_failures,
        )

    if final_report is not None and not arc_report_looks_on_topic(final_report):
        return ValidationResult(
            "failed_validation",
            "ARC full-run final report is polluted by another topic.",
            evidence,
            ["cross_topic_report_pollution"],
        )

    if state.get("status") == "blocked":
        return ValidationResult(
            "failed_validation",
            f"ARC full-run wrapper is blocked: {state.get('summary', 'unknown blocker')}",
            evidence,
            [],
        )

    if not has_arc_native_execution_log_evidence(log_path, fullrun_manifest):
        return ValidationResult(
            "failed_validation",
            "ARC full-run lacks declared framework-native entrypoint or Kimi-injection evidence.",
            evidence,
            ["missing_native_entrypoint_manifest_or_log"],
        )

    if (
        state.get("status") == "finished"
        and final_report is not None
        and submission_artifact is not None
        and score_path is not None
        and evidence.get("official_comparable")
    ):
        return ValidationResult(
            "finished",
            "ARC full-run produced official-comparable score evidence.",
            evidence,
            [],
        )
    if final_report is not None and submission_artifact is not None:
        log_has_native_entrypoint = has_arc_native_execution_log_evidence(
            log_path, fullrun_manifest
        )
        if state.get("status") == "finished_degraded" and trace_ok and log_has_native_entrypoint:
            return ValidationResult(
                "finished_degraded",
                "ARC full-run completed framework-native execution without local official scoring.",
                evidence,
                [],
            )
        return ValidationResult(
            "failed_validation",
            "ARC full-run left a submission package, but native execution evidence is incomplete.",
            evidence,
            ["missing_native_execution_evidence"],
        )
    return ValidationResult(
        "failed_validation",
        "ARC full-run did not produce sufficient score or submission evidence.",
        evidence,
        ["missing_submission_or_score"],
    )


def psydefdetect_report_looks_on_topic(report_path: Path) -> bool:
    try:
        text = report_path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False
    if "psydefdetect" in text or "psychological defense" in text or "defense mechanism" in text:
        severe_pollution = (
            "babylm proxy report",
            "gave2 task 2",
            "arc-wbe-2026 runtime contract",
            "arc_wbe_2026 runtime contract",
        )
        return not any(marker in text for marker in severe_pollution)
    return False


def has_psydefdetect_native_execution_log_evidence(
    log_path: Path, manifest: dict | None = None
) -> bool:
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if not isinstance(manifest, dict) or manifest.get("framework_orchestration") is not True:
        return False
    for key in ("native_entrypoint", "provider_injection", "native_log_marker", "executor_kind"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return manifest["native_log_marker"] in text and manifest["native_entrypoint"] in text


def psydefdetect_metric_candidates(root: Path) -> list[Path]:
    candidates = [
        root / "workspace/score.json",
        root / "workspace/score_metrics.json",
        root / "workspace/psydefdetect_metrics.json",
        root / "workspace/psydefdetect_scores.json",
        root / "workspace/metrics.json",
        root / "workspace/psydefdetect_run/metrics.json",
        root / "artifacts/score.json",
        root / "artifacts/score_metrics.json",
        root / "artifacts/psydefdetect_metrics.json",
        root / "artifacts/psydefdetect_scores.json",
        root / "artifacts/metrics.json",
    ]
    workspace = root / "workspace"
    if workspace.exists():
        candidates.extend(sorted(workspace.glob("psydefdetect*/metrics.json")))
        candidates.extend(sorted(workspace.glob("*/psydefdetect*/metrics.json")))
    return candidates


def extract_psydefdetect_score(root: Path) -> tuple[Path | None, dict | None]:
    score_keys = (
        ("psydefdetect_score",),
        ("score",),
        ("macro_f1_positive",),
        ("macro_f1_positive_1_8",),
        ("macro_f1_positive_labels_1_8",),
        ("official_macro_f1_positive_1_8",),
        ("official_positive_macro_f1_oof",),
        ("best_positive_macro_f1",),
        ("selected_scores", "official_macro_f1_positive_1_8"),
        ("test_metrics", "macro_f1_positive_1_8"),
        ("eval_metrics", "macro_f1_positive_1_8"),
        ("heldout_metrics", "macro_f1_positive_labels_1_8"),
        ("eval", "official_macro_f1_positive_1_8"),
    )
    for path in psydefdetect_metric_candidates(root):
        if not path.exists():
            continue
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        for key_path in score_keys:
            value = data
            for key in key_path:
                if not isinstance(value, dict) or key not in value:
                    value = None
                    break
                value = value[key]
            if is_number(value):
                return path, {
                    "psydefdetect_score": float(value),
                    "score_key": ".".join(key_path),
                }
    return None, None


def validate_psydefdetect_smoke(root: Path) -> ValidationResult:
    manifest_path = root / "smoke_manifest.json"
    log_path = root / "logs/smoke.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
        "checks": {},
    }
    if not manifest_path.exists():
        return ValidationResult(
            "failed_no_artifacts", "PsyDefDetect smoke manifest is missing.", evidence, []
        )
    if not log_path.exists():
        return ValidationResult(
            "failed_no_artifacts", "PsyDefDetect smoke log is missing.", evidence, []
        )
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return ValidationResult(
            "failed_no_artifacts", "PsyDefDetect smoke manifest is unreadable.", evidence, []
        )
    checks = manifest.get("checks", {})
    evidence["checks"] = checks
    evidence["framework"] = manifest.get("framework")
    evidence["dataset_root"] = manifest.get("dataset_root")
    evidence["contract_file"] = manifest.get("contract_file")
    if not checks:
        return ValidationResult(
            "failed_no_artifacts",
            "PsyDefDetect smoke manifest did not record checks.",
            evidence,
            [],
        )
    if not manifest.get("all_passed"):
        return ValidationResult(
            "failed_validation", "PsyDefDetect smoke checks did not all pass.", evidence, []
        )
    return ValidationResult("finished", "PsyDefDetect smoke checks passed.", evidence, [])


def validate_tdc_admet_tox_smoke(root: Path) -> ValidationResult:
    manifest_path = root / "smoke_manifest.json"
    state_path = root / "state.json"
    log_path = root / "logs/smoke.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "state": rel(state_path, root) if state_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
        "checks": {},
    }
    if not manifest_path.exists() or not state_path.exists() or not log_path.exists():
        return ValidationResult(
            "failed_no_artifacts",
            "TDC-ADMET-Tox smoke manifest/state/log evidence is incomplete.",
            evidence,
            [],
        )
    manifest = read_json(manifest_path)
    state = read_json(state_path)
    if not isinstance(manifest, dict) or not isinstance(state, dict):
        return ValidationResult(
            "failed_no_artifacts", "TDC-ADMET-Tox smoke evidence is unreadable.", evidence, []
        )
    evidence["checks"] = manifest.get("checks", {})
    evidence["framework"] = manifest.get("framework")
    evidence["native_entrypoint"] = manifest.get("native_entrypoint")
    evidence["dataset_root"] = manifest.get("dataset_root")
    evidence["evidence_artifact"] = manifest.get("evidence_artifact")
    if manifest.get("topic_id") != "tdc_admet_tox":
        return ValidationResult(
            "failed_validation", "TDC-ADMET-Tox smoke manifest has the wrong topic.", evidence, []
        )
    if state.get("status") != "finished" or not manifest.get("all_passed"):
        return ValidationResult(
            "failed_validation", "TDC-ADMET-Tox smoke checks did not all pass.", evidence, []
        )
    required_checks = {
        "codex_exit_zero",
        "native_entrypoint_present",
        "public_file_set_exact",
        "labeled_schema",
        "test_schema_unlabeled",
        "endpoint_sets_exact",
        "cross_topic_paths_absent",
        "credentials_absent_from_log",
        "agent_evidence",
        "no_final_outputs",
    }
    checks = manifest.get("checks")
    if not isinstance(checks, dict) or any(checks.get(key) is not True for key in required_checks):
        return ValidationResult(
            "failed_validation", "TDC-ADMET-Tox smoke required checks are incomplete.", evidence, []
        )
    return ValidationResult(
        "finished", "TDC-ADMET-Tox blocking Codex smoke checks passed.", evidence, []
    )


def validate_tdc_admet_tox_fullrun(root: Path) -> ValidationResult:
    manifest_path = root / "fullrun_manifest.json"
    state_path = root / "state.json"
    outcome_path = root / "outcome.json"
    log_path = root / "logs/e2e.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "state": rel(state_path, root) if state_path.exists() else None,
        "outcome": rel(outcome_path, root) if outcome_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
        "dimensions": {},
        "score_artifact": None,
        "main_score": None,
    }
    if not manifest_path.is_file() or not state_path.is_file() or not log_path.is_file():
        return ValidationResult(
            "failed_no_artifacts",
            "TDC-ADMET-Tox full-run wrapper did not leave manifest/state/log evidence.",
            evidence,
            [],
        )
    manifest = read_json(manifest_path)
    state = read_json(state_path)
    if not isinstance(manifest, dict) or not isinstance(state, dict):
        return ValidationResult(
            "failed_no_artifacts", "TDC-ADMET-Tox full-run evidence is unreadable.", evidence, []
        )
    evidence["framework"] = manifest.get("framework")
    evidence["native_entrypoint"] = manifest.get("native_entrypoint")
    evidence["native_entrypoint_source"] = manifest.get("native_entrypoint_source")
    evidence["actual_launch_command"] = manifest.get("actual_launch_command")
    evidence["provider_injection"] = manifest.get("provider_injection")
    evidence["evaluation_model"] = manifest.get("evaluation_model")
    evidence["executor_kind"] = manifest.get("executor_kind")

    status = state.get("status")
    if status == "unsupported_native_entrypoint":
        return ValidationResult(
            "unsupported_native_entrypoint",
            state.get("summary", "Framework has no admissible native entrypoint."),
            evidence,
            [],
        )
    if status == "blocked_benchmark_authorization":
        return ValidationResult(
            "blocked_benchmark_authorization",
            state.get("summary", "Framework benchmark authorization is unavailable."),
            evidence,
            [],
        )
    if not outcome_path.is_file():
        return ValidationResult(
            "failed_no_artifacts", "TDC-ADMET-Tox full-run outcome.json is missing.", evidence, []
        )
    outcome = read_json(outcome_path)
    if not isinstance(outcome, dict):
        return ValidationResult(
            "failed_no_artifacts", "TDC-ADMET-Tox full-run outcome is unreadable.", evidence, []
        )
    dimensions = {
        key: outcome.get(key)
        for key in (
            "research_completed",
            "scored",
            "contract_complete",
            "engineering_complete",
        )
    }
    evidence["dimensions"] = dimensions
    if any(not isinstance(value, bool) for value in dimensions.values()):
        return ValidationResult(
            "failed_validation", "TDC-ADMET-Tox outcome dimensions are incomplete.", evidence, []
        )

    network = manifest.get("network_isolation")
    actual_launch = manifest.get("actual_launch_command")
    executor_kind = manifest.get("executor_kind")
    workspace = root / "workspace"
    official_skill_ok = True
    if executor_kind == "official_framework_skill":
        official_skill_ok = (
            str(manifest.get("native_entrypoint_source", "")).startswith("skills/skills-codex/")
            and (workspace / ".aris/installed-skills-codex.txt").is_file()
            and (workspace / ".agents/skills/research-pipeline").is_symlink()
            and (workspace / "aris_tdc_admet_tox_last_message.txt").is_file()
        )
    launch_owner_ok = (
        isinstance(actual_launch, str)
        and bool(actual_launch.strip())
        and ("codex exec" not in actual_launch or executor_kind == "official_framework_skill")
    )
    native_admission_ok = (
        manifest.get("task_id") == "tdc_admet_tox"
        and manifest.get("evaluation_variant") in {"gpt", "ds", "kimi", "gpt56luna"}
        and manifest.get("framework_orchestration") is True
        and isinstance(manifest.get("native_entrypoint"), str)
        and bool(manifest["native_entrypoint"].strip())
        and isinstance(manifest.get("native_entrypoint_source"), str)
        and bool(manifest["native_entrypoint_source"].strip())
        and executor_kind
        in {
            "framework_cli",
            "framework_internal_codex_runner",
            "official_framework_skill",
        }
        and launch_owner_ok
        and official_skill_ok
        and isinstance(network, dict)
        and network.get("framework_network_internal") is True
        and network.get("public_network_visible_to_framework") is False
        and manifest.get("hidden_labels_projected") is False
        and manifest.get("host_score_after_framework_gate") is True
    )
    evidence["native_admission_ok"] = native_admission_ok
    evidence["official_skill_ok"] = official_skill_ok

    pollution_markers = (
        "babylm",
        "gave2",
        "arc_wbe_2026",
        "arc-wbe-2026",
        "psydefdetect",
        "test_labels.csv",
        "hidden_labels",
    )
    copied_inputs = manifest.get("copied_inputs")
    copied_input_pollution = []
    if not isinstance(copied_inputs, list) or any(
        not isinstance(item, str) for item in copied_inputs
    ):
        copied_input_pollution.append("invalid_copied_inputs_manifest")
    else:
        copied_input_pollution.extend(
            item
            for item in copied_inputs
            if any(marker in item.lower() for marker in pollution_markers)
        )
    workspace_path_pollution = []
    if workspace.is_dir():
        workspace_path_pollution = [
            rel(path, workspace)
            for path in workspace.rglob("*")
            if any(marker in rel(path, workspace).lower() for marker in pollution_markers)
        ]
    evidence["copied_input_pollution"] = copied_input_pollution
    evidence["workspace_path_pollution"] = workspace_path_pollution[:20]
    if copied_input_pollution or workspace_path_pollution:
        return ValidationResult(
            "failed_validation",
            "TDC-ADMET-Tox input manifest or workspace paths contain cross-topic/private-label material.",
            evidence,
            ["cross_topic_or_hidden_label_pollution"],
        )

    score_path = root / "workspace/score.json"
    if score_path.is_file():
        score = read_json(score_path)
        if isinstance(score, dict):
            evidence["score_artifact"] = rel(score_path, root)
            evidence["main_score"] = score.get("main_score")
            evidence["score_source"] = score.get("score_source")

    if dimensions["contract_complete"]:
        if not (
            native_admission_ok
            and dimensions["research_completed"]
            and dimensions["scored"]
            and dimensions["engineering_complete"]
            and evidence.get("score_source") == "host_hidden_test_labels"
            and is_number(evidence.get("main_score"))
        ):
            return ValidationResult(
                "failed_validation",
                "TDC-ADMET-Tox claims contract completion without complete native/score evidence.",
                evidence,
                [],
            )
        return ValidationResult(
            "finished",
            "TDC-ADMET-Tox native research passed framework audit, host scoring, and final audit.",
            evidence,
            [],
        )

    if dimensions["research_completed"]:
        warning = "contract_incomplete"
        if not dimensions["scored"]:
            warning = "score_unavailable"
        return ValidationResult(
            "finished_degraded",
            "TDC-ADMET-Tox native research completed with a retained score or contract warning.",
            evidence,
            [warning],
        )
    return ValidationResult(
        "failed_validation",
        "TDC-ADMET-Tox native framework did not complete an auditable research handoff.",
        evidence,
        ["research_not_completed"],
    )


def validate_psydefdetect_fullrun(root: Path) -> ValidationResult:
    manifest_path = root / "fullrun_manifest.json"
    state_path = root / "state.json"
    log_path = root / "logs/e2e.log"
    evidence = {
        "manifest": rel(manifest_path, root) if manifest_path.exists() else None,
        "state": rel(state_path, root) if state_path.exists() else None,
        "log": rel(log_path, root) if log_path.exists() else None,
        "final_report": None,
        "prediction_artifact": None,
        "score_artifact": None,
        "experiment_trace": None,
    }
    if not manifest_path.exists() or not state_path.exists() or not log_path.exists():
        return ValidationResult(
            "failed_no_artifacts",
            "PsyDefDetect full-run wrapper did not leave manifest/state/log evidence.",
            evidence,
            [],
        )
    state = read_json(state_path)
    if not isinstance(state, dict):
        return ValidationResult(
            "failed_no_artifacts", "PsyDefDetect full-run state is unreadable.", evidence, []
        )
    fullrun_manifest = read_json(manifest_path)
    if not isinstance(fullrun_manifest, dict):
        return ValidationResult(
            "failed_no_artifacts", "PsyDefDetect full-run manifest is unreadable.", evidence, []
        )
    evidence["status"] = state.get("status", "unknown")
    evidence["summary"] = state.get("summary")
    evidence["native_entrypoint"] = fullrun_manifest.get("native_entrypoint")
    evidence["provider_injection"] = fullrun_manifest.get("provider_injection")
    evidence["executor_kind"] = fullrun_manifest.get("executor_kind")
    if state.get("status") == "unsupported_native_entrypoint":
        reason = state.get(
            "summary", "Framework has no supported native noninteractive entrypoint."
        )
        return ValidationResult("unsupported_native_entrypoint", reason, evidence, [])
    if state.get("status") == "blocked_benchmark_authorization":
        reason = state.get("summary", "Framework benchmark authorization has not been supplied.")
        return ValidationResult("blocked_benchmark_authorization", reason, evidence, [])
    final_report = pick_latest(
        [root / "workspace/final_report.md", root / "artifacts/final_report.md"]
    )
    prediction_artifact = pick_latest(
        [
            root / "workspace/predictions.jsonl",
            root / "workspace/submission.csv",
            root / "artifacts/predictions.jsonl",
            root / "artifacts/submission.csv",
        ]
    )
    experiment_trace = pick_latest(
        [
            root / "workspace/experiment_trace.json",
            root / "artifacts/experiment_trace.json",
        ]
    )
    score_artifact, score_payload = extract_psydefdetect_score(root)
    if final_report is not None:
        evidence["final_report"] = rel(final_report, root)
    if prediction_artifact is not None:
        evidence["prediction_artifact"] = rel(prediction_artifact, root)
    trace_payload = read_json(experiment_trace) if experiment_trace is not None else None
    if experiment_trace is not None and isinstance(trace_payload, dict):
        evidence["experiment_trace"] = rel(experiment_trace, root)
        evidence["framework_native_execution"] = trace_payload.get("framework_native_execution")
        evidence["consumed_topic_input"] = trace_payload.get("consumed_topic_input")
        evidence["workspace_trace_root"] = trace_payload.get("workspace_trace_root")
        evidence["experiment_count"] = (
            len(trace_payload.get("experiments", []))
            if isinstance(trace_payload.get("experiments"), list)
            else 0
        )
        evidence["selected_experiment_id"] = trace_payload.get("selected_experiment_id")
        evidence["framework_internal_model"] = trace_payload.get("framework_internal_model")
        evidence["framework_internal_api_base_url"] = trace_payload.get(
            "framework_internal_api_base_url"
        )
    if score_artifact is not None and isinstance(score_payload, dict):
        evidence["score_artifact"] = rel(score_artifact, root)
        evidence["psydefdetect_score"] = score_payload["psydefdetect_score"]
        evidence["score_key"] = score_payload["score_key"]
    if final_report is not None and not psydefdetect_report_looks_on_topic(final_report):
        return ValidationResult(
            "failed_validation",
            "PsyDefDetect full-run final report is polluted by another topic.",
            evidence,
            ["cross_topic_report_pollution"],
        )
    if state.get("status") == "blocked":
        return ValidationResult(
            "failed_validation",
            f"PsyDefDetect full-run wrapper is blocked: {state.get('summary', 'unknown blocker')}",
            evidence,
            [],
        )
    native_execution = (
        isinstance(trace_payload, dict) and trace_payload.get("framework_native_execution") is True
    )
    consumed_topic_input = (
        isinstance(trace_payload, dict) and trace_payload.get("consumed_topic_input") is True
    )
    workspace_trace_root = (
        trace_payload.get("workspace_trace_root") if isinstance(trace_payload, dict) else None
    )
    selected_experiment_id = (
        trace_payload.get("selected_experiment_id") if isinstance(trace_payload, dict) else None
    )
    experiments = trace_payload.get("experiments") if isinstance(trace_payload, dict) else None
    native_log_evidence = has_psydefdetect_native_execution_log_evidence(log_path, fullrun_manifest)
    expected_model = fullrun_manifest.get("evaluation_model")
    expected_base_url = fullrun_manifest.get("provider_base_url")
    provider_model_ok = (
        isinstance(trace_payload, dict)
        and isinstance(expected_model, str)
        and expected_model.strip()
        and trace_payload.get("framework_internal_model") == expected_model
        and isinstance(trace_payload.get("framework_internal_api_base_url"), str)
        and trace_payload["framework_internal_api_base_url"].strip()
        and isinstance(expected_base_url, str)
        and expected_base_url.strip()
        and trace_payload["framework_internal_api_base_url"].rstrip("/")
        == expected_base_url.rstrip("/")
    )

    if (
        state.get("status") in {"finished", "finished_degraded"}
        and final_report is not None
        and prediction_artifact is not None
        and score_artifact is not None
        and native_execution
        and consumed_topic_input
        and isinstance(workspace_trace_root, str)
        and workspace_trace_root.strip()
        and isinstance(selected_experiment_id, str)
        and selected_experiment_id.strip()
        and isinstance(experiments, list)
        and len(experiments) >= 2
        and len(experiments) <= 4
        and native_log_evidence
        and provider_model_ok
    ):
        return ValidationResult(
            "finished",
            "PsyDefDetect full-run produced score evidence and native experiment trace.",
            evidence,
            [],
        )

    if final_report is not None and prediction_artifact is not None:
        return ValidationResult(
            "failed_validation",
            "PsyDefDetect full-run left predictions/report artifacts, but native-entrypoint, provider, score, or experiment-trace evidence is incomplete.",
            evidence,
            ["missing_native_provider_score_or_experiment_trace"],
        )
    return ValidationResult(
        "failed_validation",
        "PsyDefDetect full-run did not produce sufficient prediction/report/score evidence.",
        evidence,
        ["missing_prediction_report_or_score"],
    )


def validate_topic2_fullrun(root: Path) -> ValidationResult:
    workspace = root / "workspace"
    required_files = [
        "research_idea.json",
        "experiment_trace.json",
        "final_report.md",
        "score.json",
        "src/config.yaml",
    ]
    missing = [name for name in required_files if not (workspace / name).is_file()]
    ckpts = sorted((workspace / "checkpoints").glob("*.pkl")) if (workspace / "checkpoints").is_dir() else []
    if len(ckpts) != 5:
        missing.append(f"checkpoints/*.pkl (found {len(ckpts)})")
    evidence: dict[str, object] = {
        "missing_required_files": missing,
        "checkpoint_count": len(ckpts),
        "checkpoint_sample": [rel(p, root) for p in ckpts[:5]],
    }
    trace: dict = {}
    idea: dict = {}
    score: dict = {}
    for name in ("experiment_trace.json", "research_idea.json", "score.json"):
        path = workspace / name
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("not a JSON object")
                if name == "experiment_trace.json":
                    trace = payload
                elif name == "research_idea.json":
                    idea = payload
                else:
                    score = payload
            except Exception as exc:
                missing.append(f"{name}:{exc}")
    failures: list[str] = []
    if trace.get("framework_native_execution") is not True:
        failures.append("framework_native_execution_not_proven")
    if trace.get("consumed_topic_input") is not True:
        failures.append("topic_input_consumption_not_proven")
    experiments = trace.get("experiments")
    if not isinstance(experiments, list) or len(experiments) < 1:
        failures.append("experiment_count_invalid")
    selected = trace.get("selected_experiment_id")
    if not isinstance(selected, str) or not selected.strip():
        failures.append("missing_selected_experiment_id")
    for key in ("hypothesis", "method_rationale", "expected_failure_modes", "comparison_logic"):
        if not idea.get(key):
            failures.append(f"research_idea_missing_{key}")
    if score.get("score_source") != "official_evaluate_py":
        failures.append("missing_official_score_source")
    evidence["failures"] = failures
    if missing or failures:
        return ValidationResult(
            "failed_validation",
            "Topic 2 full-run artifacts, score, or trace are incomplete.",
            evidence,
            failures,
        )
    return ValidationResult(
        "finished",
        "Topic 2 full-run produced the required artifacts, official score, and trace.",
        evidence,
        [],
    )


def validate(framework: str, root: Path) -> ValidationResult:
    mapping = {
        "topic2_fullrun": validate_topic2_fullrun,
        "ai_researcher_real": validate_ai_researcher_real,
        "ai_researcher_resume": validate_ai_researcher_resume,
        "ai_scientist_v2": validate_ai_scientist_v2,
        "aris": validate_aris,
        "autoresearchclaw_resume": validate_autoresearchclaw_resume,
        "autoresearchclaw_babylm_fullrun": validate_autoresearchclaw_babylm_fullrun,
        "deepscientist": validate_deepscientist,
        "drclaw": validate_drclaw,
        "evoscientist_auto": validate_evoscientist,
        "evoscientist_continue": validate_evoscientist,
        "gave2_input_pack": validate_gave2_input_pack,
        "arc_wbe_2026_input_pack": validate_arc_wbe_2026_input_pack,
        "gave2_smoke": validate_gave2_smoke,
        "gave2_fullrun": validate_gave2_fullrun,
        "arc_wbe_2026_smoke": validate_arc_wbe_2026_smoke,
        "arc_wbe_2026_fullrun": validate_arc_wbe_2026_fullrun,
        "psydefdetect_smoke": validate_psydefdetect_smoke,
        "psydefdetect_fullrun": validate_psydefdetect_fullrun,
        "tdc_admet_tox_smoke": validate_tdc_admet_tox_smoke,
        "tdc_admet_tox_fullrun": validate_tdc_admet_tox_fullrun,
    }
    if framework not in mapping:
        raise SystemExit(f"Unknown framework validator: {framework}")
    return mapping[framework](root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--state-file")
    parser.add_argument("--manifest-path")
    args = parser.parse_args()

    root = Path(args.run_root).resolve()
    state_file = Path(args.state_file).resolve() if args.state_file else root / "state.json"
    manifest_path = (
        Path(args.manifest_path).resolve()
        if args.manifest_path
        else root / "artifact_manifest.json"
    )

    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    result = validate(args.framework, root)
    manifest = {
        "framework": args.framework,
        "run_root": str(root),
        "validated_at": now_iso(),
        "status": result.status,
        "summary": result.summary,
        "warnings": result.warnings,
        "evidence": result.evidence,
        "prior_state": state,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if state_file.parent.exists():
        merged = dict(state)
        merged["status"] = result.status
        merged["summary"] = result.summary
        merged["updated_at"] = now_iso()
        merged["validator_summary"] = result.summary
        merged["artifact_manifest"] = str(manifest_path)
        if "gave2_metrics" in result.evidence:
            merged["gave2_metrics"] = result.evidence["gave2_metrics"]
        if result.status == "finished_degraded":
            merged["degraded_reason"] = result.summary
        else:
            merged.pop("degraded_reason", None)
        state_file.write_text(json.dumps(merged, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if result.ok else 13


if __name__ == "__main__":
    raise SystemExit(main())

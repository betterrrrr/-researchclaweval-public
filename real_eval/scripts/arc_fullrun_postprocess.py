#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


OFFICIAL_ARC_SCORE_SOURCES = {
    "official_adapter_whest_run",
}


def read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def collect_estimator_candidates(workspace: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in ("estimator.py", "submission/estimator.py", "artifacts/estimator.py", "**/estimator.py"):
        for path in sorted(workspace.glob(pattern)):
            if path.is_file() and path not in candidates:
                candidates.append(path)
    return candidates


def write_report_with_fallback(workspace: Path, artifacts_dir: Path, content: str) -> Path:
    report_path = workspace / "final_report.md"
    try:
        if report_path.exists() and not report_path.is_file():
            raise IsADirectoryError(str(report_path))
        if report_path.exists() and not report_path.stat().st_mode & 0o200:
            report_path.unlink()
        report_path.write_text(content, encoding="utf-8")
        return report_path
    except Exception:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        fallback = artifacts_dir / "final_report.md"
        fallback.write_text(content, encoding="utf-8")
        return fallback


def build_state_payload(run_rc: int, score_payload: dict | None) -> dict[str, object]:
    if run_rc != 0:
        return {
            "status": "failed",
            "summary": "ARC framework-native execution exited non-zero; see log",
        }

    source = score_payload.get("score_source") if isinstance(score_payload, dict) else None
    if isinstance(source, str) and source in OFFICIAL_ARC_SCORE_SOURCES:
        return {
            "status": "finished",
            "summary": "ARC framework-native execution completed and produced local official score evidence.",
        }

    return {
        "status": "finished_degraded",
        "summary": "ARC framework-native execution completed without local official scoring.",
    }


def build_submission_payload(
    *,
    workspace: Path,
    framework: str,
    slug: str,
    dataset_root: str,
    contract_file: str,
    log_file: str,
    run_rc: int,
) -> dict[str, object]:
    estimator_candidates = collect_estimator_candidates(workspace)
    payload: dict[str, object] = {
        "framework": framework,
        "slug": slug,
        "topic_id": "arc_wbe_2026",
        "dataset_root": dataset_root,
        "contract_file": contract_file,
        "submission_artifact": str(workspace / "submission.json"),
        "framework_native_execution": run_rc == 0,
        "consumed_topic_input": True,
        "workspace_trace_root": str(workspace),
        "log": log_file,
    }
    if estimator_candidates:
        payload["estimator_artifact"] = str(estimator_candidates[0])
        payload["estimator_candidates"] = [str(path) for path in estimator_candidates[:10]]
    return payload


def write_postprocess_outputs(
    *,
    workspace: Path,
    artifacts_dir: Path,
    framework: str,
    slug: str,
    dataset_root: str,
    contract_file: str,
    log_file: str,
    run_rc: int,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    submission_payload = build_submission_payload(
        workspace=workspace,
        framework=framework,
        slug=slug,
        dataset_root=dataset_root,
        contract_file=contract_file,
        log_file=log_file,
        run_rc=run_rc,
    )
    submission_path = workspace / "submission.json"
    submission_path.write_text(json.dumps(submission_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    score_path = workspace / "score.json"
    score_payload = read_json(score_path) if score_path.exists() else None

    lines = [
        "# ARC-WBE-2026 Fullrun Report",
        "",
        f"Framework: {framework}",
        "",
        f"- Native execution attempted: {'yes' if run_rc == 0 else 'no'}",
        f"- Dataset root: `{dataset_root}`",
        f"- Contract file: `{contract_file}`",
        f"- Workspace trace root: `{workspace}`",
    ]
    estimator_artifact = submission_payload.get("estimator_artifact")
    if isinstance(estimator_artifact, str):
        lines.append(f"- Estimator candidate: `{estimator_artifact}`")
    if isinstance(score_payload, dict) and is_number(score_payload.get("score")):
        lines.append(f"- Official local score: `{float(score_payload['score'])}`")
        lines.append(f"- Score source: `{score_payload.get('score_source', 'unknown')}`")
    else:
        lines.append("- Official local score: unavailable")
    report_path = write_report_with_fallback(workspace, artifacts_dir, "\n".join(lines) + "\n")

    state_payload = {
        "project_id": "arc_wbe_2026",
        "phase": "fullrun",
        **build_state_payload(run_rc, score_payload if isinstance(score_payload, dict) else None),
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    return report_path, submission_payload, state_payload


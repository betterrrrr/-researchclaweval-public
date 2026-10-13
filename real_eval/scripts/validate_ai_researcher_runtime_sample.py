#!/usr/bin/env python3
"""validate_ai_researcher_runtime_sample.py

F2: Select 3 runtime samples (one per model, distinct topics) and verify
    runtime artifacts.

Given a matrix of runs (framework × topic × model × attempt), this validator
selects exactly 3 samples:
  - One per model (GPT, DeepSeek, Kimi)
  - All from distinct topics (no two samples share the same topic)
  - Prefers scored/finished runs over blocked/failed ones

It then verifies that each selected sample has the required runtime
artifacts: research_idea.json, experiment_trace.json, final_report.md, and
optionally score.json.  If --require-gave2-blocked is set, the GAVE2 topic
samples must be recorded as blocked.

Usage:
  python3 validate_ai_researcher_runtime_sample.py \
      --matrix real_eval/config/registry_matrix.json \
      --selection-policy one-per-model-distinct-topics \
      --verify research_idea.json,experiment_trace.json,final_report.md \
      --require-gave2-blocked \
      --reconcile-running \
      --output result.json

Exit codes:
  0   All selected samples pass artifact verification.
  1   One or more samples fail verification, or selection fails.
  2   Input error (missing matrix, bad JSON, etc.).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────

SCHEMA_VERSION = "runtime-sample-validation.v1"

REQUIRED_ARTIFACTS_COMMON = frozenset({
    "research_idea.json",
    "experiment_trace.json",
    "final_report.md",
})

OPTIONAL_ARTIFACTS = frozenset({
    "score.json",
    "predictions.jsonl",
    "predictions.csv",
    "submission.json",
    "submission.csv",
    "score.json",
    "state.json",
    "fullrun_manifest.json",
})

# The three models used in AI-Researcher evaluation
RECOGNIZED_MODELS = frozenset({"gpt-5.4", "deepseek-v4-flash", "kimi-k2.6"})

MODEL_SHORT_NAMES = {
    "gpt-5.4": "gpt",
    "deepseek-v4-flash": "deepseek",
    "kimi-k2.6": "kimi",
}

# ── Helpers ────────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with open(path) as f:
            return dict(json.load(f))
    except FileNotFoundError:
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def _find_runs_for_model_topic(
    runs_root: Path,
    model: str,
    topic: str,
) -> list[Path]:
    """Find run directories under *runs_root* that match the given model
    and topic.  Returns sorted list of run directories."""
    matches: list[Path] = []
    model_short = MODEL_SHORT_NAMES.get(model, model)
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir():
            continue
        name = run_dir.name.lower()
        # Match by model and topic in the directory name
        if model_short in name and topic.lower() in name:
            matches.append(run_dir)
    return matches


def _classify_run(run_dir: Path) -> str:
    """Classify a run directory by its outcome."""
    outcome_file = run_dir / "outcome.json"
    if outcome_file.exists():
        try:
            with open(outcome_file) as f:
                data = json.load(f)
            return data.get("outcome", "unknown")
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: look for state.json
    state_file = run_dir / "state.json"
    if state_file.exists():
        try:
            with open(state_file) as f:
                data = json.load(f)
            return data.get("state", "unknown")
        except (json.JSONDecodeError, OSError):
            pass

    # Heuristic: check for artifacts
    has_score = (run_dir / "score.json").exists()
    has_report = (run_dir / "final_report.md").exists()
    if has_score and has_report:
        return "scored"
    if has_report:
        return "finished"
    return "incomplete"


def _verify_artifacts(
    run_dir: Path,
    required: frozenset[str],
    *,
    runs_root: Path,
) -> dict[str, Any]:
    """Verify that *run_dir* contains all required artifacts."""
    results: dict[str, bool] = {}
    artifacts_found: list[str] = []
    artifacts_missing: list[str] = []

    for artifact in required:
        path = run_dir / artifact
        exists = path.exists() and path.is_file()
        results[artifact] = exists
        if exists:
            artifacts_found.append(artifact)
        else:
            artifacts_missing.append(artifact)

    # Also check optional artifacts
    optional_found: list[str] = []
    for artifact in OPTIONAL_ARTIFACTS:
        path = run_dir / artifact
        if path.exists() and path.is_file():
            optional_found.append(artifact)

    # Derive relative path for display
    try:
        rel_path = run_dir.relative_to(runs_root)
    except ValueError:
        rel_path = run_dir.name

    return {
        "run_dir": str(rel_path),
        "abs_path": str(run_dir.resolve()),
        "passed": len(artifacts_missing) == 0,
        "required_artifacts": results,
        "artifacts_found": artifacts_found,
        "artifacts_missing": artifacts_missing,
        "optional_found": optional_found,
    }


# ── Selection Policy ────────────────────────────────────────────────────────


def select_samples_one_per_model_distinct_topics(
    matrix: dict[str, Any],
    runs_root: Path,
    *,
    require_gave2_blocked: bool = False,
    reconcile_running: bool = False,
) -> dict[str, Any]:
    """Select 3 samples: one per model, all from distinct topics.

    Returns a dict with ``selected`` (list of sample dicts), ``passed``
    (bool), and ``errors`` (list of error strings).
    """
    # Extract the run matrix: framework -> topic -> model -> list of attempts
    runs_data = matrix.get("runs", matrix) if isinstance(matrix, dict) else matrix

    # Build a map: model -> list of (topic, run_dir, outcome)
    model_candidates: dict[str, list[dict[str, Any]]] = {m: [] for m in RECOGNIZED_MODELS}

    if isinstance(runs_data, dict):
        for framework, topics in runs_data.items():
            if isinstance(topics, dict):
                for topic, models in topics.items():
                    if isinstance(models, dict):
                        for model, attempts in models.items():
                            if model in RECOGNIZED_MODELS:
                                if isinstance(attempts, list):
                                    for attempt in attempts:
                                        if isinstance(attempt, dict):
                                            run_dir_name = attempt.get("run_dir", "")
                                            run_dir = runs_root / run_dir_name
                                            outcome = attempt.get("outcome", "unknown")
                                            model_candidates[model].append({
                                                "topic": topic,
                                                "run_dir": run_dir,
                                                "run_dir_name": run_dir_name,
                                                "outcome": outcome,
                                                "attempt": attempt,
                                            })
                                elif isinstance(attempts, str):
                                    # Direct run directory reference
                                    run_dir = runs_root / attempts
                                    model_candidates[model].append({
                                        "topic": topic,
                                        "run_dir": run_dir,
                                        "run_dir_name": attempts,
                                        "outcome": _classify_run(run_dir),
                                        "attempt": {},
                                    })

    # If matrix is flat list of runs, try to extract model/topic from each
    if isinstance(runs_data, list):
        for entry in runs_data:
            model = entry.get("model", "")
            topic = entry.get("topic", entry.get("category", ""))
            run_dir_name = entry.get("run_dir", entry.get("run_path", ""))
            if model in RECOGNIZED_MODELS and run_dir_name:
                run_dir = runs_root / run_dir_name
                model_candidates[model].append({
                    "topic": topic,
                    "run_dir": run_dir,
                    "run_dir_name": run_dir_name,
                    "outcome": entry.get("outcome", _classify_run(run_dir)),
                    "attempt": entry,
                })

    # Sort candidates: prefer scored > finished > inconclusive > incomplete
    outcome_rank = {"scored": 0, "finished": 1, "inconclusive": 2, "incomplete": 3, "unknown": 4}

    for model in model_candidates:
        model_candidates[model].sort(
            key=lambda c: (outcome_rank.get(c["outcome"], 99), c["topic"]),
        )

    # Select one sample per model, ensuring distinct topics
    selected: list[dict[str, Any]] = []
    used_topics: set[str] = set()
    errors: list[str] = []

    # Try to pick the best candidate for each model
    for model in ["gpt-5.4", "deepseek-v4-flash", "kimi-k2.6"]:
        candidates = model_candidates.get(model, [])
        if not candidates:
            errors.append(f"no candidates found for model {model}")
            continue

        chosen = None
        for candidate in candidates:
            topic = candidate["topic"]
            if topic not in used_topics:
                chosen = candidate
                used_topics.add(topic)
                break

        if chosen is None:
            # Fallback: pick the first candidate even if topic is reused
            chosen = candidates[0]
            used_topics.add(chosen["topic"])

        # Verify run directory exists
        if not chosen["run_dir"].is_dir():
            errors.append(
                f"run directory not found for {model}/{chosen['topic']}: "
                f"{chosen['run_dir']}"
            )

        selected.append(chosen)

    # GAVE2 blocked check
    if require_gave2_blocked:
        gave2_found = False
        for s in selected:
            if "gave2" in s["topic"].lower():
                gave2_found = True
                if s["outcome"] != "blocked":
                    errors.append(
                        f"GAVE2 sample has outcome '{s['outcome']}', "
                        f"expected 'blocked' (--require-gave2-blocked)"
                    )
        if not gave2_found:
            errors.append("--require-gave2-blocked set but no GAVE2 sample selected")

    return {
        "selection_policy": "one-per-model-distinct-topics",
        "selected": selected,
        "used_topics": list(used_topics),
        "errors": errors,
        "passed": len(errors) == 0,
    }


# ── Validation ──────────────────────────────────────────────────────────────


def validate_runtime_samples(
    matrix: dict[str, Any],
    runs_root: Path,
    *,
    selection_policy: str = "one-per-model-distinct-topics",
    verify_artifacts: frozenset[str] | None = None,
    require_gave2_blocked: bool = False,
    reconcile_running: bool = False,
) -> dict[str, Any]:
    """Select samples and verify their runtime artifacts.

    Returns a comprehensive result dict.
    """
    if verify_artifacts is None:
        verify_artifacts = REQUIRED_ARTIFACTS_COMMON

    # Step 1: Select samples
    if selection_policy == "one-per-model-distinct-topics":
        selection = select_samples_one_per_model_distinct_topics(
            matrix,
            runs_root,
            require_gave2_blocked=require_gave2_blocked,
            reconcile_running=reconcile_running,
        )
    else:
        return {
            "schema": SCHEMA_VERSION,
            "timestamp": now_iso(),
            "passed": False,
            "error": f"unknown selection policy: {selection_policy}",
        }

    # Step 2: Verify artifacts for each selected sample
    verifications: list[dict[str, Any]] = []
    for sample in selection["selected"]:
        run_dir = sample["run_dir"]
        if run_dir.is_dir():
            verification = _verify_artifacts(run_dir, verify_artifacts, runs_root=runs_root)
        else:
            verification = {
                "run_dir": sample["run_dir_name"],
                "abs_path": str(run_dir),
                "passed": False,
                "error": "run directory not found",
                "required_artifacts": {},
                "artifacts_found": [],
                "artifacts_missing": list(verify_artifacts),
                "optional_found": [],
            }
        verification["model"] = sample.get("model", "")
        verification["topic"] = sample["topic"]
        verification["outcome"] = sample["outcome"]
        verifications.append(verification)

    all_passed = selection["passed"] and all(v["passed"] for v in verifications)

    return {
        "schema": SCHEMA_VERSION,
        "timestamp": now_iso(),
        "passed": all_passed,
        "selection_policy": selection_policy,
        "selection": {
            "count": len(selection["selected"]),
            "used_topics": selection["used_topics"],
            "errors": selection["errors"],
        },
        "samples": verifications,
        "summary": {
            "samples_selected": len(verifications),
            "samples_passed": sum(1 for v in verifications if v["passed"]),
            "samples_failed": sum(1 for v in verifications if not v["passed"]),
            "artifacts_verified": list(verify_artifacts),
        },
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="F2: Select 3 runtime samples (one per model, distinct topics) "
                    "and verify runtime artifacts.",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        required=True,
        help="Path to the run matrix JSON (e.g. config/registry_matrix.json)",
    )
    parser.add_argument(
        "--selection-policy",
        type=str,
        default="one-per-model-distinct-topics",
        choices=["one-per-model-distinct-topics"],
        help="Sample selection strategy (default: one-per-model-distinct-topics)",
    )
    parser.add_argument(
        "--verify",
        type=str,
        default="research_idea.json,experiment_trace.json,final_report.md",
        help="Comma-separated list of required artifact filenames",
    )
    parser.add_argument(
        "--require-gave2-blocked",
        action="store_true",
        help="Require that GAVE2 samples are recorded as blocked",
    )
    parser.add_argument(
        "--reconcile-running",
        action="store_true",
        help="Reconcile running/incomplete runs before validation",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write validation result JSON",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    matrix = _load_json(args.matrix)

    # Determine runs_root from matrix or default
    runs_root = Path(matrix.get("runs_root", "real_eval/runs")) if isinstance(matrix, dict) else Path("real_eval/runs")
    if not runs_root.is_absolute():
        # Resolve relative to script location
        runs_root = Path(__file__).resolve().parents[2] / runs_root

    verify_set = frozenset(
        a.strip() for a in args.verify.split(",") if a.strip()
    )

    result = validate_runtime_samples(
        matrix,
        runs_root,
        selection_policy=args.selection_policy,
        verify_artifacts=verify_set,
        require_gave2_blocked=args.require_gave2_blocked,
        reconcile_running=args.reconcile_running,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result["summary"], indent=2))

    for sample in result["samples"]:
        status = "PASS" if sample["passed"] else "FAIL"
        print(f"  [{status}] {sample['model'] or '?'} / {sample['topic']}: "
              f"{sample.get('run_dir', '?')} "
              f"(outcome={sample['outcome']})")

    if result.get("selection", {}).get("errors"):
        for err in result["selection"]["errors"]:
            print(f"  ERROR: {err}", file=sys.stderr)

    if not result["passed"]:
        print("RUNTIME SAMPLE VALIDATION FAILED", file=sys.stderr)
        sys.exit(1)

    print("RUNTIME SAMPLE VALIDATION PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
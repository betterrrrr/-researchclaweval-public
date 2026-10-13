#!/usr/bin/env python3
"""validate_ai_researcher_handoff_order.py

Validate Topic-specific handoff order and score ownership without host
backfill for AI-Researcher evaluation runs.

Each Topic defines a contract for framework artifacts, host artifacts, and
the gates between them. The validator reads a fixture directory (one
subdirectory per Topic) and checks:

  1. Framework artifacts are present (no missing artifact prevents scoring).
  2. Host has not created framework-authored fields (no host backfill).
  3. Scorer runs only after its framework-stage gate.
  4. TDC hidden labels remain host-only.

Usage:
  python3 validate_ai_researcher_handoff_order.py \
      --fixtures real_eval/tests/fixtures/ai_researcher/handoff-order-valid \
      --output .omo/evidence/ai-researcher-repair/todo-14-happy.json

Exit codes:
  0   All Topics pass validation.
  1   One or more Topics fail validation.
  2   Input error (missing fixture root, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Topic contracts ────────────────────────────────────────────────────

# Each Topic defines:
#   framework_artifacts: list of artifact filenames the framework must create
#   host_artifacts:      list of artifact filenames the host may create
#   framework_stage:     name of the gate that must pass before scoring
#   scorer_owner:        "host" or "framework"
#   host_only_fields:    fields never written by the framework
#   framework_only_fields: fields never written by the host

TOPIC_CONTRACTS: dict[str, dict[str, Any]] = {
    "babylm": {
        "label": "BabyLM-2026-Strict-Small",
        "framework_artifacts": [
            "research_idea.json",
            "experiment_trace.json",
            "final_report.md",
            "native_results.json",
        ],
        "host_artifacts": [
            "score.json",
        ],
        "framework_stage": "framework_complete",
        "scorer_owner": "host",
        "host_only_fields": ["score", "validation_perplexity_official"],
        "framework_only_fields": ["research_idea", "experiment_trace"],
        "framework_stage_artifact": "experiment_trace.json",
        "disallowed_framework_artifacts": [],
    },
    "arc_wbe_2026": {
        "label": "ARC-WBE-2026",
        "framework_artifacts": [
            "research_idea.json",
            "estimator_results.json",
            "submission.csv",
            "experiment_trace.json",
            "final_report.md",
        ],
        "host_artifacts": [
            "official_score.json",
        ],
        "framework_stage": "framework_complete",
        "scorer_owner": "host",
        "host_only_fields": ["official_score"],
        "framework_only_fields": ["research_idea", "estimator_results", "submission"],
        "framework_stage_artifact": "experiment_trace.json",
        "disallowed_framework_artifacts": [],
    },
    "psydefdetect": {
        "label": "PsyDefDetect",
        "framework_artifacts": [
            "predictions.jsonl",
            "experiment_trace.json",
            "final_report.md",
        ],
        "host_artifacts": [
            "score.json",
        ],
        "framework_stage": "framework_complete",
        "scorer_owner": "host",
        "host_only_fields": ["score", "macro_f1_official"],
        "framework_only_fields": ["predictions", "experiment_trace"],
        "framework_stage_artifact": "experiment_trace.json",
        "disallowed_framework_artifacts": [],
    },
    "tdc_admet_tox": {
        "label": "TDC-ADMET-Tox",
        "framework_artifacts": [
            "predictions.csv",
            "research_idea.json",
            "experiment_trace.json",
            "environment.json",
            "paper.md",
            "final_report.md",
        ],
        "host_artifacts": [
            "score.json",       # host hidden-label score
            "final_audit.json", # host final audit after scoring
        ],
        "framework_stage": "framework_audit",  # audit must pass before host scoring
        "scorer_owner": "host",
        "host_only_fields": [
            "score",
            "hidden_labels",
            "ames_auroc",
            "herg_auroc",
            "dili_auroc",
            "macro_avg_auroc",
        ],
        "framework_only_fields": [
            "predictions",
            "research_idea",
            "experiment_trace",
            "environment",
        ],
        "framework_stage_artifact": "audit.json",  # framework audit gate
        "hidden_labels_path": "host/hidden_labels", # host-only path
        "disallowed_framework_artifacts": ["score.json"],
    },
}

# Ordered sequence for validation output
TOPIC_NAMES = ["babylm", "arc_wbe_2026", "psydefdetect", "tdc_admet_tox"]


# ── validation logic ───────────────────────────────────────────────────


def _artifact_exists(artifact_dir: Path, filename: str) -> bool:
    """Check if an artifact file exists in *artifact_dir*."""
    return (artifact_dir / filename).is_file()


def _load_json_artifact(artifact_dir: Path, filename: str) -> dict | None:
    """Load a JSON artifact from *artifact_dir*, returning None if missing or not JSON."""
    path = artifact_dir / filename
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _get_artifact_timestamp(artifact: dict | None, field: str = "created_at") -> str | None:
    """Extract a timestamp from an artifact dict."""
    if artifact is None:
        return None
    return artifact.get(field)


def _check_artifact_ownership(
    artifact: dict | None,
    filename: str,
    owner: str,
    forbidden_fields: list[str],
    context: str,
) -> list[str]:
    """Check that *artifact* does not contain fields owned by a different party.

    *forbidden_fields* are fields that *owner* must not write.
    """
    errors: list[str] = []
    if artifact is None:
        return errors
    for field in forbidden_fields:
        if field in artifact:
            errors.append(
                f"{context}: {owner} artifact {filename!r} contains "
                f"forbidden field {field!r} (owned by the other party)"
            )
    return errors


def validate_topic(
    topic_id: str,
    topic_dir: Path,
    contract: dict[str, Any],
) -> list[str]:
    """Validate a single Topic's fixture directory.

    Returns a list of error strings (empty list = valid).
    """
    errors: list[str] = []
    label = contract["label"]

    # ── 1. Resolve artifact directories ────────────────────────────────
    framework_dir = topic_dir / "framework"
    host_dir = topic_dir / "host"

    if not framework_dir.is_dir():
        errors.append(f"{label}: missing framework/ directory")
        return errors
    if not host_dir.is_dir():
        errors.append(f"{label}: missing host/ directory")
        return errors

    # ── 2. Check framework artifact existence ──────────────────────────
    framework_exists: dict[str, bool] = {}
    framework_json: dict[str, dict | None] = {}
    for art_name in contract["framework_artifacts"]:
        exists = _artifact_exists(framework_dir, art_name)
        framework_exists[art_name] = exists
        framework_json[art_name] = _load_json_artifact(framework_dir, art_name) if exists else None

    # Also load the framework stage artifact (always JSON)
    stage_artifact_name = contract["framework_stage_artifact"]
    stage_artifact = _load_json_artifact(framework_dir, stage_artifact_name)

    # ── 3. Check host artifact existence ────────────────────────────────
    host_exists: dict[str, bool] = {}
    host_json: dict[str, dict | None] = {}
    for art_name in contract["host_artifacts"]:
        exists = _artifact_exists(host_dir, art_name)
        host_exists[art_name] = exists
        host_json[art_name] = _load_json_artifact(host_dir, art_name) if exists else None

    # ── 4. Check missing framework artifact prevents scoring ───────────
    missing_framework = [
        name for name, exists in framework_exists.items() if not exists
    ]
    if missing_framework:
        errors.append(
            f"{label}: missing framework artifact(s): {', '.join(missing_framework)}"
        )
        # If framework artifacts are missing, scoring should be absent
        for host_art_name in contract["host_artifacts"]:
            if host_exists.get(host_art_name):
                errors.append(
                    f"{label}: host artifact {host_art_name!r} present despite "
                    f"missing framework artifact(s) — scoring must not proceed"
                )
        # No further checks if framework is incomplete
        return errors

    # ── 5. Check framework stage gate ──────────────────────────────────
    # BabyLM, ARC, PsyDefDetect: stage is "framework_complete" = all framework
    # artifacts exist.  TDC: stage is audit.json with audit_passed=true.
    stage_ok = False
    if topic_id == "tdc_admet_tox":
        if stage_artifact is not None:
            audit_passed = stage_artifact.get("audit_passed", False)
            if audit_passed:
                stage_ok = True
            if not stage_ok:
                stage_status = stage_artifact.get("status", "")
                stage_result = stage_artifact.get("result", "")
                if stage_status == "passed" or stage_result == "passed":
                    stage_ok = True
        if not stage_ok:
            errors.append(
                f"{label}: framework stage gate ({stage_artifact_name}) not passed "
                f"— audit_passed={stage_artifact.get('audit_passed', 'N/A') if stage_artifact else 'missing'}"
            )
    else:
        # Non-TDC topics: stage is complete when all framework artifacts exist
        if not missing_framework:
            stage_ok = True
        if not stage_ok:
            errors.append(
                f"{label}: framework stage not complete — missing framework artifact(s)"
            )

    if not stage_ok:
        # If stage gate not passed, host scoring must be absent
        for host_art_name in contract["host_artifacts"]:
            if host_exists.get(host_art_name):
                errors.append(
                    f"{label}: host artifact {host_art_name!r} present despite "
                    f"framework stage gate not passed — scoring must be gated"
                )
        return errors

    # ── 6. Check host does not create framework-authored fields ────────
    for art_name, art in host_json.items():
        if art is not None:
            errs = _check_artifact_ownership(
                art, art_name, "host",
                contract["framework_only_fields"],
                label,
            )
            errors.extend(errs)

    # ── 7. Check framework does not create host-only fields ────────────
    for art_name, art in framework_json.items():
        if art is not None:
            errs = _check_artifact_ownership(
                art, art_name, "framework",
                contract["host_only_fields"],
                label,
            )
            errors.extend(errs)

    # ── 7b. Check for disallowed artifacts in framework directory ──────
    for disallowed_name in contract.get("disallowed_framework_artifacts", []):
        disallowed_path = framework_dir / disallowed_name
        if disallowed_path.is_file():
            errors.append(
                f"{label}: disallowed artifact {disallowed_name!r} found in "
                f"framework/ directory — host-only artifacts must not be created by the framework"
            )

    # ── 8. TDC-specific: hidden labels host-only ───────────────────────
    if topic_id == "tdc_admet_tox":
        hidden_labels_path = topic_dir / contract["hidden_labels_path"]
        if not hidden_labels_path.is_dir():
            errors.append(
                f"{label}: hidden labels directory not found at "
                f"{contract['hidden_labels_path']}/ — hidden labels must be host-only"
            )
        else:
            # Verify hidden labels are NOT accessible from framework directory
            framework_hidden = framework_dir / "hidden_labels"
            if framework_hidden.is_dir():
                errors.append(
                    f"{label}: hidden_labels/ found in framework/ directory — "
                    f"hidden labels must be host-only"
                )

        # Verify host score.json does not leak to framework
        host_score = host_json.get("score.json")
        if host_score is not None:
            if "hidden_labels" in host_score:
                # It's OK for host score to reference hidden labels, but the
                # actual label data must not be in framework-accessible paths
                pass

        # Verify framework audit must complete before host scoring
        host_score_present = host_exists.get("score.json", False)
        framework_audit = _load_json_artifact(framework_dir, "audit.json")
        if host_score_present and framework_audit is None:
            errors.append(
                f"{label}: host score.json present but framework audit.json "
                f"missing — audit must pass before scoring"
            )

    # ── 9. Timestamp ordering: framework stage before host scoring ────
    stage_ts = _get_artifact_timestamp(stage_artifact, "created_at")
    for host_art_name, host_art in host_json.items():
        if host_art is None:
            continue
        host_ts = _get_artifact_timestamp(host_art, "created_at")
        if stage_ts and host_ts and host_ts < stage_ts:
            errors.append(
                f"{label}: host artifact {host_art_name!r} timestamp ({host_ts}) "
                f"precedes framework stage artifact timestamp ({stage_ts}) — "
                f"scoring must run after framework stage gate"
            )

    return errors


# ── CLI ────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Topic-specific handoff order and score ownership"
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        required=True,
        help="Path to fixture directory containing topic subdirectories",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write JSON output",
    )
    args = parser.parse_args()

    fixtures_root = args.fixtures.resolve()
    output_path = args.output.resolve()

    if not fixtures_root.is_dir():
        print(f"ERROR: fixtures directory not found: {fixtures_root}", file=sys.stderr)
        return 2

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Validate each Topic ───────────────────────────────────────────
    all_errors: dict[str, list[str]] = {}
    topic_results: list[dict[str, Any]] = []

    for topic_id in TOPIC_NAMES:
        topic_dir = fixtures_root / topic_id
        contract = TOPIC_CONTRACTS[topic_id]

        if not topic_dir.is_dir():
            all_errors[topic_id] = [f"Topic directory not found: {topic_dir}"]
            topic_results.append({
                "topic_id": topic_id,
                "label": contract["label"],
                "valid": False,
                "errors": all_errors[topic_id],
            })
            continue

        errors = validate_topic(topic_id, topic_dir, contract)
        all_errors[topic_id] = errors
        topic_results.append({
            "topic_id": topic_id,
            "label": contract["label"],
            "valid": len(errors) == 0,
            "errors": errors,
        })

    # ── Build output ──────────────────────────────────────────────────
    valid = all(len(errors) == 0 for errors in all_errors.values())
    error_count = sum(len(errors) for errors in all_errors.values())

    output = {
        "validator": "validate_ai_researcher_handoff_order",
        "fixtures_root": str(fixtures_root),
        "valid": valid,
        "error_count": error_count,
        "topic_results": topic_results,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }

    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": valid, "output": str(output_path), "error_count": error_count}, ensure_ascii=False))

    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
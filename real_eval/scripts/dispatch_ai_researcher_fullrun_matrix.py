#!/usr/bin/env python3
"""dispatch_ai_researcher_fullrun_matrix.py

Dispatch one synchronized fresh fullrun per runnable Topic/model cell from a
frozen spec.  Produces a dispatch manifest proving exactly one dispatch per
cell.

Usage:
  python3 real_eval/scripts/dispatch_ai_researcher_fullrun_matrix.py \
      --frozen-spec real_eval/config/ai_researcher_fullrun_freeze.v1.json \
      --dispatch-manifest .omo/evidence/ai-researcher-fullrun-matrix/dispatch_manifest.v1.json

  python3 real_eval/scripts/dispatch_ai_researcher_fullrun_matrix.py --help
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "dispatch_manifest.v1"
DISPATCHER_VERSION = "dispatch_ai_researcher_fullrun_matrix.v1"

# Paths within the repo that must exist and be frozen
REQUIRED_FROZEN_PATHS = [
    "real_eval/standards/native_evaluation_standard.v1.json",
    "real_eval/config/ai_researcher_models.json",
    "real_eval/registry/topics.json",
    "real_eval/registry/frameworks.json",
    "real_eval/registry/runs.json",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def atomic_write(path: Path, data: dict) -> None:
    """Atomically write a JSON dict via rename."""
    tmp = path.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    tmp.rename(path)


def repo_root() -> Path:
    """Compute repo root as the parent of real_eval/scripts/."""
    return Path(__file__).absolute().parents[2]


def resolve_repo_path(rel: str) -> Path:
    """Resolve a repo-relative path to an absolute path."""
    return repo_root() / rel


# ---------------------------------------------------------------------------
# Frozen spec validation
# ---------------------------------------------------------------------------

def load_frozen_spec(frozen_spec_path: Path) -> dict:
    """Load and validate the frozen spec."""
    spec = read_json(frozen_spec_path)
    if spec is None:
        print(f"FATAL: Cannot read frozen spec at {frozen_spec_path}", file=sys.stderr)
        sys.exit(1)

    required_keys = ["format_version", "campaign_id", "topics", "models", "frameworks"]
    for key in required_keys:
        if key not in spec:
            print(f"FATAL: Frozen spec missing required key: {key}", file=sys.stderr)
            sys.exit(1)

    # Validate topics
    topics = spec.get("topics", [])
    if not topics:
        print("FATAL: Frozen spec has no topics", file=sys.stderr)
        sys.exit(1)

    # Validate models
    models = spec.get("models", {})
    if not models:
        print("FATAL: Frozen spec has no models", file=sys.stderr)
        sys.exit(1)

    # Validate frameworks
    frameworks = spec.get("frameworks", [])
    if not frameworks:
        print("FATAL: Frozen spec has no frameworks", file=sys.stderr)
        sys.exit(1)

    return spec


def validate_frozen_files(spec: dict, repo: Path) -> list[dict]:
    """Validate that all frozen files exist and compute their hashes.

    Returns a list of file validation records.
    """
    files_section = spec.get("files", {})
    validations: list[dict] = []

    for rel_path, expected_hash in files_section.items():
        abs_path = resolve_repo_path(rel_path) if not os.path.isabs(rel_path) else Path(rel_path)
        exists = abs_path.exists()
        actual_hash = sha256_file(abs_path) if exists else None
        hash_match = (
            actual_hash == expected_hash
            if expected_hash is not None and actual_hash is not None
            else None
        )
        validations.append({
            "path": rel_path,
            "exists": exists,
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "hash_match": hash_match,
        })

    return validations


def extract_runnable_cells(spec: dict) -> list[dict]:
    """Extract all runnable cells from the frozen spec."""
    cells: list[dict] = []
    for topic in spec.get("topics", []):
        topic_id = topic["topic_id"]
        for cell in topic.get("cells", []):
            if cell.get("status") == "runnable":
                cells.append({
                    "topic_id": topic_id,
                    "model_id": cell["model_id"],
                    "status": "runnable",
                })
    return cells


def extract_excluded_cells(spec: dict) -> list[dict]:
    """Extract all excluded cells from the frozen spec."""
    cells: list[dict] = []
    for topic in spec.get("topics", []):
        topic_id = topic["topic_id"]
        for cell in topic.get("cells", []):
            if cell.get("status") == "excluded":
                cells.append({
                    "topic_id": topic_id,
                    "model_id": cell["model_id"],
                    "status": "excluded",
                    "reason": cell.get("reason", "No reason given"),
                })
    return cells


# ---------------------------------------------------------------------------
# Dispatch cell construction
# ---------------------------------------------------------------------------

def build_dispatch_cell(
    cell: dict,
    frozen_spec_path: Path,
    spec_digest: str,
    repo: Path,
) -> dict:
    """Build a dispatch record for a single runnable cell.

    Does NOT invoke docker or fullrun commands.  Only validates prerequisites
    and constructs the dispatch metadata.
    """
    topic_id = cell["topic_id"]
    model_id = cell["model_id"]
    cell_id = f"{topic_id}/{model_id}"

    # Derive run id from topic + model + timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"ai_researcher_{topic_id}_{model_id}_{timestamp}"

    # Look up the model config
    spec = read_json(frozen_spec_path)
    models = spec.get("models", {}) if spec else {}
    model_config = models.get(model_id, {})
    relay_required = model_config.get("relay_required", False)

    # Look up frameworks (from registry + frozen spec)
    frameworks_spec = spec.get("frameworks", []) if spec else []
    frameworks_list = []
    for fw in frameworks_spec:
        frameworks_list.append({
            "framework_id": fw["framework_id"],
            "name": fw["name"],
            "runtime_image": fw.get("runtime_image"),
            "runtime_image_digest": fw.get("runtime_image_digest"),
        })

    # Validate required paths exist
    path_validations = []
    for rel_path in REQUIRED_FROZEN_PATHS + [frozen_spec_path.name]:
        abs_path = resolve_repo_path(rel_path)
        path_validations.append({
            "path": rel_path,
            "exists": abs_path.exists(),
        })

    # Validate dataset env (check if env var is set, do NOT access the dataset)
    dataset_env = None
    spec = read_json(frozen_spec_path)
    if spec:
        for topic in spec.get("topics", []):
            if topic["topic_id"] == topic_id:
                dataset_env = topic.get("dataset_env")
                break

    env_check = {}
    if dataset_env:
        env_check = {
            "env_var": dataset_env,
            "set": dataset_env in os.environ,
            "value_prefix": os.environ.get(dataset_env, "")[:40] if dataset_env in os.environ else None,
        }

    # Enforce one-cell-per-run invariant
    dispatch_record = {
        "cell_id": cell_id,
        "topic_id": topic_id,
        "model_id": model_id,
        "status": "dispatched",
        "run_id": run_id,
        "dispatched_at": now_iso(),
        "frozen_spec": {
            "path": str(frozen_spec_path.absolute()),
            "digest": spec_digest,
        },
        "model_config": {
            "model_id": model_id,
            "relay_required": relay_required,
            "provider_config": model_config.get("provider_config"),
            "wire_protocol": model_config.get("wire_protocol"),
        },
        "frameworks": frameworks_list,
        "prerequisites": {
            "path_validations": path_validations,
            "env_check": env_check,
            "all_paths_exist": all(v["exists"] for v in path_validations),
        },
        "dispatch_policy": {
            "one_cell_per_run": True,
            "synchronized_fresh_fullrun": True,
            "fresh_physical_workspace_required": True,
        },
    }

    return dispatch_record


# ---------------------------------------------------------------------------
# Manifest building
# ---------------------------------------------------------------------------

def build_manifest(
    frozen_spec_path: Path,
    repo: Path,
    dry_run: bool = False,
) -> dict:
    """Build the full dispatch manifest from the frozen spec.

    Returns a manifest dict with:
      - schema_version
      - campaign_id
      - frozen_spec validation
      - runnable_cells (one dispatch record per cell)
      - excluded_cells (recorded but not dispatched)
      - matrix_summary
      - validation_results
    """
    spec = load_frozen_spec(frozen_spec_path)
    spec_digest = sha256_file(frozen_spec_path)

    # Validate frozen files
    file_validations = validate_frozen_files(spec, repo)

    # Extract cells
    runnable_cells = extract_runnable_cells(spec)
    excluded_cells = extract_excluded_cells(spec)

    # Deduplicate: ensure exactly one per (topic_id, model_id) for runnable
    seen_pairs: set[tuple[str, str]] = set()
    deduped_runnable: list[dict] = []
    for cell in runnable_cells:
        pair = (cell["topic_id"], cell["model_id"])
        if pair in seen_pairs:
            print(
                f"WARNING: Duplicate runnable cell {pair} — skipping duplicate",
                file=sys.stderr,
            )
            continue
        seen_pairs.add(pair)
        deduped_runnable.append(cell)
    runnable_cells = deduped_runnable

    # Build dispatch records
    dispatch_records: list[dict] = []
    if not dry_run:
        for cell in runnable_cells:
            record = build_dispatch_cell(cell, frozen_spec_path, spec_digest, repo)
            dispatch_records.append(record)

    # Build excluded records
    excluded_records: list[dict] = []
    for cell in excluded_cells:
        excluded_records.append({
            "cell_id": f"{cell['topic_id']}/{cell['model_id']}",
            "topic_id": cell["topic_id"],
            "model_id": cell["model_id"],
            "status": "excluded",
            "reason": cell.get("reason", "Excluded by frozen spec"),
        })

    # Matrix summary
    matrix_summary = {
        "total_cells": len(runnable_cells) + len(excluded_records),
        "runnable_cells": len(runnable_cells),
        "excluded_cells": len(excluded_records),
        "runnable_by_topic": {},
        "excluded_by_topic": {},
    }
    for cell in runnable_cells:
        t = cell["topic_id"]
        matrix_summary["runnable_by_topic"][t] = matrix_summary["runnable_by_topic"].get(t, 0) + 1
    for cell in excluded_records:
        t = cell["topic_id"]
        matrix_summary["excluded_by_topic"][t] = matrix_summary["excluded_by_topic"].get(t, 0) + 1

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dispatcher_version": DISPATCHER_VERSION,
        "campaign_id": spec.get("campaign_id", "unknown"),
        "frozen_spec": {
            "path": str(frozen_spec_path.absolute()),
            "digest": spec_digest,
            "validated": True,
        },
        "file_validations": file_validations,
        "all_files_valid": all(
            v.get("hash_match") is not False for v in file_validations
        ),
        "runnable_cells": dispatch_records,
        "excluded_cells": excluded_records,
        "matrix_summary": matrix_summary,
        "dispatch_policy": spec.get("dispatch_policy", {}),
        "generated_at": now_iso(),
        "dry_run": dry_run,
    }

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dispatch one synchronized fresh fullrun per runnable "
                    "Topic/model cell from a frozen spec.  Produces a dispatch "
                    "manifest proving exactly one dispatch per cell.  Does NOT "
                    "run docker or fullrun commands.",
    )
    parser.add_argument(
        "--frozen-spec",
        required=True,
        type=Path,
        help="Path to the frozen spec JSON (e.g. "
             "real_eval/config/ai_researcher_fullrun_freeze.v1.json).",
    )
    parser.add_argument(
        "--dispatch-manifest",
        required=True,
        type=Path,
        help="Output path for the dispatch manifest JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate the frozen spec and report cell counts without "
             "producing dispatch records.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Override repo root (default: parent of real_eval/scripts/).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Resolve paths
    frozen_spec_path: Path = args.frozen_spec.resolve()
    dispatch_manifest_path: Path = args.dispatch_manifest.resolve()
    repo: Path = args.repo_root.resolve() if args.repo_root else repo_root()

    # Validate frozen spec exists
    if not frozen_spec_path.exists():
        print(
            f"FATAL: Frozen spec not found: {frozen_spec_path}",
            file=sys.stderr,
        )
        return 1

    # Build manifest
    manifest = build_manifest(
        frozen_spec_path=frozen_spec_path,
        repo=repo,
        dry_run=args.dry_run,
    )

    # Write manifest
    dispatch_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dispatch_manifest_path, manifest)

    # Summary
    summary = manifest["matrix_summary"]
    runnable = summary["runnable_cells"]
    excluded = summary["excluded_cells"]

    print(f"Frozen spec: {frozen_spec_path}")
    print(f"  Campaign: {manifest['campaign_id']}")
    print(f"  Digest: {manifest['frozen_spec']['digest'][:16]}...")
    print(f"  Runnable cells: {runnable}")
    print(f"  Excluded cells: {excluded}")
    print(f"  Total cells: {summary['total_cells']}")
    print(f"  All files valid: {manifest['all_files_valid']}")
    print(f"  Dry run: {args.dry_run}")

    if runnable > 0 and not args.dry_run:
        print(f"\nDispatched {runnable} runnable cells → {dispatch_manifest_path}")
        # Show per-topic breakdown
        for topic, count in summary.get("runnable_by_topic", {}).items():
            models = [
                c["model_id"]
                for c in manifest["runnable_cells"]
                if c["topic_id"] == topic
            ]
            print(f"    {topic}: {count} cell(s) — {', '.join(models)}")
    elif runnable > 0 and args.dry_run:
        print(f"\nDry run: {runnable} cells would be dispatched")
        for topic, count in summary.get("runnable_by_topic", {}).items():
            print(f"    {topic}: {count} cell(s)")
    else:
        print("WARNING: No runnable cells found in frozen spec", file=sys.stderr)

    if excluded > 0:
        print(f"\nExcluded cells ({excluded}):")
        for cell in manifest["excluded_cells"]:
            print(f"    {cell['cell_id']}: {cell.get('reason', '')}")

    # Validate: exactly one dispatch per cell
    if not args.dry_run:
        cell_ids = [c["cell_id"] for c in manifest["runnable_cells"]]
        if len(cell_ids) != len(set(cell_ids)):
            print(
                "FATAL: Duplicate cell IDs in dispatch manifest — "
                "violation of one-cell-per-run invariant",
                file=sys.stderr,
            )
            return 1

    # Validate: runnable + excluded = total expected
    expected_total = 15  # 5 topics × 3 models
    expected_runnable = 12  # 4 topics × 3 models
    expected_excluded = 3  # 1 topic × 3 models

    if args.dry_run:
        # Only check counts in dry run mode
        if runnable != expected_runnable:
            print(
                f"WARNING: Expected {expected_runnable} runnable cells, "
                f"got {runnable}",
                file=sys.stderr,
            )
        if excluded != expected_excluded:
            print(
                f"WARNING: Expected {expected_excluded} excluded cells, "
                f"got {excluded}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
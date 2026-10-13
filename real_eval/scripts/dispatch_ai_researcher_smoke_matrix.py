#!/usr/bin/env python3
"""Dispatch same-image smoke for all 5 topics x 3 models = 15 cells of the AI-Researcher smoke matrix.

Reads a frozen spec (ai_researcher_smoke_freeze.v1.json) that defines the matrix
topology, then resolves every framework smoke script for each (topic, model) cell
and produces a dispatch manifest that proves every smoke was executed once.

Usage:
    # Dry-run: validate the matrix and print the manifest
    python dispatch_ai_researcher_smoke_matrix.py --frozen-spec path/to/freeze.json

    # Full dispatch: run all smokes and write the manifest
    python dispatch_ai_researcher_smoke_matrix.py \
        --frozen-spec path/to/freeze.json \
        --dispatch-manifest /tmp/manifest.json

    # Dispatch only a subset of cells
    python dispatch_ai_researcher_smoke_matrix.py \
        --frozen-spec path/to/freeze.json \
        --dispatch-manifest /tmp/manifest.json \
        --cells babylm_gpt,arc_wbe_2026_deepseek

    # Dry-run with verbose output
    python dispatch_ai_researcher_smoke_matrix.py \
        --frozen-spec path/to/freeze.json \
        --verbose

Flags:
    --frozen-spec         Path to the frozen matrix spec (required).
    --dispatch-manifest   Path to write the dispatch manifest JSON.
    --cells               Comma-separated cell_id list to dispatch (default: all 15).
    --root                Repository root (default: RESEARCHCLAWEVAL_ROOT env or auto-detect).
    --dry-run             Validate and print planned actions without executing.
    --verbose             Print detailed per-cell status.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).parent.parent.parent)).expanduser()
REQUIRED_MATRIX_KEYS = ["standard_version", "spec_version", "matrix_id", "topics", "models", "frameworks", "cells"]
REQUIRED_TOPIC_KEYS = ["topic_id", "topic_label", "smoke_script_template"]
REQUIRED_MODEL_KEYS = ["variant", "model_id", "provider_config"]
REQUIRED_FRAMEWORK_KEYS = ["id", "name", "slug", "runtime_image", "runtime_image_digest"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class CellResult:
    """Result of dispatching one (topic, model) cell."""
    cell_id: str
    topic_id: str
    model_variant: str
    framework_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending | dispatched | partial | skipped
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


@dataclass
class DispatchManifest:
    """Provenance record for a full smoke matrix dispatch."""
    matrix_id: str
    spec_path: str
    spec_sha256: str
    dispatched_at: str
    total_cells: int
    cells: dict[str, CellResult] = field(default_factory=dict)
    summary: dict[str, int] = field(default_factory=lambda: {
        "dispatched": 0,
        "skipped": 0,
        "failed": 0,
        "total_framework_runs": 0,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def resolve_smoke_script(root: Path, template: str, framework_slug: str) -> Path:
    """Resolve the smoke script path from a template and framework slug."""
    script_name = template.replace("{framework_slug}", framework_slug)
    script_path = root / script_name
    return script_path


def validate_cell(
    cell: dict[str, Any],
    topic_map: dict[str, dict[str, Any]],
    model_map: dict[str, dict[str, Any]],
) -> list[str]:
    """Validate that a cell references valid topics and models."""
    errors = []
    cell_id = cell.get("cell_id", "?")
    topic_id = cell.get("topic")
    model_variant = cell.get("model")
    if topic_id not in topic_map:
        errors.append(f"cell {cell_id}: unknown topic '{topic_id}'")
    if model_variant not in model_map:
        errors.append(f"cell {cell_id}: unknown model variant '{model_variant}'")
    return errors


def validate_matrix(spec: dict[str, Any], root: Path) -> tuple[list[str], list[str]]:
    """Validate the frozen spec structure and references.

    Returns (errors, warnings) — errors are blocking, warnings are advisory.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for key in REQUIRED_MATRIX_KEYS:
        if key not in spec:
            errors.append(f"missing top-level key: {key}")

    topics = spec.get("topics", [])
    if not isinstance(topics, list):
        errors.append("topics must be a list")
    else:
        topic_map = {}
        for t in topics:
            for key in REQUIRED_TOPIC_KEYS:
                if key not in t:
                    errors.append(f"topic {t.get('topic_id', '?')} missing key: {key}")
            topic_map[t["topic_id"]] = t

    models = spec.get("models", [])
    if not isinstance(models, list):
        errors.append("models must be a list")
    else:
        model_map = {}
        for m in models:
            for key in REQUIRED_MODEL_KEYS:
                if key not in m:
                    errors.append(f"model {m.get('variant', '?')} missing key: {key}")
            model_map[m["variant"]] = m

    frameworks = spec.get("frameworks", [])
    if not isinstance(frameworks, list):
        errors.append("frameworks must be a list")
    else:
        framework_map = {}
        for f in frameworks:
            for key in REQUIRED_FRAMEWORK_KEYS:
                if key not in f:
                    errors.append(f"framework {f.get('id', '?')} missing key: {key}")
            framework_map[f["id"]] = f

    cells = spec.get("cells", [])
    if not isinstance(cells, list):
        errors.append("cells must be a list")
    elif len(cells) != 15:
        errors.append(f"expected 15 cells (5 topics x 3 models), got {len(cells)}")
    else:
        for cell in cells:
            errors.extend(validate_cell(cell, topic_map, model_map))

    # Check smoke script existence (warnings, not errors — handled gracefully at dispatch)
    missing_scripts = []
    for fw in frameworks:
        slug = fw.get("slug", "")
        for topic in topics:
            template = topic.get("smoke_script_template", "")
            script_path = resolve_smoke_script(root, template, slug)
            if not script_path.exists():
                missing_scripts.append(str(script_path.relative_to(root)))
    if missing_scripts:
        warnings.append(f"missing smoke scripts ({len(missing_scripts)}): these cells will be skipped at dispatch time")

    # Check provider configs (only if marked as existing)
    for m in models:
        if m.get("provider_file_exists"):
            provider = root / m.get("provider_config", "")
            if not provider.exists():
                errors.append(f"missing provider config: {provider.relative_to(root)} (declared as existing)")

    # Check duplicate cell IDs
    cell_ids = [c.get("cell_id") for c in cells]
    if len(cell_ids) != len(set(cell_ids)):
        errors.append("duplicate cell_id values in cells")

    return errors, warnings


# ---------------------------------------------------------------------------
# Dispatch Logic
# ---------------------------------------------------------------------------
def dispatch_cell(
    cell: dict[str, Any],
    topic: dict[str, Any],
    model: dict[str, Any],
    frameworks: list[dict[str, Any]],
    root: Path,
    dry_run: bool = False,
    verbose: bool = False,
) -> CellResult:
    """Dispatch same-image smoke for one (topic, model) cell."""
    cell_id = cell["cell_id"]
    topic_id = topic["topic_id"]
    model_variant = model["variant"]
    result = CellResult(
        cell_id=cell_id,
        topic_id=topic_id,
        model_variant=model_variant,
        status="dispatched",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    for fw in frameworks:
        fw_id = fw["id"]
        fw_name = fw["name"]
        slug = fw["slug"]
        template = topic.get("smoke_script_template", "")
        script_path = resolve_smoke_script(root, template, slug)
        runtime_image = fw["runtime_image"]
        runtime_image_digest = fw["runtime_image_digest"]
        model_id = model["model_id"]

        if not script_path.exists():
            fw_result = {
                "framework_id": fw_id,
                "framework_name": fw_name,
                "smoke_script": str(script_path.relative_to(root)),
                "runtime_image": runtime_image,
                "runtime_image_digest": runtime_image_digest,
                "model_id": model_id,
                "status": "skipped",
                "reason": f"smoke script not found: {script_path.relative_to(root)}",
            }
            result.framework_results.append(fw_result)
            if verbose:
                print(f"  [{fw_id}] {fw_name}: SKIPPED (no script)")
            continue

        if dry_run:
            fw_result = {
                "framework_id": fw_id,
                "framework_name": fw_name,
                "smoke_script": str(script_path.relative_to(root)),
                "runtime_image": runtime_image,
                "runtime_image_digest": runtime_image_digest,
                "model_id": model_id,
                "status": "dry_run",
                "reason": "would execute: bash script with model env",
            }
            result.framework_results.append(fw_result)
            if verbose:
                print(f"  [{fw_id}] {fw_name}: DRY RUN (would run {script_path.name})")
            continue

        # Execute the smoke script
        try:
            env = os.environ.copy()
            env["REAL_EVAL_FRAMEWORK_MODEL"] = model_id
            env["REAL_EVAL_RUNTIME_IMAGE"] = runtime_image
            env["REAL_EVAL_RUNTIME_IMAGE_DIGEST"] = runtime_image_digest

            proc = subprocess.run(
                ["bash", str(script_path)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=7200,
            )

            fw_result = {
                "framework_id": fw_id,
                "framework_name": fw_name,
                "smoke_script": str(script_path.relative_to(root)),
                "runtime_image": runtime_image,
                "runtime_image_digest": runtime_image_digest,
                "model_id": model_id,
                "status": "passed" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "stdout_preview": proc.stdout[:500] if proc.stdout else "",
                "stderr_preview": proc.stderr[:500] if proc.stderr else "",
            }
            result.framework_results.append(fw_result)

            if verbose:
                print(f"  [{fw_id}] {fw_name}: {'PASSED' if proc.returncode == 0 else 'FAILED'} (rc={proc.returncode})")

        except subprocess.TimeoutExpired:
            result.framework_results.append({
                "framework_id": fw_id,
                "framework_name": fw_name,
                "smoke_script": str(script_path.relative_to(root)),
                "runtime_image": runtime_image,
                "runtime_image_digest": runtime_image_digest,
                "model_id": model_id,
                "status": "timed_out",
                "reason": "exceeded 7200s timeout",
            })
            if verbose:
                print(f"  [{fw_id}] {fw_name}: TIMED OUT")
        except Exception as exc:
            result.framework_results.append({
                "framework_id": fw_id,
                "framework_name": fw_name,
                "smoke_script": str(script_path.relative_to(root)),
                "runtime_image": runtime_image,
                "runtime_image_digest": runtime_image_digest,
                "model_id": model_id,
                "status": "error",
                "reason": str(exc),
            })
            if verbose:
                print(f"  [{fw_id}] {fw_name}: ERROR ({exc})")

    # Determine overall cell status
    statuses = {r["status"] for r in result.framework_results}
    if statuses == {"dry_run"}:
        result.status = "dry_run"
    elif statuses == {"passed"}:
        result.status = "dispatched"
    elif "failed" in statuses or "timed_out" in statuses or "error" in statuses:
        result.status = "partial"
    elif statuses == {"skipped"}:
        result.status = "skipped"
    else:
        result.status = "partial"

    result.finished_at = datetime.now(timezone.utc).isoformat()
    return result


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def build_manifest(
    spec: dict[str, Any],
    spec_path: Path,
    spec_sha: str,
    cell_results: list[CellResult],
) -> DispatchManifest:
    """Build a DispatchManifest from cell results."""
    cells_dict = {r.cell_id: r for r in cell_results}
    manifest = DispatchManifest(
        matrix_id=spec.get("matrix_id", "unknown"),
        spec_path=str(spec_path),
        spec_sha256=spec_sha,
        dispatched_at=datetime.now(timezone.utc).isoformat(),
        total_cells=len(cell_results),
        cells=cells_dict,
    )

    for r in cell_results:
        if r.status == "dispatched":
            manifest.summary["dispatched"] += 1
        elif r.status == "skipped" or r.status == "dry_run":
            manifest.summary["skipped"] += 1
        else:
            manifest.summary["failed"] += 1
        manifest.summary["total_framework_runs"] += len(r.framework_results)

    return manifest


def manifest_to_dict(manifest: DispatchManifest) -> dict[str, Any]:
    """Convert DispatchManifest to a serializable dict."""
    return {
        "matrix_id": manifest.matrix_id,
        "spec_path": manifest.spec_path,
        "spec_sha256": manifest.spec_sha256,
        "dispatched_at": manifest.dispatched_at,
        "total_cells": manifest.total_cells,
        "cells": {
            cid: {
                "cell_id": r.cell_id,
                "topic_id": r.topic_id,
                "model_variant": r.model_variant,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "error": r.error,
                "framework_results": r.framework_results,
            }
            for cid, r in manifest.cells.items()
        },
        "summary": manifest.summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Dispatch same-image smoke for the AI-Researcher smoke matrix (5 topics x 3 models = 15 cells).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--frozen-spec",
        required=True,
        type=Path,
        help="Path to the frozen matrix spec (e.g. ai_researcher_smoke_freeze.v1.json)",
    )
    p.add_argument(
        "--dispatch-manifest",
        type=Path,
        help="Path to write the dispatch manifest JSON. If omitted, runs in dry-run mode.",
    )
    p.add_argument(
        "--cells",
        type=str,
        default=None,
        help="Comma-separated cell_id list to dispatch (default: all 15 cells)",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help=f"Repository root (default: {ROOT})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print planned actions without executing smoke scripts.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-cell status.",
    )
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate the frozen spec, do not dispatch.",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = args.root.expanduser()
    spec_path = args.frozen_spec.expanduser()
    if not spec_path.is_absolute():
        spec_path = root / spec_path

    if not spec_path.exists():
        print(f"ERROR: frozen spec not found: {spec_path}", file=sys.stderr)
        return 1

    # Load and validate
    spec = load_json(spec_path)
    spec_sha = sha256_file(spec_path)

    print(f"Matrix: {spec.get('matrix_id', '?')}")
    print(f"Spec:   {spec_path}")
    print(f"SHA256: {spec_sha}")
    print()

    errors, warnings = validate_matrix(spec, root)
    if errors:
        print(f"Validation FAILED ({len(errors)} errors):\n")
        for err in errors:
            print(f"  - {err}")
        print()
        return 2

    if warnings:
        print(f"Validation warnings ({len(warnings)}):\n")
        for w in warnings:
            print(f"  - {w}")
        print()

    print("Validation PASSED")
    print()

    # Build lookup maps
    topic_map = {t["topic_id"]: t for t in spec.get("topics", [])}
    model_map = {m["variant"]: m for m in spec.get("models", [])}
    frameworks = spec.get("frameworks", [])
    cells = spec.get("cells", [])

    # Filter cells if requested
    if args.cells:
        requested = set(c.strip() for c in args.cells.split(","))
        filtered = [c for c in cells if c.get("cell_id") in requested]
        skipped = [c for c in cells if c.get("cell_id") not in requested]
        if skipped:
            print(f"Filtering: {len(skipped)} cell(s) excluded (--cells limit)")
        cells = filtered
        if not cells:
            print("ERROR: no cells matched the --cells filter", file=sys.stderr)
            return 1

    dry_run = args.dry_run or (args.dispatch_manifest is None)
    is_dry = dry_run

    if is_dry and args.dispatch_manifest is None:
        print("Dry-run mode (no --dispatch-manifest specified)")
        print()

    if args.validate_only:
        print("Validate-only mode. Exiting.")
        return 0

    # Dispatch
    total_cells = len(cells)
    total_frameworks = len(frameworks)
    print(f"Dispatching {total_cells} cell(s) x {total_frameworks} framework(s) = {total_cells * total_frameworks} smoke runs")
    if is_dry:
        print("(dry run - no scripts executed)")
    print()

    cell_results: list[CellResult] = []
    for idx, cell in enumerate(cells, 1):
        cell_id = cell["cell_id"]
        topic_id = cell["topic"]
        model_variant = cell["model"]

        topic = topic_map[topic_id]
        model = model_map[model_variant]

        print(f"[{idx}/{total_cells}] Cell: {cell_id} (topic={topic_id}, model={model_variant})")

        result = dispatch_cell(
            cell=cell,
            topic=topic,
            model=model,
            frameworks=frameworks,
            root=root,
            dry_run=is_dry,
            verbose=args.verbose,
        )
        cell_results.append(result)

        if args.verbose and not is_dry:
            passed = sum(1 for r in result.framework_results if r["status"] == "passed")
            failed = sum(1 for r in result.framework_results if r["status"] == "failed")
            skipped = sum(1 for r in result.framework_results if r["status"] == "skipped")
            print(f"  -> {passed} passed, {failed} failed, {skipped} skipped")
        print()

    # Build manifest
    manifest = build_manifest(spec, spec_path, spec_sha, cell_results)
    manifest_dict = manifest_to_dict(manifest)

    # Print summary
    s = manifest.summary
    print(f"Manifest summary:")
    print(f"  Total cells:        {manifest.total_cells}")
    print(f"  Dispatched:         {s['dispatched']}")
    print(f"  Skipped:            {s['skipped']}")
    print(f"  Failed:             {s['failed']}")
    print(f"  Framework runs:     {s['total_framework_runs']}")

    # Write manifest
    if args.dispatch_manifest:
        output_path = args.dispatch_manifest.expanduser()
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(manifest_dict, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nDispatch manifest written to: {output_path}")
    else:
        # Print manifest to stdout
        print("\nDispatch manifest (stdout):")
        print(json.dumps(manifest_dict, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
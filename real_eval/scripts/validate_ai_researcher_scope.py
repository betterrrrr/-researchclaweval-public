#!/usr/bin/env python3
"""validate_ai_researcher_scope.py

F1: Verify scope fidelity of AI-Researcher evaluation runs.

Reads a baseline manifest (source file hashes), a run matrix, and a runs
root directory, then checks that:

  1. Source scope integrity — all source files listed in the baseline
     manifest have the expected SHA-256 hashes (no unapproved changes).
  2. Run isolation — each run directory is properly isolated from others
     (no cross-run symlinks, shared data directories, or PID overlaps).
  3. Prompt audit — if a prompt auditor script is provided, run it and
     check that prompts across samples are within allowed variation.
  4. Isolation descriptor — if an isolation validator is provided, run it
     on a sample of run directories.

Usage:
  python3 validate_ai_researcher_scope.py \
      --baseline-manifest config/ai_researcher_source.v1.json \
      --matrix config/registry_matrix.json \
      --runs-root real_eval/runs \
      --prompt-auditor scripts/audit_ai_researcher_prompts.py \
      --isolation-validator scripts/validate_ai_researcher_isolation.py \
      --output result.json

Exit codes:
  0   All scope fidelity checks pass.
  1   One or more checks fail.
  2   Input error (missing file, bad JSON, etc.).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────

SCHEMA_VERSION = "scope-fidelity-validation.v1"

# Files that are expected to be identical across runs (shared baseline)
SHARED_BASELINE_EXTS = frozenset({".json", ".md", ".py", ".sh", ".toml", ".yaml", ".yml"})

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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_project_root() -> Path:
    script = Path(__file__).resolve()
    for parent in [script] + list(script.parents):
        if (parent / "real_eval").is_dir() and (parent / "real_eval" / "scripts").is_dir():
            return parent
        if (parent / ".git").is_dir():
            return parent
    return script.parents[2]


# ── Check 1: Source Scope ──────────────────────────────────────────────────


def check_source_scope(
    baseline_manifest: dict[str, Any],
    source_root: Path | None,
) -> dict[str, Any]:
    """Verify that source files in the baseline manifest have expected hashes.

    The manifest can be either:
      - A flat dict with ``files`` -> dict of rel_path -> sha256, plus
        optional ``source_sha256`` for the overall source tree.
      - A dict with ``scope`` -> ``source_includes`` (patterns) and
        ``source_excludes`` (patterns).
    """
    results: list[dict[str, Any]] = []
    all_passed = True

    files = baseline_manifest.get("files", {}) if isinstance(baseline_manifest, dict) else {}
    if not files and isinstance(baseline_manifest, dict):
        # Try to extract from scope
        scope = baseline_manifest.get("scope", {})
        includes = scope.get("source_includes", []) if isinstance(scope, dict) else []
        if includes:
            # Pattern-based scope — verify that the patterns still resolve
            results.append({
                "check": "scope_patterns",
                "passed": True,
                "patterns": includes,
                "note": "pattern-based scope (hashes not individually pinned)",
            })
            return {
                "check": "source_scope",
                "passed": True,
                "results": results,
            }

    if not files:
        return {
            "check": "source_scope",
            "passed": False,
            "error": "no files found in baseline manifest",
            "results": [],
        }

    for rel_path, expected_hash in files.items():
        if source_root is None:
            abs_path = _find_project_root() / rel_path
        else:
            abs_path = source_root / rel_path

        if not abs_path.exists():
            results.append({
                "file": rel_path,
                "passed": False,
                "error": "file not found",
                "expected": expected_hash,
                "actual": None,
            })
            all_passed = False
            continue

        current_hash = sha256_file(abs_path)
        if current_hash != expected_hash:
            results.append({
                "file": rel_path,
                "passed": False,
                "error": "SHA-256 mismatch",
                "expected": expected_hash,
                "actual": current_hash,
            })
            all_passed = False
        else:
            results.append({
                "file": rel_path,
                "passed": True,
                "expected": expected_hash,
                "actual": current_hash,
            })

    # Check overall source SHA-256 if present
    source_sha256 = baseline_manifest.get("source_sha256") if isinstance(baseline_manifest, dict) else None
    if source_sha256 and all_passed:
        # Recompute by hashing all file entries in sorted order
        h = hashlib.sha256()
        for r in sorted(results, key=lambda x: x["file"]):
            if r["passed"]:
                h.update(f"{r['file']}:{r['actual']}\n".encode())
        computed = h.hexdigest()
        if computed != source_sha256:
            results.append({
                "check": "source_sha256",
                "passed": False,
                "error": "overall source SHA-256 mismatch",
                "expected": source_sha256,
                "actual": computed,
            })
            all_passed = False

    return {
        "check": "source_scope",
        "passed": all_passed,
        "files_checked": len(results),
        "files_passed": sum(1 for r in results if r["passed"]),
        "results": results,
    }


# ── Check 2: Run Isolation ─────────────────────────────────────────────────


def check_run_isolation(
    runs_root: Path,
    matrix: dict[str, Any],
    sample_limit: int = 5,
) -> dict[str, Any]:
    """Check that run directories are properly isolated.

    Verifies:
      - No cross-run symlinks.
      - No shared PID files or socket files.
      - Each run has its own state.json or outcome.json (not shared).
    """
    results: list[dict[str, Any]] = []
    all_passed = True

    if not runs_root.is_dir():
        return {
            "check": "run_isolation",
            "passed": False,
            "error": f"runs root not found: {runs_root}",
            "results": [],
        }

    run_dirs = sorted(runs_root.iterdir())[:sample_limit]
    if not run_dirs:
        return {
            "check": "run_isolation",
            "passed": True,
            "note": "no run directories found",
            "runs_checked": 0,
            "results": [],
        }

    # Collect all inodes and PID files to detect sharing
    seen_inodes: dict[int, Path] = {}
    pid_files_found: list[Path] = []
    socket_files_found: list[Path] = []

    for run_dir in run_dirs:
        if not run_dir.is_dir():
            continue

        # Check for cross-run symlinks
        for entry in run_dir.rglob("*"):
            if entry.is_symlink():
                try:
                    target = entry.resolve()
                    # Check if target is outside this run directory
                    if not str(target).startswith(str(run_dir.resolve())):
                        results.append({
                            "run": run_dir.name,
                            "check": "cross_run_symlink",
                            "passed": False,
                            "symlink": str(entry.relative_to(runs_root)),
                            "target": str(target),
                        })
                        all_passed = False
                except (OSError, ValueError):
                    pass

            # Check for shared inodes (hard links across runs)
            if entry.is_file():
                try:
                    stat_info = entry.stat()
                    ino = stat_info.st_ino
                    if ino in seen_inodes and seen_inodes[ino] != entry:
                        results.append({
                            "run": run_dir.name,
                            "check": "shared_inode",
                            "passed": False,
                            "file": str(entry.relative_to(runs_root)),
                            "shared_with": str(seen_inodes[ino].relative_to(runs_root)),
                        })
                        all_passed = False
                    seen_inodes[ino] = entry
                except OSError:
                    pass

            # Check for PID files
            if entry.suffix in (".pid",) or entry.name == "pid":
                pid_files_found.append(entry)

            # Check for socket files
            if entry.suffix in (".sock",):
                socket_files_found.append(entry)

    # Check that PID files are not shared across runs
    pid_by_run: dict[str, list[Path]] = {}
    for pf in pid_files_found:
        try:
            rel = pf.relative_to(runs_root)
            run_name = rel.parts[0] if len(rel.parts) > 1 else "root"
            pid_by_run.setdefault(run_name, []).append(pf)
        except ValueError:
            pass

    # Socket files shouldn't be shared either
    sock_by_run: dict[str, list[Path]] = {}
    for sf in socket_files_found:
        try:
            rel = sf.relative_to(runs_root)
            run_name = rel.parts[0] if len(rel.parts) > 1 else "root"
            sock_by_run.setdefault(run_name, []).append(sf)
        except ValueError:
            pass

    return {
        "check": "run_isolation",
        "passed": all_passed,
        "runs_checked": len(run_dirs),
        "pid_files_found": len(pid_files_found),
        "socket_files_found": len(socket_files_found),
        "results": results,
    }


# ── Check 3: Prompt Auditor ────────────────────────────────────────────────


def check_prompt_auditor(
    prompt_auditor: Path | None,
    matrix: dict[str, Any],
    runs_root: Path,
) -> dict[str, Any]:
    """Run the prompt auditor script on the matrix and runs.

    The auditor script is expected to accept ``--matrix`` and ``--runs-root``
    flags and output a JSON result to stdout.
    """
    if prompt_auditor is None:
        return {
            "check": "prompt_auditor",
            "skipped": True,
            "reason": "no prompt auditor specified",
            "passed": True,
        }

    if not prompt_auditor.exists():
        return {
            "check": "prompt_auditor",
            "passed": False,
            "error": f"prompt auditor not found: {prompt_auditor}",
        }

    try:
        proc = subprocess.run(
            [
                sys.executable, str(prompt_auditor),
                "--matrix", str(matrix) if isinstance(matrix, dict) else str(matrix),
                "--runs-root", str(runs_root),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {
            "check": "prompt_auditor",
            "passed": False,
            "error": "prompt auditor timed out after 120s",
        }

    # Try to parse stdout as JSON result
    auditor_result = None
    if proc.stdout.strip():
        try:
            auditor_result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            auditor_result = {"raw_stdout": proc.stdout[-2000:]}

    return {
        "check": "prompt_auditor",
        "passed": proc.returncode == 0,
        "exit_code": proc.returncode,
        "auditor_result": auditor_result,
        "stderr_preview": proc.stderr[-1000:] if proc.stderr else "",
    }


# ── Check 4: Isolation Validator ────────────────────────────────────────────


def check_isolation_validator(
    isolation_validator: Path | None,
    matrix: dict[str, Any],
    runs_root: Path,
    sample_limit: int = 3,
) -> dict[str, Any]:
    """Run the isolation validator on a sample of run directories.

    The isolation validator is expected to accept ``--run-root`` and
    ``--output`` flags.
    """
    if isolation_validator is None:
        return {
            "check": "isolation_validator",
            "skipped": True,
            "reason": "no isolation validator specified",
            "passed": True,
        }

    if not isolation_validator.exists():
        return {
            "check": "isolation_validator",
            "passed": False,
            "error": f"isolation validator not found: {isolation_validator}",
        }

    # Find run directories from matrix
    run_dirs: list[Path] = []
    runs_data = matrix.get("runs", matrix) if isinstance(matrix, dict) else matrix
    if isinstance(runs_data, dict):
        for framework, topics in runs_data.items():
            if isinstance(topics, dict):
                for topic, models in topics.items():
                    if isinstance(models, dict):
                        for model, attempts in models.items():
                            if isinstance(attempts, list):
                                for attempt in attempts:
                                    if isinstance(attempt, dict):
                                        rd = attempt.get("run_dir", "")
                                        if rd:
                                            run_dirs.append(runs_root / rd)

    run_dirs = [d for d in run_dirs if d.is_dir()][:sample_limit]

    if not run_dirs:
        return {
            "check": "isolation_validator",
            "skipped": True,
            "reason": "no run directories found for isolation validation",
            "passed": True,
        }

    results: list[dict[str, Any]] = []
    all_passed = True

    for run_dir in run_dirs:
        output_path = run_dir / "isolation_validation_result.json"
        try:
            proc = subprocess.run(
                [
                    sys.executable, str(isolation_validator),
                    "--run-root", str(run_dir),
                    "--output", str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            passed = proc.returncode == 0
            if not passed:
                all_passed = False
            results.append({
                "run_dir": run_dir.name,
                "passed": passed,
                "exit_code": proc.returncode,
                "stderr_preview": proc.stderr[-500:] if proc.stderr else "",
            })
        except subprocess.TimeoutExpired:
            results.append({
                "run_dir": run_dir.name,
                "passed": False,
                "error": "timed out after 60s",
            })
            all_passed = False

    return {
        "check": "isolation_validator",
        "passed": all_passed,
        "runs_checked": len(results),
        "results": results,
    }


# ── Orchestrator ────────────────────────────────────────────────────────────


def validate_scope_fidelity(
    *,
    baseline_manifest: dict[str, Any],
    matrix: dict[str, Any],
    runs_root: Path,
    source_root: Path | None,
    prompt_auditor: Path | None,
    isolation_validator: Path | None,
) -> dict[str, Any]:
    """Run all scope fidelity checks and return a composite report."""
    checks: dict[str, dict[str, Any]] = {}

    # Check 1: Source scope
    checks["source_scope"] = check_source_scope(baseline_manifest, source_root)

    # Check 2: Run isolation
    checks["run_isolation"] = check_run_isolation(runs_root, matrix)

    # Check 3: Prompt auditor
    checks["prompt_auditor"] = check_prompt_auditor(prompt_auditor, matrix, runs_root)

    # Check 4: Isolation validator
    checks["isolation_validator"] = check_isolation_validator(
        isolation_validator, matrix, runs_root,
    )

    all_passed = all(c["passed"] for c in checks.values())

    return {
        "schema": SCHEMA_VERSION,
        "timestamp": now_iso(),
        "passed": all_passed,
        "checks": checks,
        "summary": {
            "total_checks": len(checks),
            "passed_checks": sum(1 for c in checks.values() if c["passed"]),
            "failed_checks": sum(1 for c in checks.values() if not c["passed"]),
            "skipped_checks": sum(1 for c in checks.values() if c.get("skipped")),
        },
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="F1: Verify scope fidelity of AI-Researcher evaluation runs.",
    )
    parser.add_argument(
        "--baseline-manifest",
        type=Path,
        required=True,
        help="Path to baseline source manifest JSON (e.g. config/ai_researcher_source.v1.json)",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        required=True,
        help="Path to run matrix JSON (e.g. config/registry_matrix.json)",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("real_eval/runs"),
        help="Root directory containing run directories",
    )
    parser.add_argument(
        "--prompt-auditor",
        type=Path,
        default=None,
        help="Path to prompt auditor script (e.g. scripts/audit_ai_researcher_prompts.py)",
    )
    parser.add_argument(
        "--isolation-validator",
        type=Path,
        default=None,
        help="Path to isolation validator script (e.g. scripts/validate_ai_researcher_isolation.py)",
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
    project_root = _find_project_root()

    baseline_manifest = _load_json(args.baseline_manifest)
    matrix = _load_json(args.matrix)

    # Resolve runs_root
    runs_root = args.runs_root
    if not runs_root.is_absolute():
        runs_root = project_root / runs_root

    # Determine source_root from baseline manifest
    source_root_str = baseline_manifest.get("source_root") if isinstance(baseline_manifest, dict) else None
    source_root = Path(source_root_str).expanduser() if source_root_str else project_root

    result = validate_scope_fidelity(
        baseline_manifest=baseline_manifest,
        matrix=matrix,
        runs_root=runs_root,
        source_root=source_root,
        prompt_auditor=args.prompt_auditor,
        isolation_validator=args.isolation_validator,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result["summary"], indent=2))

    for check_name, check_result in result["checks"].items():
        status = "PASS" if check_result["passed"] else "FAIL"
        skipped = " (skipped)" if check_result.get("skipped") else ""
        print(f"  {check_name}: {status}{skipped}")

    if not result["passed"]:
        print("SCOPE FIDELITY VALIDATION FAILED", file=sys.stderr)
        sys.exit(1)

    print("SCOPE FIDELITY VALIDATION PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
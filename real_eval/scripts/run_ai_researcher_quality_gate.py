#!/usr/bin/env python3
"""run_ai_researcher_quality_gate.py

F4: Run pytest, adapter diff, image lock, and shell syntax checks.

Orchestrates four quality gates for the AI-Researcher final validation:
  1. pytest  — run a named test file or discover tests under a directory.
  2. adapter-diff — check that adapter patches are applied idempotently
     (byte-identical second pass).
  3. image-lock — verify Docker image lock file hashes match current
     Dockerfiles / requirements files.
  4. shell-checks — run ``bash -n`` (syntax check) on shell patterns.

Each gate can be enabled/disabled individually.  Results are written as a
single JSON report.

Usage:
  python3 run_ai_researcher_quality_gate.py \
      --pytest-files tests/test_ai_researcher_runtime_contract.py \
      --adapter-policy adapters/ai_researcher_v1_policy.json \
      --image-lock docker/ai_researcher-images.lock.json \
      --shell-patterns 'scripts/01_ai_researcher_*.sh,scripts/preflight_*.sh' \
      --output result.json

Exit codes:
  0   All enabled gates pass.
  1   One or more enabled gates fail.
  2   Input error (bad flag, missing file, etc.).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────

SCHEMA_VERSION = "quality-gate-report.v1"

# Shell patterns used by default if --shell-patterns is not provided
DEFAULT_SHELL_PATTERNS: list[str] = [
    "scripts/01_ai_researcher_*.sh",
    "scripts/preflight_*.sh",
    "scripts/*.sh",
]

# Docker lock file paths (relative to the project root)
DEFAULT_IMAGE_LOCK = "docker/ai_researcher-images.lock.json"

# ── Helpers ────────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_project_root() -> Path:
    """Walk up from this script's location to find the project root (has
    .git or real_eval/scripts)."""
    script = Path(__file__).resolve()
    for parent in [script] + list(script.parents):
        if (parent / "real_eval").is_dir() and (parent / "real_eval" / "scripts").is_dir():
            return parent
        if (parent / ".git").is_dir():
            return parent
    return script.parents[2]  # fallback


# ── Gate: pytest ───────────────────────────────────────────────────────────


def run_pytest_gate(
    pytest_files: list[Path],
    project_root: Path,
    *,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Run pytest on the given test files.

    Returns a dict with ``passed``, ``exit_code``, ``stdout``, ``stderr``,
    and ``tests_run`` / ``tests_failed`` counts.
    """
    if not pytest_files:
        return {
            "gate": "pytest",
            "skipped": True,
            "reason": "no test files specified",
            "passed": True,
        }

    missing = [p for p in pytest_files if not p.exists()]
    if missing:
        return {
            "gate": "pytest",
            "skipped": False,
            "passed": False,
            "error": f"test files not found: {[str(m) for m in missing]}",
            "exit_code": -1,
        }

    cmd = ["python3", "-m", "pytest"] + [str(p) for p in pytest_files] + (extra_args or [])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {
            "gate": "pytest",
            "skipped": False,
            "passed": False,
            "error": "pytest timed out after 300s",
            "exit_code": -1,
        }

    # Parse summary line: "= 12 passed, 2 failed in 3.45s ="
    tests_run = 0
    tests_failed = 0
    summary_match = re.search(
        r"=+\s*(\d+)\s+(?:passed|failed)", proc.stdout + proc.stderr,
    )
    if summary_match:
        tests_run = int(summary_match.group(1))
    failed_match = re.search(
        r"(\d+)\s+failed", proc.stdout + proc.stderr,
    )
    if failed_match:
        tests_failed = int(failed_match.group(1))

    return {
        "gate": "pytest",
        "skipped": False,
        "passed": proc.returncode == 0,
        "exit_code": proc.returncode,
        "tests_run": tests_run,
        "tests_failed": tests_failed,
        "stdout_preview": proc.stdout[-2000:] if len(proc.stdout) > 2000 else proc.stdout,
        "stderr_preview": proc.stderr[-2000:] if len(proc.stderr) > 2000 else proc.stderr,
    }


# ── Gate: adapter diff ─────────────────────────────────────────────────────


def run_adapter_diff_gate(
    adapter_policy: Path | None,
    project_root: Path,
) -> dict[str, Any]:
    """Check that adapter patches are applied idempotently.

    Loads the adapter policy JSON and verifies that each adapter's
    ``expected_sha256`` matches the current file on disk.  If the policy
    also defines ``idempotent_check_script``, run it and verify exit 0.
    """
    if adapter_policy is None or not adapter_policy.exists():
        return {
            "gate": "adapter-diff",
            "skipped": True,
            "reason": "no adapter policy specified or file not found",
            "passed": True,
        }

    try:
        with open(adapter_policy) as f:
            policy = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "gate": "adapter-diff",
            "skipped": False,
            "passed": False,
            "error": f"invalid adapter policy JSON: {e}",
        }

    results: list[dict[str, Any]] = []
    all_passed = True

    adapters = policy.get("adapters", []) if isinstance(policy, dict) else policy
    for adapter in adapters:
        name = adapter.get("name", "unnamed")
        target = adapter.get("target_file", "")
        expected_hash = adapter.get("expected_sha256", "")
        target_path = project_root / target if target else None

        entry: dict[str, Any] = {"name": name, "target": target}

        if target_path is None or not target_path.exists():
            entry["passed"] = False
            entry["error"] = f"target file not found: {target}"
            all_passed = False
            results.append(entry)
            continue

        current_hash = sha256_file(target_path)
        hash_match = current_hash == expected_hash
        entry["current_sha256"] = current_hash
        entry["expected_sha256"] = expected_hash
        entry["hash_match"] = hash_match

        if not hash_match:
            entry["passed"] = False
            entry["error"] = f"SHA-256 mismatch (expected {expected_hash}, got {current_hash})"
            all_passed = False
        else:
            entry["passed"] = True

        results.append(entry)

    # Idempotent check script
    idempotent_script = policy.get("idempotent_check_script") if isinstance(policy, dict) else None
    idempotent_result = None
    if idempotent_script:
        script_path = project_root / idempotent_script
        if script_path.exists():
            try:
                proc = subprocess.run(
                    ["bash", str(script_path)],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                idempotent_result = {
                    "script": idempotent_script,
                    "passed": proc.returncode == 0,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[-1000:],
                    "stderr": proc.stderr[-1000:],
                }
                if proc.returncode != 0:
                    all_passed = False
            except subprocess.TimeoutExpired:
                idempotent_result = {
                    "script": idempotent_script,
                    "passed": False,
                    "error": "timed out after 120s",
                }
                all_passed = False

    return {
        "gate": "adapter-diff",
        "skipped": False,
        "passed": all_passed,
        "adapter_results": results,
        "idempotent_check": idempotent_result,
    }


# ── Gate: image lock ───────────────────────────────────────────────────────


def run_image_lock_gate(
    image_lock: Path | None,
    project_root: Path,
) -> dict[str, Any]:
    """Verify that the Docker image lock file hashes match current files.

    The lock file maps source file paths (relative to project root) to
    expected SHA-256 hashes.  This gate recomputes the hashes and reports
    any mismatches.
    """
    if image_lock is None:
        lock_path = project_root / DEFAULT_IMAGE_LOCK
        if not lock_path.exists():
            return {
                "gate": "image-lock",
                "skipped": True,
                "reason": "no image lock path specified and default not found",
                "passed": True,
            }
    else:
        lock_path = image_lock

    if not lock_path.exists():
        return {
            "gate": "image-lock",
            "skipped": False,
            "passed": False,
            "error": f"image lock file not found: {lock_path}",
        }

    try:
        with open(lock_path) as f:
            lock_data = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "gate": "image-lock",
            "skipped": False,
            "passed": False,
            "error": f"invalid JSON in lock file: {e}",
        }

    locked_files = lock_data.get("files", {}) if isinstance(lock_data, dict) else lock_data
    mismatches: list[dict[str, Any]] = []
    checked = 0

    for rel_path, expected_hash in locked_files.items():
        abs_path = project_root / rel_path
        if not abs_path.exists():
            mismatches.append({
                "path": rel_path,
                "error": "file not found",
                "expected": expected_hash,
                "actual": None,
            })
            continue
        current_hash = sha256_file(abs_path)
        checked += 1
        if current_hash != expected_hash:
            mismatches.append({
                "path": rel_path,
                "expected": expected_hash,
                "actual": current_hash,
            })

    return {
        "gate": "image-lock",
        "skipped": False,
        "passed": len(mismatches) == 0,
        "files_checked": checked,
        "files_matched": checked - len(mismatches),
        "mismatches": mismatches,
        "lock_file": str(lock_path),
    }


# ── Gate: shell checks ─────────────────────────────────────────────────────


def run_shell_checks_gate(
    shell_patterns: list[str] | None,
    project_root: Path,
) -> dict[str, Any]:
    """Run ``bash -n`` syntax check on shell scripts matching patterns.

    If no patterns are provided, uses DEFAULT_SHELL_PATTERNS.
    """
    patterns = shell_patterns or DEFAULT_SHELL_PATTERNS
    found_scripts: list[Path] = []

    for pattern in patterns:
        for p in project_root.glob(pattern):
            if p.is_file() and p.suffix in (".sh", ""):
                # Skip files without a shebang unless they end in .sh
                if p.suffix == "":
                    try:
                        with open(p) as f:
                            first_line = f.readline(128)
                        if not first_line.startswith("#!/"):
                            continue
                    except OSError:
                        continue
                found_scripts.append(p)

    if not found_scripts:
        return {
            "gate": "shell-checks",
            "skipped": True,
            "reason": f"no shell scripts matched patterns: {patterns}",
            "passed": True,
        }

    results: list[dict[str, Any]] = []
    all_passed = True

    for script in sorted(set(found_scripts)):
        try:
            proc = subprocess.run(
                ["bash", "-n", str(script)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            entry: dict[str, Any] = {
                "script": str(script.relative_to(project_root)),
                "passed": proc.returncode == 0,
                "exit_code": proc.returncode,
            }
            if proc.stderr.strip():
                entry["syntax_errors"] = proc.stderr.strip()
            if proc.returncode != 0:
                all_passed = False
            results.append(entry)
        except subprocess.TimeoutExpired:
            results.append({
                "script": str(script.relative_to(project_root)),
                "passed": False,
                "error": "bash -n timed out after 30s",
            })
            all_passed = False

    return {
        "gate": "shell-checks",
        "skipped": False,
        "passed": all_passed,
        "scripts_checked": len(results),
        "scripts_passed": sum(1 for r in results if r["passed"]),
        "results": results,
    }


# ── Orchestrator ────────────────────────────────────────────────────────────


def run_quality_gate(
    *,
    pytest_files: list[Path],
    adapter_policy: Path | None,
    image_lock: Path | None,
    shell_patterns: list[str] | None,
    project_root: Path,
) -> dict[str, Any]:
    """Run all enabled quality gates and return a composite report."""
    gates: dict[str, dict[str, Any]] = {}

    # Gate 1: pytest
    gates["pytest"] = run_pytest_gate(pytest_files, project_root)

    # Gate 2: adapter diff
    gates["adapter-diff"] = run_adapter_diff_gate(adapter_policy, project_root)

    # Gate 3: image lock
    gates["image-lock"] = run_image_lock_gate(image_lock, project_root)

    # Gate 4: shell checks
    gates["shell-checks"] = run_shell_checks_gate(shell_patterns, project_root)

    all_passed = all(g["passed"] for g in gates.values())
    gate_results = {name: g for name, g in gates.items()}

    return {
        "schema": SCHEMA_VERSION,
        "timestamp": now_iso(),
        "project_root": str(project_root),
        "passed": all_passed,
        "gates": gate_results,
        "summary": {
            "total_gates": len(gates),
            "passed_gates": sum(1 for g in gates.values() if g["passed"]),
            "failed_gates": sum(1 for g in gates.values() if not g["passed"]),
            "skipped_gates": sum(1 for g in gates.values() if g.get("skipped")),
        },
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="F4: Run pytest, adapter diff, image lock, and shell syntax checks.",
    )
    parser.add_argument(
        "--pytest-files",
        type=str,
        default="",
        help="Comma-separated test file paths to run with pytest",
    )
    parser.add_argument(
        "--adapter-policy",
        type=Path,
        default=None,
        help="Path to adapter policy JSON (e.g. adapters/ai_researcher_v1_policy.json)",
    )
    parser.add_argument(
        "--image-lock",
        type=Path,
        default=None,
        help="Path to Docker image lock file (e.g. docker/ai_researcher-images.lock.json)",
    )
    parser.add_argument(
        "--shell-patterns",
        type=str,
        default="",
        help="Comma-separated glob patterns for shell syntax checks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write quality gate report JSON",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    project_root = _find_project_root()

    pytest_files = (
        [Path(f.strip()) for f in args.pytest_files.split(",") if f.strip()]
        if args.pytest_files
        else []
    )
    shell_patterns = (
        [p.strip() for p in args.shell_patterns.split(",") if p.strip()]
        if args.shell_patterns
        else None
    )

    result = run_quality_gate(
        pytest_files=pytest_files,
        adapter_policy=args.adapter_policy,
        image_lock=args.image_lock,
        shell_patterns=shell_patterns,
        project_root=project_root,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result["summary"], indent=2))

    for gate_name, gate_result in result["gates"].items():
        status = "PASS" if gate_result["passed"] else "FAIL"
        skips = " (skipped)" if gate_result.get("skipped") else ""
        print(f"  {gate_name}: {status}{skips}")

    if not result["passed"]:
        print("QUALITY GATE FAILED", file=sys.stderr)
        sys.exit(1)

    print("QUALITY GATE PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
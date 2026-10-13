#!/usr/bin/env python3
"""validate_ai_researcher_final_dependencies.py

Resolve and validate all executable/config paths referenced by the F1-F4
final-verification commands.

This script parses the F1-F4 command definitions from the
``ai_researcher_final_validators.v1.json`` manifest, resolves every
executable path, config file path, and output directory referenced in the
argv templates, and reports which ones exist and are valid.  It does NOT
execute the validators — it only checks that their dependencies are
reachable.

Usage:
  python3 validate_ai_researcher_final_dependencies.py \
      --manifest config/ai_researcher_final_validators.v1.json \
      --project-root $RESEARCHCLAWEVAL_ROOT \
      --output result.json

Exit codes:
  0   All dependencies resolve and are valid.
  1   One or more dependencies are missing or invalid.
  2   Input error (missing manifest, bad JSON, etc.).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────

SCHEMA_VERSION = "final-dependencies-resolution.v1"

@dataclass
class Dependency:
    """A single dependency entry (executable, config, or output path)."""
    category: str          # "executable", "config", "output"
    raw_path: str          # original path from argv template
    resolved_path: Path | None = None
    exists: bool = False
    is_executable: bool = False
    sha256: str | None = None
    error: str | None = None


@dataclass
class CommandDeps:
    """Dependencies for a single F1-F4 command."""
    validator_id: str
    owner_todo: str
    argv_template: list[str]
    dependencies: list[Dependency] = field(default_factory=list)
    all_found: bool = True


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


def _is_executable(path: Path) -> bool:
    """Check if a path is executable (by its permission bits or file type)."""
    if not path.exists():
        return False
    # Check if it's executable via stat
    st = path.stat()
    executable = bool(st.st_mode & stat.S_IXUSR) or bool(st.st_mode & stat.S_IXGRP) or bool(st.st_mode & stat.S_IXOTH)
    # Also check if it's a Python/shebang script
    if not executable:
        try:
            with open(path) as f:
                first_line = f.read(128)
            if first_line.startswith("#!") and ("python" in first_line or "bash" in first_line or "sh" in first_line):
                executable = True
        except (OSError, UnicodeDecodeError):
            pass
    return executable


# ── Path resolution ─────────────────────────────────────────────────────────


def _resolve_path(
    raw: str,
    project_root: Path,
    validator_def: dict[str, Any],
) -> Path:
    """Resolve a raw path from an argv template against project_root.

    Handles:
      - Relative paths (resolved against project_root)
      - Absolute paths (used as-is)
      - Variable references like ``$PROJECT_ROOT``, ``${REAL_EVAL_ROOT}``
      - Paths that reference other fields in the validator definition
        (e.g. ``{runs_root}`` is replaced with ``validator_def['runs_root']``)
    """
    path_str = raw

    # Replace {variable} references from validator definition
    if isinstance(validator_def, dict):
        for key, value in validator_def.items():
            if isinstance(value, str):
                path_str = path_str.replace(f"{{{key}}}", value)

    # Replace environment variables
    path_str = os.path.expandvars(path_str)
    path_str = os.path.expanduser(path_str)

    resolved = Path(path_str)
    if not resolved.is_absolute():
        resolved = project_root / resolved

    return resolved.resolve()


def _classify_path(raw: str) -> str:
    """Classify a path string from an argv template.

    Returns one of: "executable", "config", "output", "flag", "unknown".
    """
    # Flags start with --
    if raw.startswith("--"):
        return "flag"

    # Common variable references
    if raw.startswith("{") or raw.startswith("$"):
        return "unknown"

    # Check extension
    ext = Path(raw).suffix.lower()
    if ext in (".py", ".sh", ""):
        return "executable"
    if ext in (".json", ".jsonc", ".yaml", ".yml", ".toml", ".md", ".txt", ".cfg", ".conf", ".lock"):
        return "config"
    if ext in (".log", ".out", ".result"):
        return "output"

    # No extension or unknown extension — likely executable or config
    if not ext:
        return "executable"

    return "unknown"


# ── Dependency Resolution ───────────────────────────────────────────────────


def resolve_dependencies(
    manifest: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Resolve all F1-F4 command dependencies from the manifest.

    Returns a result dict with per-validator dependency listings.
    """
    validators = manifest.get("validators", {}) if isinstance(manifest, dict) else {}
    if not validators and isinstance(manifest, list):
        # Treat list as flat list of validators
        validators = {v.get("id", f"validator-{i}"): v for i, v in enumerate(manifest)}

    command_deps_list: list[dict[str, Any]] = []
    all_found = True
    total_deps = 0
    total_found = 0

    for vid, vdef in validators.items():
        if not isinstance(vdef, dict):
            continue

        cmd = CommandDeps(
            validator_id=vid,
            owner_todo=vdef.get("owner_todo", ""),
            argv_template=vdef.get("argv_template", []),
        )

        argv = vdef.get("argv_template", [])
        if not argv:
            # Fallback: use executable + args
            exe = vdef.get("executable", "")
            args = vdef.get("args", [])
            argv = [exe] + args

        for i, arg in enumerate(argv):
            category = _classify_path(arg)
            if category == "flag":
                continue

            dep = Dependency(category=category, raw_path=arg)

            try:
                resolved = _resolve_path(arg, project_root, vdef)
                dep.resolved_path = resolved
                dep.exists = resolved.exists()

                if dep.exists:
                    total_found += 1
                    if category == "executable":
                        dep.is_executable = _is_executable(resolved)
                        if not dep.is_executable:
                            dep.error = f"not executable: {resolved}"
                            cmd.all_found = False
                    # Compute SHA-256 for config files and executables
                    if category in ("executable", "config") and resolved.is_file():
                        dep.sha256 = sha256_file(resolved)
                else:
                    dep.error = f"not found: {resolved}"
                    cmd.all_found = False
                    all_found = False

            except (OSError, ValueError) as e:
                dep.error = f"resolution error: {e}"
                cmd.all_found = False
                all_found = False

            total_deps += 1
            cmd.dependencies.append(dep)

        # Check that the executable itself exists
        exe = vdef.get("executable", "")
        if exe:
            exe_dep = Dependency(category="executable", raw_path=exe)
            try:
                resolved = _resolve_path(exe, project_root, vdef)
                exe_dep.resolved_path = resolved
                exe_dep.exists = resolved.exists()
                if resolved.exists():
                    total_found += 1
                    exe_dep.is_executable = _is_executable(resolved)
                    if resolved.is_file():
                        exe_dep.sha256 = sha256_file(resolved)
                else:
                    exe_dep.error = f"not found: {resolved}"
                    cmd.all_found = False
                    all_found = False
                total_deps += 1
                cmd.dependencies.append(exe_dep)
            except (OSError, ValueError) as e:
                exe_dep.error = f"resolution error: {e}"
                cmd.all_found = False
                all_found = False
                total_deps += 1
                cmd.dependencies.append(exe_dep)

        # Check input/output schema paths
        for schema_key in ("input_schema", "output_schema"):
            schema_path = vdef.get(schema_key)
            if schema_path:
                schema_dep = Dependency(category="config", raw_path=str(schema_path))
                try:
                    resolved = _resolve_path(str(schema_path), project_root, vdef)
                    schema_dep.resolved_path = resolved
                    schema_dep.exists = resolved.exists()
                    if resolved.exists():
                        total_found += 1
                        if resolved.is_file():
                            schema_dep.sha256 = sha256_file(resolved)
                    else:
                        schema_dep.error = f"not found: {resolved}"
                        cmd.all_found = False
                        all_found = False
                    total_deps += 1
                    cmd.dependencies.append(schema_dep)
                except (OSError, ValueError) as e:
                    schema_dep.error = f"resolution error: {e}"
                    cmd.all_found = False
                    all_found = False
                    total_deps += 1
                    cmd.dependencies.append(schema_dep)

        # Serialize
        deps_serialized = []
        for d in cmd.dependencies:
            deps_serialized.append({
                "category": d.category,
                "raw_path": d.raw_path,
                "resolved_path": str(d.resolved_path) if d.resolved_path else None,
                "exists": d.exists,
                "is_executable": d.is_executable,
                "sha256": d.sha256,
                "error": d.error,
            })

        command_deps_list.append({
            "validator_id": cmd.validator_id,
            "owner_todo": cmd.owner_todo,
            "argv_template": cmd.argv_template,
            "all_found": cmd.all_found,
            "dependencies": deps_serialized,
        })

    return {
        "schema": SCHEMA_VERSION,
        "timestamp": now_iso(),
        "project_root": str(project_root),
        "manifest_path": "",
        "passed": all_found,
        "validators": command_deps_list,
        "summary": {
            "total_validators": len(command_deps_list),
            "total_dependencies": total_deps,
            "dependencies_found": total_found,
            "dependencies_missing": total_deps - total_found,
            "validators_all_found": sum(1 for v in command_deps_list if v["all_found"]),
            "validators_with_missing": sum(1 for v in command_deps_list if not v["all_found"]),
        },
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve and validate all executable/config paths referenced "
                    "by the F1-F4 final-verification commands.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to the final validators manifest JSON "
             "(e.g. config/ai_researcher_final_validators.v1.json)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (default: auto-detected from script location)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write dependency resolution result JSON",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    manifest = _load_json(args.manifest)

    if args.project_root:
        project_root = args.project_root.resolve()
    else:
        # Auto-detect: walk up from script location
        script = Path(__file__).resolve()
        for parent in [script] + list(script.parents):
            if (parent / "real_eval").is_dir() and (parent / "real_eval" / "scripts").is_dir():
                project_root = parent
                break
        else:
            project_root = script.parents[2]

    result = resolve_dependencies(manifest, project_root)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result["summary"], indent=2))

    for v in result["validators"]:
        status = "PASS" if v["all_found"] else "FAIL"
        print(f"  [{status}] {v['validator_id']} ({v['owner_todo']}): "
              f"{len(v['dependencies'])} deps")
        for dep in v["dependencies"]:
            if dep["error"]:
                print(f"    MISSING: {dep['raw_path']} -> {dep['error']}", file=sys.stderr)

    if not result["passed"]:
        print("DEPENDENCY RESOLUTION FAILED", file=sys.stderr)
        sys.exit(1)

    print("DEPENDENCY RESOLUTION PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
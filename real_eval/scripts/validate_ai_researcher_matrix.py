#!/usr/bin/env python3
"""validate_ai_researcher_matrix.py

Validate an AI Researcher Matrix report against:
  1. The JSON Schema (ai_researcher_matrix.v1.json)
  2. The dispatch freeze manifest (optional)
  3. The runs-root directory (optional)

The matrix report is a closed JSON document that records every framework's
attempt kind, run references, and evidence pointers for a single campaign.
Three attempt kinds are distinguished by oneOf:

  - primary:  completed primary run with full evidence chain
  - admission_only: passed admission but not dispatched (blocked)
  - excluded: excluded from campaign (unsupported / blocked)

Usage:
  python3 validate_ai_researcher_matrix.py \\
      --matrix path/to/matrix.json \\
      [--manifest path/to/freeze_manifest.json] \\
      [--runs-root path/to/runs] \\
      [--schema path/to/schema.json] \\
      [--output path/to/result.json]

Exit codes:
  0   All validations pass.
  1   Validation failures (schema errors, manifest mismatches, missing refs).
  2   Input error (missing file, bad JSON, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(
    os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])
).expanduser()
SCHEMA_PATH = ROOT / "real_eval/schemas/ai_researcher_matrix.v1.json"
RUNS_ROOT = ROOT / "real_eval" / "runs"

# ── Helpers ──────────────────────────────────────────────────────────────


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def repo_path(root: Path, value: object) -> Path | None:
    if not nonempty_string(value):
        return None
    p = Path(str(value))
    return p if p.is_absolute() else root / p


# ── Validation report ────────────────────────────────────────────────────


@dataclass
class ValidationReport:
    matrix: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_valid: bool = False
    manifest_checks: dict[str, Any] = field(default_factory=dict)
    ref_checks: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        return "passed" if self.ok else "failed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "matrix": self.matrix,
            "schema_valid": self.schema_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "manifest_checks": self.manifest_checks,
            "ref_checks": self.ref_checks,
        }


# ── Schema validation ────────────────────────────────────────────────────


def validate_against_schema(
    matrix: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    """Validate matrix document against the JSON Schema (draft 2020-12).

    Uses a minimal recursive validator to avoid external dependencies.
    """
    schema_errors: list[str] = []
    _validate_node(matrix, schema, "#", schema_errors, schema)

    if schema_errors:
        report.errors.extend(schema_errors[:20])
        report.schema_valid = False
    else:
        # ── Additional semantic checks beyond schema ──────────────────
        entries = matrix.get("entries", [])
        primary_cells = matrix.get("primary_cells", [])

        # Every primary_cells pair must match an entry
        cell_lookup: dict[str, str] = {}
        for pair in primary_cells:
            fid, kind = pair[0], pair[1]
            cell_lookup[f"{fid}/{kind}"] = pair

        entry_keys: set[str] = set()
        for entry in entries:
            fid = entry.get("framework_id", "")
            kind = entry.get("attempt_kind", "")
            entry_keys.add(f"{fid}/{kind}")

        for key in cell_lookup:
            if key not in entry_keys:
                schema_errors.append(f"primary_cells pair {key} has no matching entry")

        # Check primary cells have exactly 15 unique pairs
        if len(primary_cells) != 15:
            schema_errors.append(
                f"primary_cells must have exactly 15 items, got {len(primary_cells)}"
            )

        # Check that entries cover all 7 frameworks
        framework_ids_in_entries = sorted(
            {e.get("framework_id") for e in entries if nonempty_string(e.get("framework_id"))}
        )
        expected_ids = ["01", "02", "03", "04", "05", "06", "07"]
        if framework_ids_in_entries != expected_ids:
            missing = sorted(set(expected_ids) - set(framework_ids_in_entries))
            extra = sorted(set(framework_ids_in_entries) - set(expected_ids))
            parts = []
            if missing:
                parts.append(f"missing frameworks: {missing}")
            if extra:
                parts.append(f"unexpected frameworks: {extra}")
            if parts:
                schema_errors.append("entry_framework_ids: " + "; ".join(parts))

        # Check that score_ref is null when score_applicable is false
        for entry in entries:
            kind = entry.get("attempt_kind")
            score_applicable = entry.get("score_applicable")
            score_ref = entry.get("score_ref")
            if score_applicable is False and score_ref is not None:
                schema_errors.append(
                    f"entry {entry.get('framework_id')}/{kind}: "
                    f"score_applicable is false but score_ref is not null"
                )

        if schema_errors:
            report.errors.extend(schema_errors[:20])
            report.schema_valid = False
        else:
            report.schema_valid = True


def _validate_node(
    value: object,
    subschema: dict[str, Any],
    path: str,
    errors: list[str],
    root: dict[str, Any],
) -> None:
    """Recursive schema validator for draft 2020-12 subset.

    Supports: type, const, enum, required, properties, additionalProperties,
    items, prefixItems, minItems, maxItems, uniqueItems, minLength, pattern,
    oneOf, \$ref, oneOf (nullable), format.
    """
    # ── Resolve $ref ──────────────────────────────────────────────────
    ref = subschema.get("$ref")
    if ref and isinstance(ref, str):
        if ref.startswith("#/$defs/"):
            def_name = ref[len("#/$defs/") :]
            resolved = root.get("$defs", {}).get(def_name)
            if resolved is None:
                errors.append(f"{path}: unresolved \$ref {ref}")
                return
            return _validate_node(value, resolved, path, errors, root)
        else:
            errors.append(f"{path}: unsupported \$ref {ref}")
            return

    # ── type check ────────────────────────────────────────────────────
    expected_type = subschema.get("type")
    if expected_type == "null":
        if value is not None:
            errors.append(f"{path}: expected null, got {type(value).__name__}")
        return

    if expected_type and isinstance(expected_type, str):
        type_map = {
            "string": str,
            "boolean": bool,
            "integer": int,
            "number": (int, float),
            "object": dict,
            "array": list,
        }
        if expected_type == "integer" and isinstance(value, bool):
            errors.append(f"{path}: expected integer, got boolean")
            return
        if not isinstance(value, type_map.get(expected_type, object)):
            if isinstance(value, bool) and expected_type in ("integer", "number"):
                errors.append(f"{path}: expected {expected_type}, got boolean")
                return
            if not (expected_type == "number" and isinstance(value, int)):
                pass  # allow int for number
            if not isinstance(value, type_map.get(expected_type, object)):
                errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")
                return

    # Check for type array with multiple types (oneOf pattern)
    if isinstance(expected_type, list):
        matched = False
        for t in expected_type:
            if t == "null" and value is None:
                matched = True
                break
            if t == "string" and isinstance(value, str):
                matched = True
                break
            if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
                matched = True
                break
            if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
                matched = True
                break
            if t == "boolean" and isinstance(value, bool):
                matched = True
                break
            if t == "object" and isinstance(value, dict):
                matched = True
                break
            if t == "array" and isinstance(value, list):
                matched = True
                break
        if not matched:
            errors.append(f"{path}: expected one of {expected_type}, got {type(value).__name__}")
            return

    # ── const check ───────────────────────────────────────────────────
    if "const" in subschema:
        if value != subschema["const"]:
            errors.append(f"{path}: expected const {subschema['const']!r}, got {value!r}")
        return

    # ── enum check ────────────────────────────────────────────────────
    if "enum" in subschema:
        if value not in subschema["enum"]:
            errors.append(f"{path}: expected one of {subschema['enum']}, got {value!r}")
        return

    # ── minLength / pattern (string) ──────────────────────────────────
    if isinstance(value, str):
        min_len = subschema.get("minLength")
        if min_len is not None and len(value) < min_len:
            errors.append(f"{path}: string length {len(value)} < minLength {min_len}")
            return
        pattern = subschema.get("pattern")
        if pattern:
            import re

            if not re.match(pattern, value):
                errors.append(f"{path}: string does not match pattern {pattern!r}")

    # ── format check ──────────────────────────────────────────────────
    fmt = subschema.get("format")
    if fmt == "date-time" and isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            errors.append(f"{path}: invalid date-time format: {value!r}")

    # ── object checks ─────────────────────────────────────────────────
    if isinstance(value, dict):
        required = subschema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")

        if subschema.get("additionalProperties") is False:
            allowed = set(subschema.get("properties", {}).keys())
            extra = set(value.keys()) - allowed
            if extra:
                errors.append(f"{path}: unexpected properties {sorted(extra)}")

        for prop_name, prop_schema in subschema.get("properties", {}).items():
            if prop_name in value:
                _validate_node(value[prop_name], prop_schema, f"{path}.{prop_name}", errors, root)

    # ── array checks ──────────────────────────────────────────────────
    if isinstance(value, list):
        min_items = subschema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: array length {len(value)} < minItems {min_items}")
        max_items = subschema.get("maxItems")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: array length {len(value)} > maxItems {max_items}")
        if subschema.get("uniqueItems"):
            seen = set()
            for i, item in enumerate(value):
                item_tuple = _make_hashable(item)
                if item_tuple in seen:
                    errors.append(f"{path}[{i}]: duplicate item {item!r}")
                seen.add(item_tuple)

        prefix_items = subschema.get("prefixItems", [])
        if prefix_items:
            if len(value) < len(prefix_items):
                errors.append(
                    f"{path}: array length {len(value)} < prefixItems count {len(prefix_items)}"
                )
            else:
                for i, item_schema in enumerate(prefix_items):
                    _validate_node(value[i], item_schema, f"{path}[{i}]", errors, root)
                if subschema.get("additionalItems") is False:
                    if len(value) > len(prefix_items):
                        errors.append(f"{path}: additional items beyond prefixItems not allowed")

        items_schema = subschema.get("items")
        if items_schema and not prefix_items:
            for i, item in enumerate(value):
                _validate_node(item, items_schema, f"{path}[{i}]", errors, root)

    # ── oneOf check ───────────────────────────────────────────────────
    one_of = subschema.get("oneOf")
    if one_of:
        match_count = 0
        for i, branch in enumerate(one_of):
            branch_errors: list[str] = []
            _validate_node(value, branch, f"{path}(oneOf[{i}])", branch_errors, root)
            if not branch_errors:
                match_count += 1
        if match_count == 0:
            errors.append(f"{path}: does not match any oneOf branch")
        elif match_count > 1:
            errors.append(f"{path}: matches {match_count} oneOf branches (must match exactly 1)")


def _make_hashable(item: object) -> object:
    """Convert a JSON value to a hashable tuple for uniqueness checks."""
    if isinstance(item, list):
        return tuple(_make_hashable(i) for i in item)
    if isinstance(item, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in item.items()))
    return item


# ── Manifest cross-validation ────────────────────────────────────────────


def cross_validate_manifest(
    matrix: dict[str, Any],
    manifest: dict[str, Any],
    root: Path,
    report: ValidationReport,
) -> None:
    """Cross-validate matrix entries against the freeze manifest.

    Checks:
      - campaign_id matches
      - Every entry framework_id referenced in the manifest exists
      - Manifest framework_images keys are a subset of entry framework_ids
    """
    checks: dict[str, Any] = {}

    # Campaign ID match
    matrix_campaign = matrix.get("campaign_id", "")
    manifest_campaign = manifest.get("campaign_id", "")
    if matrix_campaign and manifest_campaign:
        checks["campaign_id_match"] = matrix_campaign == manifest_campaign
        if not checks["campaign_id_match"]:
            report.errors.append(
                f"campaign_id mismatch: matrix={matrix_campaign!r}, manifest={manifest_campaign!r}"
            )

    # Framework image coverage
    manifest_images = manifest.get("framework_images", {})
    matrix_framework_ids = {e.get("framework_id") for e in matrix.get("entries", [])}

    checks["manifest_framework_ids"] = sorted(manifest_images.keys())
    checks["matrix_framework_ids"] = sorted(matrix_framework_ids)

    for fid in manifest_images:
        if fid not in matrix_framework_ids:
            report.errors.append(
                f"manifest references framework {fid} but matrix has no entry for it"
            )

    # Standard version check
    manifest_standard = manifest.get("standard_version")
    matrix_schema = matrix.get("schema_version")
    if manifest_standard and matrix_schema:
        checks["standard_version_present"] = True

    # File hashes in manifest should reference campaign evidence paths
    manifest_files = manifest.get("files", {})
    evidence_paths = [k for k in manifest_files if "admission" in k or "prompt_audit" in k]
    checks["evidence_file_count"] = len(evidence_paths)

    # Verify evidence files exist
    missing_evidence = []
    for path_str in evidence_paths:
        p = repo_path(root, path_str)
        if p and not p.exists():
            missing_evidence.append(path_str)
    if missing_evidence:
        checks["missing_evidence_files"] = missing_evidence
        report.warnings.append(
            f"manifest references {len(missing_evidence)} evidence files that do not exist"
        )

    report.manifest_checks = checks


# ── Runs-root cross-validation ───────────────────────────────────────────


def cross_validate_runs_root(
    matrix: dict[str, Any],
    runs_root: Path,
    report: ValidationReport,
) -> None:
    """Cross-validate matrix entry run references against the runs-root.

    For each entry with a primary_run_id, checks that:
      - A matching directory exists under runs_root
      - The run directory contains an outcome evidence file
    """
    checks: dict[str, Any] = {
        "runs_root": str(runs_root),
        "runs_root_exists": runs_root.is_dir(),
        "entries_checked": 0,
        "entries_found": 0,
        "entries_missing": [],
    }

    if not runs_root.is_dir():
        report.errors.append(f"runs-root does not exist: {runs_root}")
        report.ref_checks = checks
        return

    entries = matrix.get("entries", [])
    for entry in entries:
        kind = entry.get("attempt_kind")
        run_id = entry.get("primary_run_id")
        if not nonempty_string(run_id):
            continue

        checks["entries_checked"] += 1
        run_dir = runs_root / run_id

        if run_dir.is_dir():
            checks["entries_found"] += 1
        else:
            checks["entries_missing"].append(run_id)
            report.errors.append(
                f"run directory not found: {run_id} "
                f"(referenced by framework {entry.get('framework_id')}/{kind})"
            )

    # Check outcome_ref and admission_ref paths exist
    missing_refs = []
    for entry in entries:
        for ref_key in ("outcome_ref", "admission_ref", "prompt_audit_ref", "isolation_ref"):
            ref_val = entry.get(ref_key)
            if nonempty_string(ref_val):
                ref_path = repo_path(runs_root, ref_val)
                if ref_path and not ref_path.exists():
                    missing_refs.append(f"{entry.get('framework_id')}/{ref_key}: {ref_val}")

    if missing_refs:
        checks["missing_refs"] = missing_refs
        report.warnings.append(f"{len(missing_refs)} evidence refs not found under runs-root")

    report.ref_checks = checks


# ── Main validation ──────────────────────────────────────────────────────


def validate_matrix(
    matrix_path: Path,
    *,
    schema_path: Path = SCHEMA_PATH,
    manifest_path: Path | None = None,
    runs_root: Path | None = None,
    root: Path = ROOT,
) -> ValidationReport:
    report = ValidationReport(matrix=str(matrix_path))

    try:
        schema = load_json(schema_path)
        matrix = load_json(matrix_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report.errors.append(f"invalid_json:{exc}")
        return report

    # ── Schema validation ─────────────────────────────────────────────
    validate_against_schema(matrix, schema, report)

    # ── Manifest cross-validation ─────────────────────────────────────
    if manifest_path is not None:
        if manifest_path.is_file():
            try:
                manifest = load_json(manifest_path)
                cross_validate_manifest(matrix, manifest, root, report)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                report.errors.append(f"invalid_manifest:{exc}")
        else:
            report.errors.append(f"manifest not found: {manifest_path}")

    # ── Runs-root cross-validation ────────────────────────────────────
    if runs_root is not None:
        cross_validate_runs_root(matrix, runs_root, report)

    return report


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an AI Researcher Matrix report against schema, "
        "dispatch manifest, and runs-root."
    )
    parser.add_argument("--matrix", required=True, type=Path, help="Path to matrix report JSON")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to dispatch freeze manifest for cross-validation",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="Path to runs root directory for cross-validation (default: real_eval/runs)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help=f"Path to schema JSON (default: {SCHEMA_PATH})",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root for relative path resolution",
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="Path to write validation result JSON"
    )
    args = parser.parse_args()

    root = args.root.expanduser()
    matrix_path = args.matrix.expanduser()
    schema_path = args.schema.expanduser()
    manifest_path = args.manifest.expanduser() if args.manifest else None
    runs_root = args.runs_root.expanduser() if args.runs_root else None

    # Default runs-root to real_eval/runs
    if runs_root is None:
        runs_root = root / "real_eval" / "runs"

    if not matrix_path.is_file():
        print(f"ERROR: matrix not found: {matrix_path}", file=sys.stderr)
        return 2
    if not schema_path.is_file():
        print(f"ERROR: schema not found: {schema_path}", file=sys.stderr)
        return 2

    report = validate_matrix(
        matrix_path,
        schema_path=schema_path,
        manifest_path=manifest_path,
        runs_root=runs_root,
        root=root,
    )

    rendered = json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    print(rendered, end="")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""validate_adapter_diff.py — Validate adapter diff against policy.

Usage:
    python3 validate_adapter_diff.py --policy adapter-policy.v1.json --check-current
    python3 validate_adapter_diff.py --policy adapter-policy.v1.json --diff /path/to/diff.patch
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_native_source_hashes(policy: dict, root: Path, errors: list[str]) -> None:
    native_sha = policy.get("native_source_sha256", {})
    for rel_path, expected_sha in native_sha.items():
        full = root / rel_path
        if not full.is_file():
            errors.append(f"MISSING native source: {rel_path}")
            continue
        actual = _sha256(full)
        if actual != expected_sha:
            errors.append(f"SHA256 MISMATCH {rel_path}: expected {expected_sha}, got {actual}")
    if not errors:
        print(f"[OK] All {len(native_sha)} native source files match policy hashes.")


def _check_adapter_sha256(policy: dict, adapter_path: Path, errors: list[str]) -> None:
    expected = policy.get("source_adapter_sha256")
    if not expected:
        errors.append("MISSING source_adapter_sha256 in policy")
        return
    if not adapter_path.is_file():
        errors.append(f"MISSING adapter: {adapter_path}")
        return
    actual = _sha256(adapter_path)
    if actual != expected:
        errors.append(f"Adapter SHA256 MISMATCH: expected {expected}, got {actual}")
    else:
        print("[OK] Adapter SHA256 matches policy.")


def _check_policy_structure(policy: dict, errors: list[str]) -> None:
    required_top = [
        "policy_version", "policy_id", "source_adapter_path",
        "source_adapter_sha256", "allowed_operation_categories",
        "forbidden_operation_categories", "native_source_sha256", "entries",
    ]
    for key in required_top:
        if key not in policy:
            errors.append(f"MISSING top-level key: {key}")

    if "entries" in policy:
        for i, entry in enumerate(policy["entries"]):
            for key in ("rule_id", "operation_category", "target_path", "qualified_symbol", "ast_edit_kind"):
                if key not in entry:
                    errors.append(f"Entry[{i}] MISSING key: {key}")

            cat = entry.get("operation_category", "")
            allowed = policy.get("allowed_operation_categories", [])
            forbidden = policy.get("forbidden_operation_categories", [])
            if cat in forbidden:
                errors.append(f"Entry[{i}] rule_id={entry.get('rule_id')}: category '{cat}' is in forbidden list")
            if cat not in allowed and cat not in forbidden:
                errors.append(f"Entry[{i}] rule_id={entry.get('rule_id')}: category '{cat}' is neither allowed nor forbidden")


def _check_forbidden_in_adapter(policy: dict, adapter_path: Path, errors: list[str]) -> None:
    """Check that the adapter script itself does not contain forbidden patterns."""
    if not adapter_path.is_file():
        return
    text = adapter_path.read_text(encoding="utf-8", errors="ignore")
    forbidden_markers = {
        "hardcoded_prepare": "def prepare_agent",
        "agent_prompt_replacement": "TDC-ADMET-Tox HARD BUDGET RULES",
        "method_baseline_strategy": "AVAILABLE TOOLS:",
        "host_handoff_promotion": "_promote_tdc_handoff",
        "score_creation": "host_score",
        "hidden_label_access": "HIDDEN_LABELS_FILE",
    }
    for cat, marker in forbidden_markers.items():
        if cat not in policy.get("forbidden_operation_categories", []):
            continue
        if marker in text:
            errors.append(f"FORBIDDEN pattern '{marker}' ({cat}) found in adapter script")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate adapter diff against policy.")
    parser.add_argument("--policy", required=True, type=Path, help="Path to the adapter-policy JSON file.")
    parser.add_argument("--check-current", action="store_true", help="Verify current native source files match policy hashes.")
    parser.add_argument("--diff", type=Path, help="Path to a diff/patch file to validate against the policy.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root for native source resolution (default: cwd).")
    parser.add_argument("--adapter-root", type=Path, default=None, help="Root for adapter script resolution (default: same as --root).")
    args = parser.parse_args()

    if not args.policy.is_file():
        print(f"ERROR: policy file not found: {args.policy}", file=sys.stderr)
        return 1

    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    errors: list[str] = []

    # 1. Validate policy structure
    _check_policy_structure(policy, errors)

    # 2. Check adapter SHA256
    adapter_root = args.adapter_root or args.root
    adapter_rel = policy.get("source_adapter_path", "")
    adapter_path = adapter_root / adapter_rel
    _check_adapter_sha256(policy, adapter_path, errors)

    # 3. Check current native source hashes
    if args.check_current:
        _check_native_source_hashes(policy, args.root, errors)

    # 4. Check forbidden patterns are absent from the adapter script itself
    _check_forbidden_in_adapter(policy, adapter_path, errors)

    # 5. Validate diff if provided
    if args.diff:
        if not args.diff.is_file():
            errors.append(f"Diff file not found: {args.diff}")
        else:
            diff_text = args.diff.read_text(encoding="utf-8", errors="replace")
            entries_by_path = {}
            for entry in policy.get("entries", []):
                entries_by_path.setdefault(entry.get("target_path", ""), []).append(entry)
            for line in diff_text.splitlines():
                if line.startswith("--- a/") or line.startswith("+++ b/"):
                    p = line[6:].strip()
                    if p and p != "/dev/null" and p not in entries_by_path:
                        errors.append(f"DIFF touches untracked path: {p} (not in policy entries)")
            if not errors:
                print(f"[OK] Diff file '{args.diff}' references only policy-tracked paths.")

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\n[PASS] All policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

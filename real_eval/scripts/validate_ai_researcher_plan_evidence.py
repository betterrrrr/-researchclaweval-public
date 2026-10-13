#!/usr/bin/env python3
"""validate_ai_researcher_plan_evidence.py

F3: Verify every plan todo has a corresponding evidence artifact.

Reads a plan JSON (produced by Prometheus or equivalent planner) and an
evidence root directory, then checks that each todo item has at least one
matching evidence file under the evidence root.  Evidence matching is
flexible: a todo's label or content is matched against filenames, file
contents, or a designated evidence index.

Usage:
  python3 validate_ai_researcher_plan_evidence.py \
      --plan real_eval/.omo/plans/ai-researcher-repair.json \
      --evidence-root .omo/evidence/ai-researcher-repair \
      --require-todos todo-7,todo-8,todo-14 \
      --output result.json

Exit codes:
  0   All required todos have evidence, and all todos have evidence.
  1   One or more todos lack evidence.
  2   Input error (missing plan, unreadable evidence root, bad JSON).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────

EVIDENCE_EXTENSIONS = frozenset({".json", ".md", ".txt", ".yaml", ".yml", ".log"})
"""File extensions considered evidence artifacts."""

PLAN_SCHEMA_VERSION = "prometheus-plan.v1"
"""Expected schema version for plan files."""

# ── Helpers ────────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file, exiting with code 2 on failure."""
    try:
        with open(path, "r") as f:
            return dict(json.load(f))
    except FileNotFoundError:
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def _scan_evidence(
    evidence_root: Path,
    extensions: frozenset[str] = EVIDENCE_EXTENSIONS,
) -> dict[str, Path]:
    """Scan *evidence_root* recursively and return a dict of stem -> path.

    The stem is the filename without extension (e.g. ``todo-14-happy.json``
    yields key ``todo-14-happy``).  If multiple files share a stem, the last
    one wins (warning emitted).
    """
    evidence: dict[str, Path] = {}
    if not evidence_root.is_dir():
        print(f"WARNING: evidence root not found: {evidence_root}", file=sys.stderr)
        return evidence

    for p in sorted(evidence_root.rglob("*")):
        if p.is_file() and p.suffix in extensions:
            stem = p.stem  # filename without extension
            if stem in evidence:
                print(f"WARNING: duplicate evidence stem '{stem}': {p} "
                      f"(was {evidence[stem]})", file=sys.stderr)
            evidence[stem] = p
    return evidence


def _match_todo_to_evidence(
    todo: dict[str, Any],
    evidence_map: dict[str, Path],
) -> list[str]:
    """Return list of evidence stems that match *todo*.

    Matching strategies (in order, first match wins):
      1. Exact label match: if todo has a ``label`` field, look for an
         evidence file whose stem equals that label.
      2. Content match: if evidence files contain a ``todo_id`` or
         ``source_todo`` field matching the todo's ``id`` or ``label``.
      3. Fuzzy stem match: if the todo's ``id`` or ``label`` is a substring
         of an evidence stem, or vice versa.
    """
    matches: list[str] = []
    todo_id = str(todo.get("id", ""))
    todo_label = str(todo.get("label", ""))
    todo_content = str(todo.get("content", ""))

    # Strategy 1: exact label match
    if todo_label and todo_label in evidence_map:
        matches.append(todo_label)

    # Strategy 2: exact id match
    if todo_id and todo_id in evidence_map:
        matches.append(todo_id)

    # Strategy 3: content-based match — load evidence files and check fields
    for stem, path in evidence_map.items():
        if stem in matches:
            continue
        try:
            with open(path, "r") as f:
                raw = f.read(4096)  # read first 4KB
            # Try JSON
            if path.suffix == ".json":
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {}
                ev_todo_id = str(data.get("todo_id", "") or data.get("source_todo", ""))
                if ev_todo_id and (ev_todo_id == todo_id or ev_todo_id == todo_label):
                    matches.append(stem)
                    continue
            # Try markdown: look for todo_id or label in content
            if todo_id and todo_id in raw:
                matches.append(stem)
                continue
            if todo_label and todo_label in raw:
                matches.append(stem)
                continue
            if todo_content and len(todo_content) > 10 and todo_content[:80] in raw:
                matches.append(stem)
                continue
        except (OSError, json.JSONDecodeError):
            continue

    # Strategy 4: fuzzy substring match (only if no other match found)
    if not matches:
        for stem in evidence_map:
            if todo_id and (todo_id in stem or stem in todo_id):
                matches.append(stem)
            elif todo_label and (todo_label in stem or stem in todo_label):
                matches.append(stem)

    return matches


# ── Validation ─────────────────────────────────────────────────────────────


def validate_plan_evidence(
    plan: dict[str, Any],
    evidence_root: Path,
    require_todos: list[str] | None = None,
) -> dict[str, Any]:
    """Validate that every plan todo has corresponding evidence.

    Returns a result dict with per-todo status and overall pass/fail.
    """
    todos = plan.get("todos", []) if isinstance(plan, dict) else plan if isinstance(plan, list) else []
    if isinstance(todos, list) and len(todos) == 0 and "todos" not in plan:
        # Maybe the plan IS the list
        todos = plan if isinstance(plan, list) else []

    evidence_map = _scan_evidence(evidence_root)
    results: list[dict[str, Any]] = []
    missing_evidence: list[str] = []
    missing_required: list[str] = []

    required_set = set(require_todos or [])
    found_required: set[str] = set()

    for i, todo in enumerate(todos):
        todo_id = str(todo.get("id", f"todo-{i}"))
        todo_label = str(todo.get("label", ""))
        todo_content = str(todo.get("content", ""))
        todo_status = str(todo.get("status", "pending"))

        matched_stems = _match_todo_to_evidence(todo, evidence_map)
        has_evidence = len(matched_stems) > 0

        entry: dict[str, Any] = {
            "index": i,
            "id": todo_id,
            "label": todo_label,
            "content": todo_content[:120] + ("..." if len(todo_content) > 120 else ""),
            "status": todo_status,
            "has_evidence": has_evidence,
            "evidence_stems": matched_stems,
        }
        results.append(entry)

        if not has_evidence:
            missing_evidence.append(todo_id)

        if todo_id in required_set:
            if has_evidence:
                found_required.add(todo_id)
            else:
                missing_required.append(todo_id)

    # Check required todos that weren't in the plan at all
    for req in required_set:
        if req not in {r["id"] for r in results}:
            missing_required.append(req)
            missing_evidence.append(req)

    passed = len(missing_evidence) == 0 and len(missing_required) == 0
    total_evidence_files = len(evidence_map)

    return {
        "schema": "plan-evidence-validation.v1",
        "timestamp": now_iso(),
        "plan_path": str(evidence_root),
        "passed": passed,
        "summary": {
            "total_todos": len(todos),
            "total_evidence_files": total_evidence_files,
            "todos_with_evidence": len(todos) - len(missing_evidence),
            "todos_without_evidence": len(missing_evidence),
            "required_todos_requested": len(required_set),
            "required_todos_met": len(found_required),
            "required_todos_missing": missing_required,
        },
        "results": results,
        "missing_evidence": missing_evidence,
        "missing_required": missing_required,
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="F3: Verify every plan todo has a corresponding evidence artifact.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="Path to plan JSON file (e.g. .omo/plans/ai-researcher-repair.json)",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        required=True,
        help="Root directory of evidence artifacts (e.g. .omo/evidence/ai-researcher-repair)",
    )
    parser.add_argument(
        "--require-todos",
        type=str,
        default="",
        help="Comma-separated list of todo IDs that MUST have evidence",
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
    plan = _load_json(args.plan)
    require_todos = [t.strip() for t in args.require_todos.split(",") if t.strip()] if args.require_todos else None

    result = validate_plan_evidence(plan, args.evidence_root, require_todos)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result["summary"], indent=2))

    if result["missing_required"]:
        print(f"FAIL: required todos missing evidence: {result['missing_required']}",
              file=sys.stderr)

    if result["missing_evidence"]:
        print(f"FAIL: {len(result['missing_evidence'])} todos lack evidence",
              file=sys.stderr)
        for tid in result["missing_evidence"]:
            print(f"  - {tid}", file=sys.stderr)

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
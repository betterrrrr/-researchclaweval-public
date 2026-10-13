#!/usr/bin/env python3
"""capture_ai_researcher_repair_baseline.py

Descriptor-walk and freeze baseline hashes for all historical 01 runs
under real_eval/runs/ and approved source scope.  Writes
real_eval/config/ai_researcher_repair_scope.v1.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


# ── tree hash ──────────────────────────────────────────────────────────

def tree_hash(root: Path, *, follow_symlinks: bool = False) -> str:
    """Recursive SHA-256 of every file under *root*, sorted by relative
    path, producing a single content-addressable digest.

    Directories are hashed as the concatenation of their children's hashes
    (each child line is ``<relative_path> HASH``).  Empty directories yield
    the hash of the empty string.  Permission-denied subtrees are skipped.
    """
    if not root.is_dir():
        try:
            raw = root.read_bytes()
        except (PermissionError, OSError):
            return ""
        return hashlib.sha256(raw).hexdigest()

    try:
        children: list[Path] = sorted(root.iterdir(), key=lambda p: p.name)
    except (PermissionError, OSError):
        return ""

    parts: list[str] = []
    for child in children:
        rel = child.name
        try:
            if child.is_dir() and not follow_symlinks:
                h = tree_hash(child, follow_symlinks=follow_symlinks)
            elif child.is_file() or (child.is_symlink() and follow_symlinks):
                h = tree_hash(child, follow_symlinks=follow_symlinks)
            else:
                continue
        except (PermissionError, OSError):
            continue
        parts.append(f"{rel} {h}")

    combined = "\n".join(parts) + ("\n" if parts else "")
    return hashlib.sha256(combined.encode()).hexdigest()


# ── descriptor walk helpers ───────────────────────────────────────────

def _is_01_run_dir(name: str) -> bool:
    """Heuristic: a run directory containing an 01 (AI-Researcher) result."""
    return name.startswith("topic") or any(
        pat in name
        for pat in ("01_ai_researcher", "ai-researcher", "ai_researcher")
    )


def walk_approved_source_scope(src_root: Path) -> dict[str, str]:
    """Walk the approved source scope (files declared in the scope config)
    and return {relative_path: sha256} for every file found.
    """
    manifest: dict[str, str] = {}
    # Core source files that define the AI-Researcher native entrypoint
    # and framework orchestration contract.
    core_patterns = [
        "research_agent/run_infer_idea.py",
        "research_agent/inno/**/*.py",
        "research_agent/workflow/**/*.py",
        "research_agent/agents/**/*.py",
        "research_agent/tools/**/*.py",
        "research_agent/environment/**/*.py",
        "docker/Dockerfile",
        "docker/requirements.txt",
        "README.md",
    ]
    for pattern in core_patterns:
        for f in src_root.glob(pattern):
            if f.is_file():
                rel = f.relative_to(src_root).as_posix()
                manifest[rel] = _sha256_file(f)
    return dict(sorted(manifest.items()))


def walk_run_artifacts(runs_root: Path) -> dict[str, dict]:
    """Walk all historical 01 AI-Researcher run directories under
    *runs_root* and return a mapping of ``run_dir_name -> {rel_path: sha256}``.
    """
    runs: dict[str, dict] = {}
    if not runs_root.is_dir():
        return runs

    # Only hash descriptor files (not every file in the workspace) for speed
    descriptor_patterns = [
        "fullrun_manifest.json",
        "experiment_trace.json",
        "research_idea.json",
        "final_report.md",
        "score.json",
        "submission.json",
        "submission.csv",
        "predictions.csv",
        "predictions.jsonl",
        "state.json",
        "logs/e2e.log",
        "logs/official_score.log",
    ]

    for entry in sorted(runs_root.iterdir()):
        if not entry.is_dir():
            continue
        if not _is_01_run_dir(entry.name):
            continue
        has_entrypoint = False
        artifacts: dict[str, str] = {}
        for pattern in descriptor_patterns:
            try:
                matches = list(entry.glob(pattern))
            except (PermissionError, OSError):
                continue
            for f in matches:
                if not f.is_file():
                    continue
                try:
                    if not os.access(str(f), os.R_OK):
                        continue
                    rel = f.relative_to(entry).as_posix()
                    artifacts[rel] = _sha256_file(f)
                    if "run_infer_idea" in rel or "fullrun_manifest" in rel:
                        has_entrypoint = True
                except (PermissionError, OSError):
                    continue
        # Also check for any 01_ai_researcher_*fullrun.sh or run_infer_idea.py
        try:
            sh_matches = list(entry.rglob("*.sh"))
        except (PermissionError, OSError):
            sh_matches = []
        for f in sh_matches:
            try:
                if not os.access(str(f), os.R_OK):
                    continue
                rel = f.relative_to(entry).as_posix()
                if "01_ai_researcher" in rel or "run_infer_idea" in rel:
                    has_entrypoint = True
                    artifacts[rel] = _sha256_file(f)
            except (PermissionError, OSError):
                continue
        if not has_entrypoint:
            continue
        runs[entry.name] = dict(sorted(artifacts.items()))
    return runs


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── main ──────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="Descriptor-walk and freeze baseline hashes for AI-Researcher repair"
    )
    p.add_argument(
        "--runs-root",
        default=os.environ.get(
            "REAL_EVAL_RUN_ROOT",
            str(Path(__file__).resolve().parents[1] / "runs"),
        ),
        help="Path to real_eval/runs/ (default: ../runs relative to this script)",
    )
    p.add_argument(
        "--source-root",
        default=os.environ.get(
            "RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT",
            "",
        ),
        help="Path to AI-Researcher source root (default: empty, skip source walk)",
    )
    p.add_argument(
        "--output",
        default=str(
            Path(__file__).resolve().parents[1] / "config" / "ai_researcher_repair_scope.v1.json"
        ),
        help="Output path for the scope baseline JSON",
    )
    p.add_argument(
        "--fail-if-exists",
        action="store_true",
        help="Exit with code 2 if the output file already exists",
    )
    args = p.parse_args()

    out_path = Path(args.output)
    if args.fail_if_exists and out_path.exists():
        print(f"ERROR: output already exists: {out_path}", file=sys.stderr)
        return 2

    runs_root = Path(args.runs_root)
    src_root = Path(args.source_root) if args.source_root else None

    baseline: dict = {
        "version": "1.0",
        "description": "AI-Researcher repair baseline – frozen hashes for approved source scope and historical 01 run artifacts",
        "source_root": str(src_root.resolve()) if src_root else None,
        "source_files": {},
        "runs": {},
        "source_tree_hash": None,
        "run_hashes": {},
    }

    # Source scope
    if src_root and src_root.is_dir():
        baseline["source_files"] = walk_approved_source_scope(src_root)
        baseline["source_tree_hash"] = tree_hash(src_root)

    # Run artifacts
    baseline["runs"] = walk_run_artifacts(runs_root)

    # Per-run tree hashes
    run_hashes: dict[str, str] = {}
    for run_name, artifacts in baseline["runs"].items():
        run_dir = runs_root / run_name
        if run_dir.is_dir():
            run_hashes[run_name] = tree_hash(run_dir)
    baseline["run_hashes"] = run_hashes

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote baseline to {out_path}")
    print(f"  source_tree_hash:  {baseline['source_tree_hash']}")
    print(f"  source_files:      {len(baseline['source_files'])}")
    print(f"  run directories:   {len(baseline['runs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
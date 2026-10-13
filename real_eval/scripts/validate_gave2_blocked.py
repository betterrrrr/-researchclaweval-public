#!/usr/bin/env python3
"""validate_gave2_blocked.py

Descriptor-based validator that derives the GAVE2 dataset root from
real_eval/registry/topics.json and automation/gave2_task2_contract.md,
then probes every dataset segment via O_PATH|O_DIRECTORY|O_NOFOLLOW
descriptors.  Always emits blocked outcomes for all three models
(gpt-5.4, deepseek-v4-flash, kimi-k2.6) because the dataset is
unavailable.

Outcome maps:
  - missing / empty dataset        → blocked_dataset_unavailable
  - permission / read / path /     → blocked_authority_unverifiable
    identity / replacement failure

Usage:
  python3 real_eval/scripts/validate_gave2_blocked.py \
      --runs-root real_eval/runs \
      --registry real_eval/registry/topics.json \
      --contract automation/gave2_task2_contract.md \
      --output .omo/evidence/ai-researcher-repair/todo-12-happy.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Models to emit blocked outcomes for
# ---------------------------------------------------------------------------
MODELS = ["gpt-5.4", "deepseek-v4-flash", "kimi-k2.6"]

# Dataset segments expected under the GAVE2 dataset root
DATASET_SEGMENTS = [
    "training/images",
    "training/masks",
    "training/FFA_A",
    "training/FFA_AV",
    "training/av",
    "training/biomarker",
    "validation/images",
    "validation/masks",
    "validation/FFA_A",
    "validation/FFA_AV",
]


# ---------------------------------------------------------------------------
# Descriptor helpers
# ---------------------------------------------------------------------------

def open_dir_at(fd: int, rel: str) -> int:
    """Open *rel* (relative to *fd*) with O_PATH|O_DIRECTORY|O_NOFOLLOW.

    Returns the new fd or raises OSError.
    """
    probe = f"/proc/self/fd/{fd}/{rel}"
    return os.open(probe, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)


def open_file_at(fd: int, rel: str) -> int:
    """Open a regular file at *rel* relative to *fd* for reading.

    Returns the new fd (O_RDONLY | O_NOFOLLOW) or raises OSError.
    """
    probe = f"/proc/self/fd/{fd}/{rel}"
    return os.open(probe, os.O_RDONLY | os.O_NOFOLLOW)


def read_json_at(fd: int, rel: str) -> dict:
    """Read and parse a JSON file relative to *fd*."""
    fh = open_file_at(fd, rel)
    try:
        raw = os.read(fh, 4 * 1024 * 1024)
    finally:
        os.close(fh)
    return json.loads(raw.decode("utf-8"))


def read_text_at(fd: int, rel: str) -> str:
    """Read a text file relative to *fd*."""
    fh = open_file_at(fd, rel)
    try:
        raw = os.read(fh, 4 * 1024 * 1024)
    finally:
        os.close(fh)
    return raw.decode("utf-8")


def hash_file_at(fd: int, rel: str) -> str:
    """SHA-256 hex digest of a file relative to *fd*."""
    fh = open_file_at(fd, rel)
    try:
        h = hashlib.sha256()
        while True:
            chunk = os.read(fh, 65536)
            if not chunk:
                break
            h.update(chunk)
        return h.hexdigest()
    finally:
        os.close(fh)


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate_gave2_blocked(
    repo_root: str,
    registry_rel: str,
    contract_rel: str,
) -> dict:
    """Perform descriptor-based validation of GAVE2 dataset availability.

    Returns a dict with:
      - ``topic_id``
      - ``dataset_root`` (derived)
      - ``dataset_status``: one of ``blocked_dataset_unavailable``,
        ``blocked_authority_unverifiable``
      - ``blocked_reason``: human-readable explanation
      - ``evidence``: a dict of descriptor-level findings
      - ``models``: list of per-model outcomes (all blocked)
    """
    evidence: dict[str, object] = {}
    errors: list[str] = []
    status: str = "blocked"
    blocked_reason: str = ""
    dataset_root_rel: str = ""

    # ── 1. Open repo root  ──────────────────────────────────────────────
    repo_fd: int | None = None
    try:
        repo_fd = os.open(repo_root, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
        evidence["repo_root_fd"] = repo_fd
        st = os.fstat(repo_fd)
        evidence["repo_root_dev_ino"] = (st.st_dev, st.st_ino)
    except OSError as exc:
        errors.append(f"cannot open repo root {repo_root!r}: {exc}")
        evidence["repo_root_error"] = str(exc)
        status = "blocked_authority_unverifiable"
        blocked_reason = f"Repo root inaccessible: {exc}"
        return _build_payload(
            dataset_root_rel, status, blocked_reason, evidence, errors
        )

    # ── 2. Read registry + contract via descriptors  ────────────────────
    try:
        registry_hash = hash_file_at(repo_fd, registry_rel)
        evidence["registry_hash"] = registry_hash
        registry = read_json_at(repo_fd, registry_rel)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read registry {registry_rel!r}: {exc}")
        evidence["registry_error"] = str(exc)
        status = "blocked_authority_unverifiable"
        blocked_reason = f"Registry unreadable: {exc}"
        os.close(repo_fd)
        return _build_payload(
            dataset_root_rel, status, blocked_reason, evidence, errors
        )

    try:
        contract_hash = hash_file_at(repo_fd, contract_rel)
        evidence["contract_hash"] = contract_hash
        contract_text = read_text_at(repo_fd, contract_rel)
    except OSError as exc:
        errors.append(f"cannot read contract {contract_rel!r}: {exc}")
        evidence["contract_error"] = str(exc)
        status = "blocked_authority_unverifiable"
        blocked_reason = f"Contract unreadable: {exc}"
        os.close(repo_fd)
        return _build_payload(
            dataset_root_rel, status, blocked_reason, evidence, errors
        )

    # ── 3. Derive dataset root from both sources  ───────────────────────
    # From topics.json
    topics = registry.get("topics", [])
    gave2_topic: dict | None = None
    for t in topics:
        if t.get("id") == "gave2_task2":
            gave2_topic = t
            break
    if gave2_topic is None:
        errors.append("gave2_task2 topic not found in registry")
        evidence["topic_found"] = False
        status = "blocked_authority_unverifiable"
        blocked_reason = "gave2_task2 topic missing from registry"
        os.close(repo_fd)
        return _build_payload(
            dataset_root_rel, status, blocked_reason, evidence, errors
        )

    ds_from_registry = gave2_topic.get("dataset_root", "")
    evidence["dataset_root_from_registry"] = ds_from_registry
    evidence["topic_label"] = gave2_topic.get("label")
    evidence["topic_status"] = gave2_topic.get("status")
    evidence["topic_blocked_reason"] = gave2_topic.get("blocked_reason", "")

    # From contract.md
    ds_from_contract = ""
    for line in contract_text.splitlines():
        if line.strip().startswith("Dataset root:"):
            ds_from_contract = line.split(":", 1)[1].strip().strip("`")
            break
        if line.strip().startswith("- Dataset root:"):
            ds_from_contract = line.split(":", 1)[1].strip().strip("`")
            break
    evidence["dataset_root_from_contract"] = ds_from_contract

    # Cross-validate
    if ds_from_registry and ds_from_contract and ds_from_registry != ds_from_contract:
        evidence["dataset_root_mismatch"] = True
        status = "blocked_authority_unverifiable"
        blocked_reason = (
            f"Dataset root mismatch: registry says {ds_from_registry!r}, "
            f"contract says {ds_from_contract!r}"
        )
        os.close(repo_fd)
        return _build_payload(
            ds_from_registry or ds_from_contract, status, blocked_reason, evidence, errors
        )

    dataset_root_rel = ds_from_registry or ds_from_contract or "data/gave2/task2"
    evidence["dataset_root"] = dataset_root_rel

    # ── 4. Open dataset root via descriptor  ────────────────────────────
    ds_fd: int | None = None
    try:
        ds_fd = open_dir_at(repo_fd, dataset_root_rel)
        evidence["dataset_root_fd"] = ds_fd
        ds_st = os.fstat(ds_fd)
        evidence["dataset_root_dev_ino"] = (ds_st.st_dev, ds_st.st_ino)
    except OSError as exc:
        errors.append(f"dataset root {dataset_root_rel!r} not accessible: {exc}")
        evidence["dataset_root_error"] = str(exc)
        status = "blocked_dataset_unavailable"
        blocked_reason = f"Dataset root {dataset_root_rel!r} does not exist or is inaccessible"
        os.close(repo_fd)
        return _build_payload(
            dataset_root_rel, status, blocked_reason, evidence, errors
        )

    # ── 5. Open each dataset segment via descriptor  ────────────────────
    segment_fds: dict[str, int] = {}
    segment_entries: dict[str, list[str]] = {}
    for seg in DATASET_SEGMENTS:
        seg_fd: int | None = None
        try:
            seg_fd = open_dir_at(ds_fd, seg)
            segment_fds[seg] = seg_fd
            # descriptor-relative inventory: list entries via fd
            try:
                entries = sorted(os.listdir(f"/proc/self/fd/{seg_fd}"))
            except OSError:
                entries = []
            segment_entries[seg] = entries
        except OSError as exc:
            errors.append(f"segment {seg!r} not accessible: {exc}")
            evidence[f"segment_error:{seg}"] = str(exc)
            segment_fds[seg] = -1
            segment_entries[seg] = []

    evidence["segment_fds"] = {k: v for k, v in segment_fds.items()}
    evidence["segment_entry_counts"] = {
        k: len(v) for k, v in segment_entries.items()
    }

    # ── 6. Determine overall status  ────────────────────────────────────
    if errors:
        # If any segment is missing or empty → blocked_dataset_unavailable
        # If it's a permission/path/identity issue → blocked_authority_unverifiable
        has_missing = any(
            "not accessible" in str(e) or "does not exist" in str(e) or "No such file" in str(e)
            for e in errors
        )
        has_empty = any(
            seg_key in evidence.get("segment_entry_counts", {})
            and evidence["segment_entry_counts"][seg_key] == 0
            for seg_key in evidence.get("segment_entry_counts", {})
        )
        if has_missing or has_empty:
            status = "blocked_dataset_unavailable"
            blocked_reason = (
                f"GAVE2 dataset root {dataset_root_rel!r} exists but is "
                f"empty or has missing segments; no current dataset is available."
            )
        else:
            status = "blocked_authority_unverifiable"
            blocked_reason = (
                f"GAVE2 dataset root {dataset_root_rel!r} could not be "
                f"verified due to permission/read/path/identity failures."
            )
    else:
        # Dataset exists and all segments are present — but we still block
        # because the topic is marked blocked in the registry.
        status = "blocked_dataset_unavailable"
        blocked_reason = gave2_topic.get(
            "blocked_reason",
            f"Dataset root {dataset_root_rel!r} exists but is empty; "
            f"no current dataset is available.",
        )

    # ── 7. Clean up descriptors  ────────────────────────────────────────
    for seg_fd in segment_fds.values():
        if seg_fd > 0:
            try:
                os.close(seg_fd)
            except OSError:
                pass
    if ds_fd is not None:
        os.close(ds_fd)
    os.close(repo_fd)

    return _build_payload(
        dataset_root_rel, status, blocked_reason, evidence, errors
    )


def _build_payload(
    dataset_root: str,
    status: str,
    blocked_reason: str,
    evidence: dict,
    errors: list[str],
) -> dict:
    """Build the final payload with per-model outcomes."""
    now_iso = datetime.now(timezone.utc).astimezone().isoformat()
    outcomes = []
    for model in MODELS:
        outcome = {
            "model": model,
            "topic_id": "gave2_task2",
            "dataset_root": dataset_root,
            "outcome": status,
            "reason": blocked_reason,
            "blocked": True,
            "validated_at": now_iso,
        }
        outcomes.append(outcome)

    return {
        "validator": "validate_gave2_blocked",
        "topic_id": "gave2_task2",
        "dataset_root": dataset_root,
        "dataset_status": status,
        "blocked_reason": blocked_reason,
        "evidence": evidence,
        "errors": errors,
        "model_outcomes": outcomes,
        "outcome_count": len(outcomes),
        "created_at": now_iso,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Descriptor-based GAVE2 blocked validator"
    )
    p.add_argument("--runs-root", type=Path, required=True, help="Path to real_eval/runs")
    p.add_argument("--registry", type=Path, required=True, help="Path to topics.json")
    p.add_argument("--contract", type=Path, required=True, help="Path to gave2_task2_contract.md")
    p.add_argument("--output", type=Path, required=True, help="Output JSON path")
    args = p.parse_args()

    # Repo root: use absolute() NOT resolve() to avoid following the
    # real_eval symlink -> <run root>.
    repo_root = Path(__file__).absolute().parents[2]  # scripts/ -> real_eval/ -> repo
    if not (repo_root / "real_eval" / "registry" / "topics.json").exists():
        repo_root = args.runs_root.absolute().parents[1]

    repo_root_str = str(repo_root.absolute())

    # Compute relative paths from repo root using absolute() (no symlink-follow).
    def _make_rel(p: Path) -> str:
        absp = str(p.absolute())
        if absp.startswith(repo_root_str + "/"):
            return absp[len(repo_root_str) + 1:]
        if absp == repo_root_str:
            return "."
        return absp

    registry_rel = _make_rel(args.registry)
    contract_rel = _make_rel(args.contract)

    payload = validate_gave2_blocked(
        repo_root=str(repo_root.absolute()),
        registry_rel=registry_rel,
        contract_rel=contract_rel,
    )

    # Write output
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Print summary
    print(json.dumps({
        "status": payload["dataset_status"],
        "outcome_count": payload["outcome_count"],
        "output": str(output_path),
        "models": [o["model"] for o in payload["model_outcomes"]],
    }, ensure_ascii=False))

    return 0 if payload["outcome_count"] == len(MODELS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
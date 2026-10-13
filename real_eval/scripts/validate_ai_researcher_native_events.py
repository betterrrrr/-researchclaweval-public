#!/usr/bin/env python3
"""validate_ai_researcher_native_events.py

Validate ordered, hash-valid, host-observed native ancestry events from
an AI-Researcher experiment_trace.json.

Validates:
  - Events are ordered by sequence number.
  - Each event's hash is self-consistent (chain hash).
  - PID ancestry is consistent (ppid matches previous event's pid).
  - First event's ppid is a plausible host PID (≥ 1).
  - No duplicate or out-of-order sequences.
  - Native entrypoint and executor_kind are set correctly.

Usage:
  python3 validate_ai_researcher_native_events.py \
      --trace real_eval/runs/<run>/experiment_trace.json
  python3 validate_ai_researcher_native_events.py \
      --trace-dir real_eval/runs/<run>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


# ── validation ────────────────────────────────────────────────────────


def validate_native_events(
    trace: dict,
    *,
    strict_pid_ancestry: bool = True,
    allow_missing_entrypoint: bool = False,
) -> list[str]:
    """Validate the native ancestry events in *trace*.

    Returns a list of error strings (empty list = valid).
    """
    errors: list[str] = []

    # 1. Top-level fields
    if not allow_missing_entrypoint:
        entrypoint = trace.get("native_entrypoint", "")
        if not entrypoint:
            errors.append("missing native_entrypoint")
        elif "run_infer_idea.py" not in entrypoint:
            errors.append(
                f"native_entrypoint must reference run_infer_idea.py, got {entrypoint!r}"
            )

    executor_kind = trace.get("executor_kind")
    if executor_kind != "framework_cli":
        errors.append(f"executor_kind must be 'framework_cli', got {executor_kind!r}")

    native_log_marker = trace.get("native_log_marker", "")
    if not native_log_marker or len(native_log_marker) < 5:
        errors.append(f"native_log_marker too short or missing: {native_log_marker!r}")

    if trace.get("framework_orchestration") is not True:
        errors.append("framework_orchestration must be true")

    if trace.get("framework_native_execution") is not True:
        errors.append("framework_native_execution must be true")

    # 2. Events list
    events = trace.get("events", [])
    if not isinstance(events, list):
        errors.append("events must be a list")
        return errors

    if not events:
        errors.append("events list is empty — no ancestry evidence")
        return errors

    # 3. Ordering and sequence check
    seen_seqs: set[int] = set()
    prev_seq = 0
    prev_pid: int | None = None
    prev_hash = ""

    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            errors.append(f"events[{i}] is not a dict")
            continue

        seq = ev.get("sequence")
        if not isinstance(seq, int) or seq < 1:
            errors.append(f"events[{i}] missing or invalid sequence number: {seq!r}")
            continue

        if seq in seen_seqs:
            errors.append(f"events[{i}] duplicate sequence number: {seq}")
        seen_seqs.add(seq)

        if seq <= prev_seq:
            errors.append(
                f"events[{i}] sequence {seq} is not greater than previous {prev_seq}"
            )
        prev_seq = seq

        # 4. Required fields
        event_type = ev.get("event", "")
        if not event_type:
            errors.append(f"events[{i}] missing event type")

        pid = ev.get("pid")
        if not isinstance(pid, int) or pid < 1:
            errors.append(f"events[{i}] missing or invalid pid: {pid!r}")

        ppid = ev.get("ppid")
        if not isinstance(ppid, int) or ppid < 1:
            errors.append(f"events[{i}] missing or invalid ppid: {ppid!r}")

        command = ev.get("command", "")
        if not command:
            errors.append(f"events[{i}] missing command")

        # 5. Hash chain validation
        claimed_hash = ev.get("hash", "")
        if not claimed_hash:
            errors.append(f"events[{i}] missing hash")
        else:
            payload = f"{prev_hash}|{seq}|{event_type}|{pid}|{ppid}"
            expected_hash = hashlib.sha256(payload.encode()).hexdigest()
            if claimed_hash != expected_hash:
                errors.append(
                    f"events[{i}] hash mismatch: "
                    f"claimed={claimed_hash}, expected={expected_hash} "
                    f"(payload: {payload!r})"
                )

        # 6. PID ancestry (first event's ppid must be plausible;
        # subsequent events' ppid must match previous pid)
        if i == 0:
            if ppid is not None and ppid < 1:
                errors.append(
                    f"events[{i}] first event ppid={ppid} is not a plausible host PID"
                )
        elif strict_pid_ancestry and prev_pid is not None:
            if ppid != prev_pid:
                errors.append(
                    f"events[{i}] ppid={ppid} does not match previous event pid={prev_pid}"
                )

        prev_pid = pid
        if claimed_hash and claimed_hash == expected_hash:
            prev_hash = claimed_hash
        else:
            prev_hash = expected_hash  # use expected for chain continuity

    # 7. At least one event must reference run_infer_idea.py
    has_infer_idea = any(
        "run_infer_idea.py" in ev.get("command", "")
        for ev in events
    )
    if not has_infer_idea:
        errors.append("no event references run_infer_idea.py in its command")

    return errors


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(
        description="Validate ordered, hash-valid, host-observed native ancestry events"
    )
    p.add_argument(
        "--trace",
        help="Path to experiment_trace.json",
    )
    p.add_argument(
        "--trace-dir",
        help="Path to a run directory containing experiment_trace.json",
    )
    p.add_argument(
        "--no-strict-pid",
        action="store_false",
        dest="strict_pid_ancestry",
        help="Disable strict PID ancestry checking",
    )
    p.add_argument(
        "--allow-missing-entrypoint",
        action="store_true",
        help="Allow missing native_entrypoint field (for partial traces)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = p.parse_args()

    # Resolve trace path
    trace_path: Path | None = None
    if args.trace:
        trace_path = Path(args.trace)
    elif args.trace_dir:
        trace_path = Path(args.trace_dir) / "experiment_trace.json"
    else:
        p.error("either --trace or --trace-dir is required")

    if not trace_path.is_file():
        print(f"ERROR: trace file not found: {trace_path}", file=sys.stderr)
        return 1

    trace = json.loads(trace_path.read_text(encoding="utf-8"))

    errors = validate_native_events(
        trace,
        strict_pid_ancestry=args.strict_pid_ancestry,
        allow_missing_entrypoint=args.allow_missing_entrypoint,
    )

    valid = len(errors) == 0

    if args.json:
        output = {
            "valid": valid,
            "trace_path": str(trace_path),
            "error_count": len(errors),
            "errors": errors,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if valid:
            print(f"✓ VALID: {trace_path}")
            print("  All native ancestry events are ordered, hash-valid, and consistent.")
        else:
            print(f"✗ INVALID: {trace_path}")
            for err in errors:
                print(f"  - {err}")

    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
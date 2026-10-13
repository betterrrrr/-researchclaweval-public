#!/usr/bin/env python3
"""reconcile_ai_researcher_runs.py

Terminal lifecycle state management for AI researcher runs.

Journaling
  Atomically persist launch nonce, runner/native/daemon/container ids,
  /proc start times, cgroups, daemon socket inode, and event cursor.

CAS state
  Only the trap/reconciler may CAS (compare-and-swap) the run state.

Reconciler
  Locks and probes at monotonic t=0s, t=15s, t=30s +/-1s, comparing
  all receipts.  Evaluates and records every predicate before choosing
  outcome via total precedence from the Acceptance policy.

Usage:
  python3 real_eval/scripts/reconcile_ai_researcher_runs.py \
      --runs-root <path> --classify --output <path>
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "ai_researcher_outcome.v1"
RECONCILER_VERSION = "reconcile.v1"
CLASSIFIER_VERSION = "reconcile.v1"

# Total precedence ordering: highest rank = most severe / blocking.
# Applied exactly once per reconciliation.
OUTCOME_PRECEDENCE: list[str] = [
    "blocked_dataset_unavailable",
    "blocked_authority_unverifiable",
    "blocked_benchmark_authorization",
    "unsupported_native_entrypoint",
    "failed_admission",
    "failed_engineering",
    "failed_contract",
    "failed_native_research",
    "failed_interrupted",
    "failed_reconciliation_unavailable",
    "inconclusive_unknown_termination",
    "scored",
    "finished",
]

PRECEDENCE_RANK: dict[str, int] = {o: i for i, o in enumerate(OUTCOME_PRECEDENCE)}

# Acceptable clock drift for probe windows (±1 second)
PROBE_WINDOW_S = 1.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def monotonic_s() -> float:
    return time.monotonic()


def digest(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def atomic_write(path: Path, data: dict) -> None:
    """Atomically write a JSON dict to *path* via rename."""
    tmp = path.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    tmp.rename(path)


def read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None


def glob_with_timestamp(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime)


def running_under(path: Path) -> bool:
    """Check if the run is still active (e.g. a PID file exists with a live PID)."""
    pid_file = path / ".run.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return False


# ---------------------------------------------------------------------------
# Journaling
# ---------------------------------------------------------------------------

def journal_acquire(run_dir: Path) -> dict:
    """Atomically write a journal recording the launch snapshot.

    Captures: launch nonce, runner/native/daemon/container ids, /proc start
    times, cgroups, daemon socket inode, and event cursor.
    """
    journal_path = run_dir / ".journal.v1.json"

    # If journal already exists, return it (idempotent).
    existing = read_json(journal_path)
    if existing is not None:
        return existing

    nonce = uuid.uuid4().hex

    # --- Probe /proc for our own identity ---
    our_pid = os.getpid()
    proc_start = ""
    try:
        stat_lines = Path(f"/proc/{our_pid}/stat").read_text().split()
        # Field 22 (1-indexed) = starttime in clock ticks after boot
        if len(stat_lines) > 21:
            proc_start = stat_lines[21]
    except Exception:
        proc_start = ""

    cgroups: list[str] = []
    try:
        cg_raw = Path(f"/proc/{our_pid}/cgroup").read_text().strip()
        cgroups = [ln.strip() for ln in cg_raw.splitlines() if ln.strip()]
    except Exception:
        pass

    daemon_socket_inode: Optional[int] = None
    try:
        for entry in Path("/proc/1/fd").iterdir():
            try:
                link = os.readlink(str(entry))
                if "socket" in link:
                    ino = entry.stat().st_ino
                    daemon_socket_inode = ino
                    break
            except OSError:
                continue
    except Exception:
        pass

    event_cursor: Optional[str] = None
    try:
        from subprocess import run as sprun
        r = sprun(["journalctl", "--list-cursors", "--quiet", "-n", "1"],
                  capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            event_cursor = r.stdout.strip().split()[0] if r.stdout.strip() else None
    except Exception:
        pass

    journal: dict = {
        "nonce": nonce,
        "acquired_at": now_iso(),
        "monotonic_at_s": monotonic_s(),
        "reconciler_pid": our_pid,
        "reconciler_proc_start": proc_start,
        "runner_ids": {
            "pid": os.environ.get("RUNNER_PID", str(our_pid)),
            "native_pid": os.environ.get("NATIVE_PID"),
            "daemon_pid": os.environ.get("DAEMON_PID"),
            "container_id": os.environ.get("CONTAINER_ID"),
        },
        "proc_start_times": {
            "reconciler": proc_start,
            "runner": os.environ.get("RUNNER_PROC_START"),
            "native": os.environ.get("NATIVE_PROC_START"),
            "daemon": os.environ.get("DAEMON_PROC_START"),
        },
        "cgroups": cgroups,
        "daemon_socket_inode": daemon_socket_inode,
        "event_cursor": event_cursor,
    }

    atomic_write(journal_path, journal)
    return journal


# ---------------------------------------------------------------------------
# CAS State Lock
# ---------------------------------------------------------------------------

class CASLock:
    """Compare-and-swap lock using flock.  Only the trap/reconciler may CAS
    state — the lock file path is derived from the run directory."""

    def __init__(self, run_dir: Path) -> None:
        self._lock_path = run_dir / ".reconciler.lock"
        self._fd: Optional[int] = None

    def acquire(self, blocking: bool = True) -> bool:
        try:
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            fcntl.flock(fd, flags)
            self._fd = fd
            return True
        except (IOError, OSError):
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            return False

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "CASLock":
        self.acquire(blocking=True)
        return self

    def __exit__(self, *args: Any) -> None:
        self.release()

    def read_state(self) -> dict:
        """Read the current CAS state from the lock file."""
        data = read_json(self._lock_path)
        return data if data is not None else {}

    def write_state(self, state: dict) -> None:
        """Atomically write CAS state (must hold lock)."""
        if self._fd is None:
            raise RuntimeError("CASLock not acquired")
        atomic_write(self._lock_path, state)


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

def probe(run_dir: Path, monotonic_offset: float) -> dict:
    """Take a probe snapshot of the run at the given monotonic offset.

    Captures wall clock, PID, /proc start time, cgroup availability,
    daemon socket inode, and event cursor.  Returns a receipt dict.
    """
    pid = None
    proc_start = None
    cgroup_available = False
    daemon_socket_inode = None
    event_cursor = None

    # Look for the run's PID file
    pid_file = run_dir / ".run.pid"
    try:
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        pass

    # If we have a PID, probe /proc
    if pid is not None:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text().split()
            if len(stat) > 21:
                proc_start = stat[21]
        except Exception:
            pass

        try:
            cg = Path(f"/proc/{pid}/cgroup").read_text().strip()
            cgroup_available = bool(cg)
        except Exception:
            pass

    # Daemon socket inode from /proc/1/fd
    try:
        for entry in Path("/proc/1/fd").iterdir():
            try:
                link = os.readlink(str(entry))
                if "socket" in link:
                    daemon_socket_inode = entry.stat().st_ino
                    break
            except OSError:
                continue
    except Exception:
        pass

    # Event cursor
    try:
        from subprocess import run as sprun
        r = sprun(["journalctl", "--list-cursors", "--quiet", "-n", "1"],
                  capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            event_cursor = r.stdout.strip().split()[0]
    except Exception:
        pass

    receipt = {
        "wall_clock": now_iso(),
        "monotonic_offset_s": monotonic_offset,
        "pid": pid,
        "proc_start_time": proc_start,
        "cgroup_available": cgroup_available,
        "daemon_socket_inode": daemon_socket_inode,
        "event_cursor": event_cursor,
    }
    receipt["receipt_digest"] = digest(receipt)
    return receipt


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------

def evaluate_predicates(run_dir: Path, journal: dict, probes: dict) -> list[dict]:
    """Evaluate every failure predicate.  Returns a list of predicate records.

    Each record has: predicate, label, triggered (bool), evidence_path.
    """
    predicates: list[dict] = []

    # Gather clues from the run directory
    outcome_files = list(run_dir.glob("*.outcome.*"))
    has_outcome = len(outcome_files) > 0
    latest_outcome = None
    if outcome_files:
        latest_outcome = read_json(sorted(outcome_files)[-1])

    blocked_flags = list(run_dir.glob("*.blocked.*"))
    has_blocked = len(blocked_flags) > 0

    failure_flags = list(run_dir.glob("*.failed.*"))
    has_failure = len(failure_flags) > 0

    score_files = list(run_dir.glob("*.score.*"))
    has_score = len(score_files) > 0 and any(
        read_json(f) is not None for f in score_files
    )

    done_files = list(run_dir.glob("*.done.*"))
    has_done = len(done_files) > 0

    admission_passed = (run_dir / ".admission.passed").exists()
    admission_failed = (run_dir / ".admission.failed").exists()
    engineering_done = (run_dir / ".engineering.done").exists()
    engineering_failed = (run_dir / ".engineering.failed").exists()
    contract_met = (run_dir / ".contract.met").exists()
    contract_failed = (run_dir / ".contract.failed").exists()
    native_done = (run_dir / ".native.done").exists()
    native_failed = (run_dir / ".native.failed").exists()

    # Probe consistency
    receipts_consistent = True
    receipt_digests = set()
    for probe_key in ("t0", "t15", "t30"):
        p = probes.get(probe_key)
        if p is not None:
            receipt_digests.add(p.get("receipt_digest", ""))
    receipts_consistent = len(receipt_digests) <= 1

    # --- Predicate 1: blocked_dataset_unavailable ---
    dataset_blocked = (
        has_blocked
        and any("dataset" in f.name for f in blocked_flags)
    ) or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "blocked_dataset_unavailable"
    )
    ev_path = None
    if dataset_blocked:
        bf = [f for f in blocked_flags if "dataset" in f.name]
        ev_path = str(bf[0].relative_to(run_dir)) if bf else None
    predicates.append({
        "predicate": "blocked_dataset_unavailable",
        "label": "Dataset unavailable",
        "triggered": dataset_blocked,
        "evidence_path": ev_path,
    })

    # --- Predicate 2: blocked_authority_unverifiable ---
    authority_blocked = (
        has_blocked
        and any("authority" in f.name or "unverifiable" in f.name for f in blocked_flags)
    ) or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "blocked_authority_unverifiable"
    )
    ev_path = None
    if authority_blocked:
        bf = [f for f in blocked_flags if "authority" in f.name or "unverifiable" in f.name]
        ev_path = str(bf[0].relative_to(run_dir)) if bf else None
    predicates.append({
        "predicate": "blocked_authority_unverifiable",
        "label": "Authority unverifiable",
        "triggered": authority_blocked,
        "evidence_path": ev_path,
    })

    # --- Predicate 3: blocked_benchmark_authorization ---
    bench_blocked = (
        has_blocked
        and any("benchmark" in f.name or "authorization" in f.name for f in blocked_flags)
    ) or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "blocked_benchmark_authorization"
    )
    ev_path = None
    if bench_blocked:
        bf = [f for f in blocked_flags if "benchmark" in f.name or "authorization" in f.name]
        ev_path = str(bf[0].relative_to(run_dir)) if bf else None
    predicates.append({
        "predicate": "blocked_benchmark_authorization",
        "label": "Benchmark authorization blocked",
        "triggered": bench_blocked,
        "evidence_path": ev_path,
    })

    # --- Predicate 4: unsupported_native_entrypoint ---
    unsupported = (
        (run_dir / ".unsupported_entrypoint").exists()
    ) or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "unsupported_native_entrypoint"
    )
    predicates.append({
        "predicate": "unsupported_native_entrypoint",
        "label": "Unsupported native entrypoint",
        "triggered": unsupported,
        "evidence_path": str(".unsupported_entrypoint") if unsupported else None,
    })

    # --- Predicate 5: failed_admission ---
    fail_admission = admission_failed or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "failed_admission"
    )
    predicates.append({
        "predicate": "failed_admission",
        "label": "Admission failed",
        "triggered": fail_admission,
        "evidence_path": str(".admission.failed") if admission_failed else None,
    })

    # --- Predicate 6: failed_engineering ---
    fail_engineering = engineering_failed or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "failed_engineering"
    )
    predicates.append({
        "predicate": "failed_engineering",
        "label": "Engineering failed",
        "triggered": fail_engineering,
        "evidence_path": str(".engineering.failed") if engineering_failed else None,
    })

    # --- Predicate 7: failed_contract ---
    fail_contract = contract_failed or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "failed_contract"
    )
    predicates.append({
        "predicate": "failed_contract",
        "label": "Contract failed",
        "triggered": fail_contract,
        "evidence_path": str(".contract.failed") if contract_failed else None,
    })

    # --- Predicate 8: failed_native_research ---
    fail_native = native_failed or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "failed_native_research"
    )
    predicates.append({
        "predicate": "failed_native_research",
        "label": "Native research failed",
        "triggered": fail_native,
        "evidence_path": str(".native.failed") if native_failed else None,
    })

    # --- Predicate 9: scored ---
    did_score = has_score or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "scored"
    )
    predicates.append({
        "predicate": "scored",
        "label": "Score available",
        "triggered": did_score,
        "evidence_path": str(score_files[-1].relative_to(run_dir)) if score_files else None,
    })

    # --- Predicate 10: finished ---
    did_finish = has_done or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "finished"
    )
    predicates.append({
        "predicate": "finished",
        "label": "Run completed successfully",
        "triggered": did_finish,
        "evidence_path": str(done_files[-1].relative_to(run_dir)) if done_files else None,
    })

    # --- Predicate 11: failed_interrupted ---
    interrupted = (
        (run_dir / ".interrupted").exists()
    ) or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "failed_interrupted"
    )
    predicates.append({
        "predicate": "failed_interrupted",
        "label": "Run interrupted",
        "triggered": interrupted,
        "evidence_path": str(".interrupted") if (run_dir / ".interrupted").exists() else None,
    })

    # --- Predicate 12: failed_reconciliation_unavailable ---
    reconciliation_unavailable = (
        (run_dir / ".reconciliation.unavailable").exists()
    ) or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "failed_reconciliation_unavailable"
    )
    predicates.append({
        "predicate": "failed_reconciliation_unavailable",
        "label": "Reconciliation unavailable",
        "triggered": reconciliation_unavailable,
        "evidence_path": str(".reconciliation.unavailable") if (run_dir / ".reconciliation.unavailable").exists() else None,
    })

    # --- Predicate 13: inconclusive_unknown_termination ---
    unknown_termination = (
        (run_dir / ".unknown_termination").exists()
    ) or (
        not has_outcome
        and not has_done
        and not has_failure
        and not has_blocked
        and not running_under(run_dir)
    ) or (
        latest_outcome is not None
        and latest_outcome.get("outcome") == "inconclusive_unknown_termination"
    )
    predicates.append({
        "predicate": "inconclusive_unknown_termination",
        "label": "Unknown termination",
        "triggered": unknown_termination,
        "evidence_path": str(".unknown_termination") if (run_dir / ".unknown_termination").exists() else None,
    })

    return predicates


# ---------------------------------------------------------------------------
# Precedence resolution
# ---------------------------------------------------------------------------

def resolve_precedence(predicates: list[dict]) -> str:
    """Apply total precedence ordering exactly once.

    Among all triggered predicates, pick the highest-ranked outcome
    (lowest rank number = most severe).
    """
    triggered_outcomes = [
        p["predicate"] for p in predicates if p["triggered"]
    ]
    if not triggered_outcomes:
        return "inconclusive_unknown_termination"

    # Rank by precedence (lower number = higher precedence)
    triggered_outcomes.sort(key=lambda o: PRECEDENCE_RANK.get(o, 999))
    return triggered_outcomes[0]


# ---------------------------------------------------------------------------
# Dimension evaluation
# ---------------------------------------------------------------------------

def evaluate_dimensions(
    run_dir: Path,
    journal: dict,
    probes: dict,
    predicates: list[dict],
    precedence_winner: str,
) -> dict:
    """Evaluate the four dimensions: lifecycle, integrity, capability, outcome."""
    # --- Lifecycle ---
    outcome_files = list(run_dir.glob("*.outcome.*"))
    latest_outcome = read_json(sorted(outcome_files)[-1]) if outcome_files else None

    phase_map: dict[str, str] = {
        "admission": "admission",
        "preparation": "preparation",
        "engineering": "engineering",
        "research": "research",
        "scoring": "scoring",
        "finished": "finished",
        "interrupted": "interrupted",
    }
    detected_phase = "unknown"
    for marker, phase in phase_map.items():
        if (run_dir / f".{marker}").exists() or (run_dir / f".phase.{marker}").exists():
            detected_phase = phase
    if latest_outcome:
        outcome_val = latest_outcome.get("outcome", "")
        if outcome_val in ("scored", "finished"):
            detected_phase = outcome_val if outcome_val in phase_map else "finished"
        elif "failed" in outcome_val:
            detected_phase = outcome_val.replace("failed_", "")
        elif "blocked" in outcome_val:
            detected_phase = "admission"

    # --- Integrity ---
    receipt_digests = set()
    for pk in ("t0", "t15", "t30"):
        p = probes.get(pk)
        if p is not None:
            receipt_digests.add(p.get("receipt_digest", ""))
    receipts_match = len(receipt_digests) <= 1

    journal_verified = bool(journal and journal.get("nonce"))
    trap_cas_used = (run_dir / ".reconciler.lock").exists()
    state_consistent = (
        journal_verified
        and receipts_match
        and trap_cas_used
    )

    # --- Capability ---
    admission_passed = (run_dir / ".admission.passed").exists()
    engineering_completed = (run_dir / ".engineering.done").exists()
    contract_met = (run_dir / ".contract.met").exists()
    native_research_completed = (run_dir / ".native.done").exists()

    # --- Outcome ---
    has_failures = any(p["triggered"] for p in predicates
                       if p["predicate"] not in ("scored", "finished"))
    has_score = any(p["predicate"] == "scored" and p["triggered"] for p in predicates)
    termination_known = precedence_winner not in (
        "inconclusive_unknown_termination",
        "failed_reconciliation_unavailable",
    )

    return {
        "lifecycle": {
            "phase": detected_phase,
            "journal_present": journal is not None,
            "journal_nonce": journal.get("nonce") if journal else None,
            "probes": {
                "t0": probes.get("t0"),
                "t15": probes.get("t15"),
                "t30": probes.get("t30"),
            },
        },
        "integrity": {
            "journal_verified": journal_verified,
            "receipts_match": receipts_match,
            "trap_cas_used": trap_cas_used,
            "state_consistent": state_consistent,
        },
        "capability": {
            "admission_passed": admission_passed,
            "engineering_completed": engineering_completed,
            "contract_met": contract_met,
            "native_research_completed": native_research_completed,
        },
        "outcome": {
            "precedence_applied": True,
            "has_failures": has_failures,
            "score_available": has_score,
            "termination_known": termination_known,
        },
    }


# ---------------------------------------------------------------------------
# Evidence pointers
# ---------------------------------------------------------------------------

def build_evidence_pointers(
    run_dir: Path,
    journal: dict,
    probes: dict,
    predicates: list[dict],
    output_path: Path,
) -> dict:
    """Build evidence pointers for journal, probe receipts, predicate
    evaluations, and the outcome record."""
    probes_path = run_dir / ".probe_receipts.json"
    predicates_path = run_dir / ".predicate_evaluations.json"

    return {
        "journal": str(run_dir / ".journal.v1.json"),
        "probe_receipts": str(probes_path),
        "predicate_evaluations": str(predicates_path),
        "outcome_record": str(output_path),
    }


# ---------------------------------------------------------------------------
# Main reconciler
# ---------------------------------------------------------------------------

def reconcile_run(
    run_dir: Path,
    output_path: Path,
    classifier_version: str = CLASSIFIER_VERSION,
) -> dict:
    """Run full reconciliation on a single run directory.

    Steps:
      1. Acquire CAS lock.
      2. Journal (atomic write, idempotent).
      3. Probe at t=0s, t=15s, t=30s (±1s window).
      4. Evaluate every predicate.
      5. Resolve precedence winner.
      6. Evaluate dimensions.
      7. Build evidence pointers.
      8. Write outcome record.
    """
    run_dir = run_dir.resolve()
    output_path = output_path.resolve()

    # Step 1: CAS lock
    lock = CASLock(run_dir)
    with lock:
        lock_state = lock.read_state()
        lock_state["last_reconciled"] = now_iso()
        lock_state["reconciler_pid"] = os.getpid()
        lock.write_state(lock_state)

        # Step 2: Journal
        journal = journal_acquire(run_dir)

        # Step 3: Probe at monotonic t=0s, t=15s, t=30s
        t0 = monotonic_s()

        probe_t0 = probe(run_dir, 0.0)
        time.sleep(0.5)  # brief settle

        probe_t15 = probe(run_dir, 15.0)
        # Wait until we're at ~15s monotonic
        elapsed = monotonic_s() - t0
        if elapsed < 15.0 - PROBE_WINDOW_S:
            time.sleep(15.0 - PROBE_WINDOW_S - elapsed)
        probe_t15 = probe(run_dir, monotonic_s() - t0)

        elapsed = monotonic_s() - t0
        if elapsed < 30.0 - PROBE_WINDOW_S:
            time.sleep(30.0 - PROBE_WINDOW_S - elapsed)
        probe_t30 = probe(run_dir, monotonic_s() - t0)

        probes = {"t0": probe_t0, "t15": probe_t15, "t30": probe_t30}

        # Persist probe receipts
        probes_path = run_dir / ".probe_receipts.json"
        atomic_write(probes_path, probes)

        # Step 4: Evaluate predicates
        predicates = evaluate_predicates(run_dir, journal, probes)

        # Persist predicate evaluations
        predicates_path = run_dir / ".predicate_evaluations.json"
        atomic_write(predicates_path, {
            "predicates": predicates,
            "evaluated_at": now_iso(),
        })

        # Step 5: Resolve precedence (applied exactly once)
        precedence_winner = resolve_precedence(predicates)

        # Step 6: Evaluate dimensions
        dimensions = evaluate_dimensions(
            run_dir, journal, probes, predicates, precedence_winner,
        )

        # Step 7: Build evidence pointers
        evidence_pointers = build_evidence_pointers(
            run_dir, journal, probes, predicates, output_path,
        )

        # Step 8: Assemble outcome record
        outcome_record: dict = {
            "schema_version": SCHEMA_VERSION,
            "outcome": precedence_winner,
            "classifier_version": classifier_version,
            "dimensions": dimensions,
            "precedence_winner": precedence_winner,
            "failures": predicates,
            "evidence_pointers": evidence_pointers,
            "metadata": {
                "reconciled_at": now_iso(),
                "reconciler_version": RECONCILER_VERSION,
                "runs_root": str(run_dir.parent),
                "run_id": run_dir.name,
            },
        }

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(output_path, outcome_record)

        # Also write a local copy in the run dir
        local_outcome = run_dir / ".reconciled.outcome.v1.json"
        atomic_write(local_outcome, outcome_record)

    return outcome_record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile AI researcher runs: journal, probe, classify.",
    )
    parser.add_argument(
        "--runs-root",
        required=True,
        type=Path,
        help="Root directory containing run subdirectories.",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Run classification (reconciliation). Required.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the outcome JSON record.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Specific run ID to reconcile. If omitted, reconciles the latest run.",
    )
    parser.add_argument(
        "--classifier-version",
        type=str,
        default=CLASSIFIER_VERSION,
        help=f"Classifier version string (default: {CLASSIFIER_VERSION}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    runs_root: Path = args.runs_root
    if not runs_root.is_dir():
        print(f"FATAL: --runs-root {runs_root} is not a directory.", file=sys.stderr)
        return 1

    # Discover run directories
    run_dirs: list[Path] = sorted([
        p for p in runs_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ])

    if not run_dirs:
        print(f"FATAL: No run directories found under {runs_root}.", file=sys.stderr)
        return 1

    # Select run
    if args.run_id:
        target = runs_root / args.run_id
        if not target.is_dir():
            print(f"FATAL: --run-id {args.run_id} not found under {runs_root}.", file=sys.stderr)
            return 1
        selected = [target]
    else:
        selected = [run_dirs[-1]]  # latest

    if args.classify:
        for run_dir in selected:
            outcome = reconcile_run(
                run_dir,
                output_path=args.output,
                classifier_version=args.classifier_version,
            )
            print(
                f"Reconciled {run_dir.name}: {outcome['outcome']} "
                f"→ {args.output}",
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
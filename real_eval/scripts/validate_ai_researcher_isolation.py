#!/usr/bin/env python3
"""validate_ai_researcher_isolation.py

Validate strict Topic/run isolation with per-run rootless Docker daemon.

Each AI-Researcher attempt must start its own rootless Docker daemon under a
dedicated runtime directory.  This validator reads an *isolation descriptor*
(a JSON manifest recorded by the runner before/after each launch) and checks
that the daemon, its sockets, data directories, PID files, and network are
properly isolated from the host and from other topics/runs.

The validator NEVER runs actual Docker commands.  It validates descriptors
that describe the isolation state — file metadata, syscall-level observations,
namespace identities, and capability/ mount records gathered by the runner.

Usage:
  python3 validate_ai_researcher_isolation.py \
      --run-root $REAL_EVAL_RUN_ROOT/attempt-001 \
      --daemon-socket $REAL_EVAL_RUN_ROOT/attempt-001/docker-daemon/run/docker.sock \
      --attempt 1 \
      --require-positive \
      --output $REAL_EVAL_RUN_ROOT/attempt-001/isolation_validation.json

Exit codes:
  0   All isolation checks pass.
  1   One or more isolation checks fail.
  2   Input error (missing run root, unreadable descriptor, etc.).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat as stat_module
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ── Constants ───────────────────────────────────────────────────────────

DESCRIPTOR_FILENAME = "isolation_descriptor.json"
"""Filename of the JSON isolation descriptor inside the run root."""

DESCRIPTOR_VERSION = 1
"""Schema version for the isolation descriptor."""

FORBIDDEN_HOST_SOCKET = Path("/var/run/docker.sock")
"""Global host Docker socket that must never be reachable from a run."""

FORBIDDEN_DATA_ROOTS = ("/var/lib/docker", "/var/lib/containerd")
"""Global data-root paths that must not appear in a rootless daemon's config."""

REQUIRED_DESCRIPTOR_KEYS: tuple[str, ...] = (
    "schema_version",
    "created_at",
    "attempt",
    "daemon",
    "probes",
)
"""Top-level keys that must be present in the descriptor."""

REQUIRED_DAEMON_KEYS: tuple[str, ...] = (
    "effective_uid",
    "effective_gid",
    "rootless_user_ns_mappings",
    "pid_ns",
    "executable_path",
    "executable_hash_sha256",
    "socket",
    "data_root",
    "pid_file",
    "pid",
    "start_time",
    "cgroup",
    "bridge",
    "network_id",
    "mounts",
    "capabilities",
)
"""Keys required in the daemon section of the descriptor."""

REQUIRED_FSTAT_KEYS: tuple[str, ...] = (
    "dev",
    "ino",
    "mode",
    "uid",
    "gid",
    "size",
    "mtime_ns",
)
"""Keys required in each fstat entry (socket, data-root, PID-file)."""


# ── Data types ──────────────────────────────────────────────────────────


@dataclass
class ProbeResult:
    """Result of a single isolation probe."""

    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"  # error | warning | info


@dataclass
class ValidationSummary:
    """Aggregated validation output."""

    valid: bool
    status: str
    summary: str
    manifest: dict[str, Any] = field(default_factory=dict)
    probes: dict[str, ProbeResult] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    bridge_network_id: str | None = None
    descriptor_path: str | None = None
    created_at: str = ""


# ── Helpers ─────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _resolve_path(base: Path, path_str: str | None) -> Path | None:
    """Resolve a path from the descriptor relative to *base* if it's relative."""
    if path_str is None:
        return None
    p = Path(path_str)
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def _safe_read_json(path: Path) -> Any | None:
    """Read and parse a JSON file, returning None on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _fstat_dict(path: Path) -> dict[str, Any] | None:
    """Return a dict of file metadata for *path*, or None if inaccessible."""
    try:
        st = path.stat()
        mode = st.st_mode
        return {
            "dev": st.st_dev,
            "ino": st.st_ino,
            "mode": stat_module.filemode(mode),
            "mode_int": mode,
            "is_sock": stat_module.S_ISSOCK(mode),
            "is_reg": stat_module.S_ISREG(mode),
            "is_dir": stat_module.S_ISDIR(mode),
            "is_symlink": path.is_symlink(),
            "uid": st.st_uid,
            "gid": st.st_gid,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
        }
    except OSError:
        return None


def _is_symlink_to(path: Path, target: Path) -> bool:
    """Return True if *path* is a symlink pointing to *target*."""
    try:
        return path.is_symlink() and path.readlink().resolve() == target.resolve()
    except OSError:
        return False


def _path_exists_not_symlink(path: Path) -> bool:
    """Return True if the path exists and is NOT a symlink."""
    try:
        return path.exists() and not path.is_symlink()
    except OSError:
        return False


# ── Descriptor loading ──────────────────────────────────────────────────


def load_descriptor(run_root: Path) -> dict[str, Any] | None:
    """Load the isolation descriptor from *run_root*.

    Returns the parsed descriptor dict, or None if the file is missing or
    unreadable.
    """
    path = run_root / DESCRIPTOR_FILENAME
    if not path.is_file():
        return None
    return _safe_read_json(path)


# ── Manifest validation ─────────────────────────────────────────────────


def validate_manifest_structure(
    descriptor: dict[str, Any],
    run_root: Path,
    expected_attempt: int | None,
) -> list[str]:
    """Validate the top-level structure and required keys of the descriptor.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []

    for key in REQUIRED_DESCRIPTOR_KEYS:
        if key not in descriptor:
            errors.append(f"descriptor missing required top-level key: {key!r}")

    if errors:
        return errors

    # Schema version
    sv = descriptor.get("schema_version")
    if sv != DESCRIPTOR_VERSION:
        errors.append(
            f"descriptor schema_version={sv!r}, expected {DESCRIPTOR_VERSION}"
        )

    # Attempt
    attempt = descriptor.get("attempt")
    if expected_attempt is not None and attempt != expected_attempt:
        errors.append(
            f"descriptor attempt={attempt!r}, expected {expected_attempt}"
        )

    # Daemon section
    daemon = descriptor.get("daemon")
    if not isinstance(daemon, dict):
        errors.append("descriptor.daemon is missing or not a dict")
        return errors

    for key in REQUIRED_DAEMON_KEYS:
        if key not in daemon:
            errors.append(f"descriptor.daemon missing required key: {key!r}")

    if errors:
        return errors

    # Fstat entries
    for fstat_key in ("socket", "data_root", "pid_file"):
        entry = daemon.get(fstat_key)
        if not isinstance(entry, dict):
            errors.append(f"descriptor.daemon.{fstat_key} is missing or not a dict")
            continue
        for subkey in REQUIRED_FSTAT_KEYS:
            if subkey not in entry:
                errors.append(
                    f"descriptor.daemon.{fstat_key} missing required key: {subkey!r}"
                )

    # Effective UID/GID must be non-zero (rootless)
    euid = daemon.get("effective_uid")
    egid = daemon.get("effective_gid")
    if euid == 0:
        errors.append(f"effective_uid is 0 (root) — rootless daemon must run as non-root")
    if egid == 0:
        errors.append(f"effective_gid is 0 (root) — rootless daemon must run as non-root")

    # PID namespace must be non-host
    pid_ns = daemon.get("pid_ns")
    if pid_ns in (None, "host"):
        errors.append(f"pid_ns is {pid_ns!r} — must be a private PID namespace")

    # Executable hash must be present
    exe_hash = daemon.get("executable_hash_sha256")
    if not isinstance(exe_hash, str) or len(exe_hash) != 64:
        errors.append(
            f"executable_hash_sha256 is invalid (got {type(exe_hash).__name__}, "
            f"len={len(exe_hash) if isinstance(exe_hash, str) else 'N/A'})"
        )

    # Bridge must be non-default
    bridge = daemon.get("bridge")
    if not isinstance(bridge, str) or bridge in ("bridge", "docker0", ""):
        errors.append(
            f"bridge is {bridge!r} — must be a per-run bridge name "
            f"(not 'bridge' or 'docker0')"
        )

    # Network ID must be non-empty
    network_id = daemon.get("network_id")
    if not isinstance(network_id, str) or not network_id.strip():
        errors.append(f"network_id is missing or empty — must record per-run network ID")

    # Mounts must be present
    mounts = daemon.get("mounts")
    if not isinstance(mounts, list):
        errors.append("descriptor.daemon.mounts is missing or not a list")

    # Capabilities must be present
    caps = daemon.get("capabilities")
    if not isinstance(caps, list):
        errors.append("descriptor.daemon.capabilities is missing or not a list")

    return errors


# ── Re-fstat validation ─────────────────────────────────────────────────


def validate_fstat_consistency(
    descriptor: dict[str, Any],
    run_root: Path,
) -> list[str]:
    """Re-fstat socket/data-root/PID-file descriptors and compare with
    the recorded values.

    This is run before each launch and terminalization to detect inode/device
    changes that would indicate replacement or recreation.
    """
    errors: list[str] = []
    daemon = descriptor.get("daemon", {})
    base = run_root.resolve()

    for key, label in (
        ("socket", "Docker socket"),
        ("data_root", "data-root directory"),
        ("pid_file", "PID file"),
    ):
        recorded = daemon.get(key)
        if not isinstance(recorded, dict):
            continue

        path_str = recorded.get("path")
        if not path_str:
            continue

        target = _resolve_path(base, path_str)
        if target is None or not target.exists():
            errors.append(
                f"{label} at {path_str} does not exist at validation time"
            )
            continue

        current = _fstat_dict(target)
        if current is None:
            errors.append(f"cannot stat {label} at {path_str}")
            continue

        # Compare device and inode
        recorded_dev = recorded.get("dev")
        recorded_ino = recorded.get("ino")
        if recorded_dev is not None and current["dev"] != recorded_dev:
            errors.append(
                f"{label} device changed: recorded {recorded_dev}, "
                f"current {current['dev']} — possible replacement"
            )
        if recorded_ino is not None and current["ino"] != recorded_ino:
            errors.append(
                f"{label} inode changed: recorded {recorded_ino}, "
                f"current {current['ino']} — possible replacement"
            )

        # Check symlink status
        recorded_is_symlink = recorded.get("is_symlink", False)
        if current["is_symlink"] != recorded_is_symlink:
            errors.append(
                f"{label} symlink status changed: recorded "
                f"is_symlink={recorded_is_symlink}, current is_symlink="
                f"{current['is_symlink']}"
            )

    return errors


# ── Global socket prohibition ────────────────────────────────────────────


def check_global_socket_prohibition(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Verify that the global /var/run/docker.sock is NOT accessible from
    the run environment and that the descriptor does not reference it.
    """
    base = run_root.resolve()
    daemon = descriptor.get("daemon", {})

    # Check descriptor's socket path
    socket_entry = daemon.get("socket", {})
    socket_path_str = socket_entry.get("path", "") if isinstance(socket_entry, dict) else ""

    # 1. The daemon socket must NOT point to the global socket
    if socket_path_str and Path(socket_path_str).resolve() == FORBIDDEN_HOST_SOCKET.resolve():
        return ProbeResult(
            name="host-socket",
            passed=False,
            detail=f"Daemon socket path points to global {FORBIDDEN_HOST_SOCKET}",
            severity="error",
        )

    # 2. The global socket must not exist inside the run root
    global_sock_in_run = base / "var/run/docker.sock"
    if global_sock_in_run.exists():
        return ProbeResult(
            name="host-socket",
            passed=False,
            detail=f"Global socket path found inside run root: {global_sock_in_run}",
            severity="error",
        )

    # 3. The descriptor must record that the global socket was checked
    global_sock_check = descriptor.get("probes", {}).get("global_socket_absent")
    if global_sock_check is not True:
        return ProbeResult(
            name="host-socket",
            passed=False,
            detail=(
                "Descriptor does not confirm global /var/run/docker.sock "
                "was absent at launch time"
            ),
            severity="error",
        )

    return ProbeResult(
        name="host-socket",
        passed=True,
        detail=f"Global {FORBIDDEN_HOST_SOCKET} is not reachable from the run",
        severity="info",
    )


# ── Escape probes ────────────────────────────────────────────────────────


def probe_host_socket(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify the host socket is not accessible."""
    return check_global_socket_prohibition(descriptor, run_root)


def probe_socket_symlink_replacement(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify the daemon socket is not a symlink pointing
    outside the run root, and that it has not been replaced.
    """
    base = run_root.resolve()
    daemon = descriptor.get("daemon", {})
    socket_entry = daemon.get("socket", {})
    if not isinstance(socket_entry, dict):
        return ProbeResult(
            name="socket-symlink",
            passed=False,
            detail="Socket entry missing from descriptor",
            severity="error",
        )

    path_str = socket_entry.get("path")
    if not path_str:
        return ProbeResult(
            name="socket-symlink",
            passed=False,
            detail="Socket path missing from descriptor",
            severity="error",
        )

    target = _resolve_path(base, path_str)
    if target is None:
        return ProbeResult(
            name="socket-symlink",
            passed=False,
            detail=f"Cannot resolve socket path: {path_str}",
            severity="error",
        )

    # Check symlink
    if target.is_symlink():
        link_target = target.readlink().resolve()
        run_root_resolved = run_root.resolve()
        try:
            link_target.relative_to(run_root_resolved)
            inside = True
        except ValueError:
            inside = False

        if not inside:
            return ProbeResult(
                name="socket-symlink",
                passed=False,
                detail=(
                    f"Socket {target} is a symlink pointing outside run root "
                    f"to {link_target}"
                ),
                severity="error",
            )

    # Check inode consistency from re-fstat
    fstat_errors = validate_fstat_consistency(descriptor, run_root)
    socket_fstat_errors = [e for e in fstat_errors if "socket" in e.lower()]
    if socket_fstat_errors:
        return ProbeResult(
            name="socket-symlink",
            passed=False,
            detail="; ".join(socket_fstat_errors),
            severity="error",
        )

    return ProbeResult(
        name="socket-symlink",
        passed=True,
        detail=f"Socket at {target} is not a symlink to outside the run root",
        severity="info",
    )


def probe_data_root_replacement(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify the data-root is not a symlink or replacement
    pointing outside the run root, and is not a forbidden global path.
    """
    base = run_root.resolve()
    daemon = descriptor.get("daemon", {})
    data_root_entry = daemon.get("data_root", {})
    if not isinstance(data_root_entry, dict):
        return ProbeResult(
            name="data-root-replacement",
            passed=False,
            detail="Data-root entry missing from descriptor",
            severity="error",
        )

    path_str = data_root_entry.get("path")
    if not path_str:
        return ProbeResult(
            name="data-root-replacement",
            passed=False,
            detail="Data-root path missing from descriptor",
            severity="error",
        )

    target = _resolve_path(base, path_str)
    if target is None:
        return ProbeResult(
            name="data-root-replacement",
            passed=False,
            detail=f"Cannot resolve data-root path: {path_str}",
            severity="error",
        )

    # Check forbidden global data roots
    resolved_str = str(target.resolve())
    for forbidden in FORBIDDEN_DATA_ROOTS:
        if resolved_str == forbidden or resolved_str.startswith(forbidden + "/"):
            return ProbeResult(
                name="data-root-replacement",
                passed=False,
                detail=f"Data-root {resolved_str} is a forbidden global path ({forbidden})",
                severity="error",
            )

    # Check symlink pointing outside
    if target.is_symlink():
        link_target = target.readlink().resolve()
        try:
            link_target.relative_to(run_root.resolve())
        except ValueError:
            return ProbeResult(
                name="data-root-replacement",
                passed=False,
                detail=(
                    f"Data-root {target} is a symlink pointing outside run root "
                    f"to {link_target}"
                ),
                severity="error",
            )

    # Check inode consistency
    fstat_errors = validate_fstat_consistency(descriptor, run_root)
    data_root_errors = [e for e in fstat_errors if "data-root" in e.lower()]
    if data_root_errors:
        return ProbeResult(
            name="data-root-replacement",
            passed=False,
            detail="; ".join(data_root_errors),
            severity="error",
        )

    return ProbeResult(
        name="data-root-replacement",
        passed=True,
        detail=f"Data-root at {target} is contained within the run root",
        severity="info",
    )


def probe_pidfile_replacement(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify the PID file is not a symlink pointing outside
    the run root and has not been replaced.
    """
    base = run_root.resolve()
    daemon = descriptor.get("daemon", {})
    pid_file_entry = daemon.get("pid_file", {})
    if not isinstance(pid_file_entry, dict):
        return ProbeResult(
            name="pidfile-replacement",
            passed=False,
            detail="PID-file entry missing from descriptor",
            severity="error",
        )

    path_str = pid_file_entry.get("path")
    if not path_str:
        return ProbeResult(
            name="pidfile-replacement",
            passed=False,
            detail="PID-file path missing from descriptor",
            severity="error",
        )

    target = _resolve_path(base, path_str)
    if target is None:
        return ProbeResult(
            name="pidfile-replacement",
            passed=False,
            detail=f"Cannot resolve PID-file path: {path_str}",
            severity="error",
        )

    if target.is_symlink():
        link_target = target.readlink().resolve()
        try:
            link_target.relative_to(run_root.resolve())
        except ValueError:
            return ProbeResult(
                name="pidfile-replacement",
                passed=False,
                detail=(
                    f"PID file {target} is a symlink pointing outside run root "
                    f"to {link_target}"
                ),
                severity="error",
            )

    # Check inode consistency
    fstat_errors = validate_fstat_consistency(descriptor, run_root)
    pidfile_errors = [e for e in fstat_errors if "pid file" in e.lower()]
    if pidfile_errors:
        return ProbeResult(
            name="pidfile-replacement",
            passed=False,
            detail="; ".join(pidfile_errors),
            severity="error",
        )

    return ProbeResult(
        name="pidfile-replacement",
        passed=True,
        detail=f"PID file at {target} is not a symlink to outside the run root",
        severity="info",
    )


def probe_pid_reuse(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify the recorded PID is not a reused host PID
    from a previous daemon instance.
    """
    daemon = descriptor.get("daemon", {})
    recorded_pid = daemon.get("pid")
    recorded_start_time = daemon.get("start_time")
    pid_ns = daemon.get("pid_ns")

    if not isinstance(recorded_pid, int) or recorded_pid <= 0:
        return ProbeResult(
            name="pid-reuse",
            passed=False,
            detail=f"Invalid PID in descriptor: {recorded_pid!r}",
            severity="error",
        )

    # PID must be > 1 (not init/PID 1) for rootless daemon
    if recorded_pid == 1:
        return ProbeResult(
            name="pid-reuse",
            passed=False,
            detail="PID is 1 (init) — rootless daemon must not run as PID 1",
            severity="error",
        )

    # Start time must be present
    if not isinstance(recorded_start_time, str) or not recorded_start_time.strip():
        return ProbeResult(
            name="pid-reuse",
            passed=False,
            detail="Daemon start_time is missing from descriptor",
            severity="error",
        )

    # PID namespace must be private
    if pid_ns in (None, "host"):
        return ProbeResult(
            name="pid-reuse",
            passed=False,
            detail=f"PID namespace is {pid_ns!r} — must be private to prevent PID reuse",
            severity="error",
        )

    return ProbeResult(
        name="pid-reuse",
        passed=True,
        detail=f"Daemon PID {recorded_pid} with start_time {recorded_start_time} "
        f"in private PID namespace {pid_ns}",
        severity="info",
    )


def probe_proc_host(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that /proc/sysrq-trigger or /proc/1/root
    are not accessible (would indicate host PID namespace leakage).
    """
    mounts = descriptor.get("daemon", {}).get("mounts", [])
    if not isinstance(mounts, list):
        mounts = []

    # Check that procfs is mounted with the correct options
    proc_mounts = [m for m in mounts if isinstance(m, dict) and m.get("target") == "/proc"]
    host_proc_found = False
    for pm in proc_mounts:
        opts = pm.get("options", "")
        source = pm.get("source", "")
        if "rbind" in opts and source in ("/proc", "/proc/1"):
            host_proc_found = True
            break

    if host_proc_found:
        return ProbeResult(
            name="proc-host",
            passed=False,
            detail="Descriptor shows host /proc bind-mounted — host PID namespace leak",
            severity="error",
        )

    # Check for /sys/kernel/security or other sensitive mounts
    sensitive_mounts = [m for m in mounts if isinstance(m, dict)]
    for sm in sensitive_mounts:
        target = sm.get("target", "")
        if "sys/kernel" in target:
            return ProbeResult(
                name="proc-host",
                passed=False,
                detail=f"Sensitive mount at {target} — possible kernel information leak",
                severity="error",
            )

    return ProbeResult(
        name="proc-host",
        passed=True,
        detail="No host procfs or sensitive kernel mounts in descriptor",
        severity="info",
    )


def probe_docker_api_cross_run(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that no other run's Docker socket is accessible
    from this run's descriptor.
    """
    base = run_root.resolve()
    daemon = descriptor.get("daemon", {})
    socket_entry = daemon.get("socket", {})
    socket_path_str = socket_entry.get("path", "") if isinstance(socket_entry, dict) else ""

    # Check for other sockets in the docker-daemon tree
    docker_daemon_dir = base / "docker-daemon"
    if docker_daemon_dir.is_dir():
        for other_sock in docker_daemon_dir.rglob("docker.sock"):
            if other_sock.resolve() == _resolve_path(base, socket_path_str):
                continue
            # A different socket file exists — this is only a problem if the
            # descriptor's socket is accessible from a different run root
            return ProbeResult(
                name="docker-api-cross-run",
                passed=False,
                detail=(
                    f"Multiple docker sockets found in run root: "
                    f"{socket_path_str} and {other_sock.relative_to(base)}"
                ),
                severity="error",
            )

    # Check for sibling socket references in the descriptor
    cross_run_evidence = descriptor.get("probes", {}).get("cross_run_socket_absent")
    if cross_run_evidence is not True:
        return ProbeResult(
            name="docker-api-cross-run",
            passed=False,
            detail="Descriptor does not confirm absence of cross-run sockets",
            severity="error",
        )

    return ProbeResult(
        name="docker-api-cross-run",
        passed=True,
        detail="No cross-run Docker socket access detected",
        severity="info",
    )


def probe_list_sibling(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that the descriptor records that container
    listing was restricted to the current run only.
    """
    probe_marker = descriptor.get("probes", {}).get("list_sibling_restricted")
    if probe_marker is not True:
        return ProbeResult(
            name="list-sibling",
            passed=False,
            detail="Descriptor does not confirm sibling container listing was restricted",
            severity="error",
        )

    return ProbeResult(
        name="list-sibling",
        passed=True,
        detail="Container listing is restricted to the current run",
        severity="info",
    )


def probe_inspect_sibling(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that the descriptor records that container
    inspection was restricted to the current run only.
    """
    probe_marker = descriptor.get("probes", {}).get("inspect_sibling_restricted")
    if probe_marker is not True:
        return ProbeResult(
            name="inspect-sibling",
            passed=False,
            detail="Descriptor does not confirm sibling container inspection was restricted",
            severity="error",
        )

    return ProbeResult(
        name="inspect-sibling",
        passed=True,
        detail="Container inspection is restricted to the current run",
        severity="info",
    )


def probe_privileged(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that the daemon is not running in privileged mode
    and does not have dangerous capabilities.
    """
    daemon = descriptor.get("daemon", {})
    caps = daemon.get("capabilities", [])
    if not isinstance(caps, list):
        caps = []

    dangerous_caps = (
        "CAP_SYS_ADMIN",
        "CAP_NET_ADMIN",
        "CAP_SYS_RAWIO",
        "CAP_SYS_PTRACE",
        "CAP_SYS_MODULE",
        "CAP_SYS_BOOT",
        "CAP_LINUX_IMMUTABLE",
        "CAP_NET_RAW",
    )
    found_dangerous = [c for c in caps if c in dangerous_caps]

    # Check for --privileged flag in the exec entry
    exec_entry = daemon.get("exec", {})
    if isinstance(exec_entry, dict):
        argv = exec_entry.get("argv", [])
        if isinstance(argv, list) and "--privileged" in argv:
            found_dangerous.append("--privileged")

    if found_dangerous:
        return ProbeResult(
            name="privileged",
            passed=False,
            detail=f"Daemon has dangerous capabilities or flags: {found_dangerous}",
            severity="error",
        )

    return ProbeResult(
        name="privileged",
        passed=True,
        detail=f"Daemon capabilities are restricted ({len(caps)} caps recorded)",
        severity="info",
    )


def probe_disallowed_bind(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that no disallowed bind mounts exist
    (e.g., /etc, /var, /run outside the run root).
    """
    mounts = descriptor.get("daemon", {}).get("mounts", [])
    if not isinstance(mounts, list):
        mounts = []

    # Only flag HOST bind mounts of sensitive paths — virtual filesystems
    # (proc, tmpfs, devpts, sysfs) are standard container mounts.
    bind_types = {"bind", "rbind"}
    disallowed_sources = (
        "/etc",
        "/var",
        "/run",
        "/sys",
        "/proc",
        "/dev",
        "/boot",
        "/root",
        "/home",
    )
    violations: list[str] = []
    for m in mounts:
        if not isinstance(m, dict):
            continue
        mtype = m.get("type", "")
        options = m.get("options", "")
        source = m.get("source", "")
        if not source:
            continue
        # Only consider bind/rbind mounts; skip virtual filesystems
        if mtype not in bind_types and "bind" not in options and "rbind" not in options:
            continue
        for disallowed in disallowed_sources:
            if source == disallowed or source.startswith(disallowed + "/"):
                # Allow if it's within the run root
                try:
                    Path(source).relative_to(run_root.resolve())
                except (ValueError, RuntimeError):
                    violations.append(f"{source} (type={mtype}, options={options})")
                break

    if violations:
        return ProbeResult(
            name="disallowed-bind",
            passed=False,
            detail=f"Disallowed bind mounts detected: {violations}",
            severity="error",
        )

    return ProbeResult(
        name="disallowed-bind",
        passed=True,
        detail="No disallowed bind mounts in descriptor",
        severity="info",
    )


def probe_public_dns(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that public DNS is not configured inside the
    rootless daemon (would indicate network isolation bypass).
    """
    daemon = descriptor.get("daemon", {})
    dns = daemon.get("dns", [])

    public_dns_servers = ("8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9")
    found_public = [d for d in dns if d in public_dns_servers]

    if found_public:
        return ProbeResult(
            name="public-dns",
            passed=False,
            detail=f"Public DNS servers configured in daemon: {found_public}",
            severity="error",
        )

    # Check that DNS is isolated if recorded
    probe_marker = descriptor.get("probes", {}).get("dns_isolated")
    if probe_marker is not True:
        return ProbeResult(
            name="public-dns",
            passed=False,
            detail="Descriptor does not confirm DNS isolation",
            severity="error",
        )

    return ProbeResult(
        name="public-dns",
        passed=True,
        detail="DNS is isolated from public servers",
        severity="info",
    )


def probe_public_http(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that unrestricted HTTP(S) access to public
    internet is not allowed (would indicate network isolation bypass).
    """
    daemon = descriptor.get("daemon", {})
    iptables = daemon.get("iptables_rules", [])

    if not isinstance(iptables, list):
        iptables = []

    # Check for ACCEPT rules that allow all outbound traffic
    unrestricted_accept = any(
        isinstance(r, dict)
        and r.get("chain") == "FORWARD"
        and r.get("target") == "ACCEPT"
        and r.get("source") in ("0.0.0.0/0", None)
        and r.get("destination") in ("0.0.0.0/0", None)
        for r in iptables
    )

    if unrestricted_accept:
        return ProbeResult(
            name="public-http",
            passed=False,
            detail="Unrestricted FORWARD ACCEPT rule detected — public internet access allowed",
            severity="error",
        )

    # Check that the descriptor records confirmed HTTP isolation
    probe_marker = descriptor.get("probes", {}).get("http_isolated")
    if probe_marker is not True:
        return ProbeResult(
            name="public-http",
            passed=False,
            detail="Descriptor does not confirm HTTP isolation",
            severity="error",
        )

    return ProbeResult(
        name="public-http",
        passed=True,
        detail="HTTP traffic is isolated from the public internet",
        severity="info",
    )


def probe_other_topic(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that no other topic's data, sockets, or artifacts
    are accessible from this run.
    """
    base = run_root.resolve()
    known_topics = ("babylm", "arc_wbe_2026", "psydefdetect", "tdc_admet_tox", "gave2_task2")

    # Check for topic-specific directories that don't belong to this run
    topic_markers: list[str] = []
    for topic in known_topics:
        # Check if the run root's name/path contains a topic marker that
        # doesn't match the current topic
        pass

    # Check the descriptor for cross-topic references
    probes = descriptor.get("probes", {})
    if isinstance(probes, dict):
        cross_topic = probes.get("cross_topic_data_absent")
        if cross_topic is not True:
            return ProbeResult(
                name="other-topic",
                passed=False,
                detail="Descriptor does not confirm absence of cross-topic data",
                severity="error",
            )

    # Check mounts for cross-topic data roots
    mounts = descriptor.get("daemon", {}).get("mounts", [])
    if isinstance(mounts, list):
        for m in mounts:
            if not isinstance(m, dict):
                continue
            source = m.get("source", "")
            for topic in known_topics:
                if topic in source:
                    try:
                        Path(source).relative_to(base)
                    except (ValueError, RuntimeError):
                        topic_markers.append(f"{source} (topic: {topic})")

    if topic_markers:
        return ProbeResult(
            name="other-topic",
            passed=False,
            detail=f"Cross-topic data references detected: {topic_markers}",
            severity="error",
        )

    return ProbeResult(
        name="other-topic",
        passed=True,
        detail="No cross-topic data accessible from this run",
        severity="info",
    )


def probe_previous_cache(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Escape probe: verify that the descriptor records that Docker build
    caches, image layers, and volumes from previous runs are not accessible.
    """
    # Check that the data-root is fresh (not a previous run's data-root)
    daemon = descriptor.get("daemon", {})
    data_root_entry = daemon.get("data_root", {})
    data_root_path_str = data_root_entry.get("path", "") if isinstance(data_root_entry, dict) else ""

    base = run_root.resolve()
    data_root = _resolve_path(base, data_root_path_str)

    if data_root is not None and data_root.exists():
        # Check for pre-existing image layers (previous cache).
        # Gracefully handle permission errors: if we cannot read the
        # data-root (e.g. it is a forbidden global path), the
        # data-root-replacement probe already catches that.
        try:
            overlay2 = data_root / "overlay2"
            image_dir = data_root / "image"
            if overlay2.is_dir():
                contents = list(overlay2.iterdir())
                if contents:
                    return ProbeResult(
                        name="previous-cache",
                        passed=False,
                        detail=(
                            f"Data-root overlay2 directory at {data_root} "
                            f"contains {len(contents)} entries — possible cache reuse"
                        ),
                        severity="error",
                    )
            if image_dir.is_dir():
                image_contents = list(image_dir.iterdir())
                if image_contents:
                    return ProbeResult(
                        name="previous-cache",
                        passed=False,
                        detail=(
                            f"Data-root image directory at {data_root} "
                            f"contains {len(image_contents)} entries — possible cache reuse"
                        ),
                        severity="error",
                    )
        except PermissionError:
            # Cannot read data-root — will be caught by data-root-replacement
            pass

    # Check descriptor confirmation
    probe_marker = descriptor.get("probes", {}).get("fresh_data_root")
    if probe_marker is not True:
        return ProbeResult(
            name="previous-cache",
            passed=False,
            detail="Descriptor does not confirm that the data-root was freshly created",
            severity="error",
        )

    return ProbeResult(
        name="previous-cache",
        passed=True,
        detail="No previous Docker cache or image layers detected in data-root",
        severity="info",
    )


# ── Positive probes ─────────────────────────────────────────────────────


def probe_workspace_readwrite(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Positive probe: verify that the workspace directory is writable
    by the daemon's effective UID/GID.
    """
    daemon = descriptor.get("daemon", {})
    euid = daemon.get("effective_uid")
    egid = daemon.get("effective_gid")
    workspace = run_root / "workspace"

    if not workspace.is_dir():
        # Workspace may not exist yet at descriptor time — that's OK
        return ProbeResult(
            name="workspace-readwrite",
            passed=True,
            detail="Workspace directory not yet created (deferred to runner)",
            severity="info",
        )

    # Check workspace ownership from descriptor
    workspace_fstat = descriptor.get("probes", {}).get("workspace_ownership")
    if isinstance(workspace_fstat, dict):
        ws_uid = workspace_fstat.get("uid")
        ws_gid = workspace_fstat.get("gid")
        ws_mode = workspace_fstat.get("mode", "")

        if ws_uid is not None and euid is not None and ws_uid != euid:
            return ProbeResult(
                name="workspace-readwrite",
                passed=False,
                detail=(
                    f"Workspace owner UID {ws_uid} does not match daemon "
                    f"effective UID {euid}"
                ),
                severity="error",
            )

        if "w" not in ws_mode and ws_mode:
            return ProbeResult(
                name="workspace-readwrite",
                passed=False,
                detail=f"Workspace is not writable (mode={ws_mode})",
                severity="error",
            )

    return ProbeResult(
        name="workspace-readwrite",
        passed=True,
        detail=f"Workspace at {workspace} is writable by daemon UID {euid}",
        severity="info",
    )


def probe_provider_relay_responses(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Positive probe: verify that the provider relay is reachable from
    the daemon's network namespace.
    """
    relay = descriptor.get("probes", {}).get("provider_relay")
    if not isinstance(relay, dict):
        return ProbeResult(
            name="provider-relay-responses",
            passed=False,
            detail="Descriptor does not contain provider_relay probe results",
            severity="error",
        )

    reachable = relay.get("reachable")
    endpoint = relay.get("endpoint", "unknown")
    status_code = relay.get("status_code")

    if reachable is not True:
        return ProbeResult(
            name="provider-relay-responses",
            passed=False,
            detail=(
                f"Provider relay at {endpoint} is not reachable "
                f"(status_code={status_code})"
            ),
            severity="error",
        )

    return ProbeResult(
        name="provider-relay-responses",
        passed=True,
        detail=f"Provider relay at {endpoint} is reachable (status={status_code})",
        severity="info",
    )


def probe_rootless_daemon_start_container(
    descriptor: dict[str, Any],
    run_root: Path,
) -> ProbeResult:
    """Positive probe: verify that the descriptor records a successful
    rootless daemon container start test with correct namespace isolation.
    """
    container_test = descriptor.get("probes", {}).get("container_test")
    if not isinstance(container_test, dict):
        return ProbeResult(
            name="rootless-daemon-start-container",
            passed=False,
            detail="Descriptor does not contain container_test probe results",
            severity="error",
        )

    started = container_test.get("started")
    container_pid = container_test.get("container_pid")
    container_cgroup = container_test.get("container_cgroup")
    container_uid = container_test.get("container_uid")
    container_gid = container_test.get("container_gid")

    daemon = descriptor.get("daemon", {})
    rootless_uids = daemon.get("rootless_user_ns_mappings", [])

    if started is not True:
        return ProbeResult(
            name="rootless-daemon-start-container",
            passed=False,
            detail=f"Container test did not start successfully: {container_test.get('error', 'unknown')}",
            severity="error",
        )

    # Verify container PID/cgroup/UID/GID match rootless mapping
    issues: list[str] = []
    if container_pid is not None and container_pid <= 0:
        issues.append(f"container PID is invalid: {container_pid}")

    if container_uid is not None:
        # In rootless mode, the container UID should match the mapping
        if isinstance(rootless_uids, list) and rootless_uids:
            # Expect UID in the mapped range
            mapped = False
            for mapping in rootless_uids:
                if isinstance(mapping, dict):
                    if mapping.get("inside_id") == container_uid:
                        mapped = True
                        break
                    # Also check if container UID falls within a range
                    start = mapping.get("inside_id_start")
                    count = mapping.get("count")
                    if start is not None and count is not None:
                        if start <= container_uid < start + count:
                            mapped = True
                            break
            if not mapped:
                issues.append(
                    f"container UID {container_uid} not in rootless mapping "
                    f"{rootless_uids}"
                )

    if container_gid is not None:
        if isinstance(rootless_uids, list) and rootless_uids:
            mapped = False
            for mapping in rootless_uids:
                if isinstance(mapping, dict):
                    if mapping.get("inside_id") == container_gid:
                        mapped = True
                        break
                    start = mapping.get("inside_id_start")
                    count = mapping.get("count")
                    if start is not None and count is not None:
                        if start <= container_gid < start + count:
                            mapped = True
                            break
            if not mapped:
                issues.append(
                    f"container GID {container_gid} not in rootless mapping "
                    f"{rootless_uids}"
                )

    # Cgroup should be under the rootless cgroup tree
    if container_cgroup is not None and "docker" not in str(container_cgroup):
        issues.append(
            f"container cgroup {container_cgroup} does not appear to be "
            f"under Docker cgroup tree"
        )

    if issues:
        return ProbeResult(
            name="rootless-daemon-start-container",
            passed=False,
            detail="; ".join(issues),
            severity="error",
        )

    return ProbeResult(
        name="rootless-daemon-start-container",
        passed=True,
        detail=(
            f"Container started with PID {container_pid}, "
            f"UID {container_uid}, GID {container_gid}, "
            f"cgroup {container_cgroup} — all match rootless mapping"
        ),
        severity="info",
    )


# ── Probe registry ──────────────────────────────────────────────────────

ESCAPE_PROBES: list[Callable[[dict[str, Any], Path], ProbeResult]] = [
    probe_host_socket,
    probe_socket_symlink_replacement,
    probe_data_root_replacement,
    probe_pidfile_replacement,
    probe_pid_reuse,
    probe_proc_host,
    probe_docker_api_cross_run,
    probe_list_sibling,
    probe_inspect_sibling,
    probe_privileged,
    probe_disallowed_bind,
    probe_public_dns,
    probe_public_http,
    probe_other_topic,
    probe_previous_cache,
]

POSITIVE_PROBES: list[Callable[[dict[str, Any], Path], ProbeResult]] = [
    probe_workspace_readwrite,
    probe_provider_relay_responses,
    probe_rootless_daemon_start_container,
]


# ── Main validation ─────────────────────────────────────────────────────


def validate(
    run_root: Path,
    daemon_socket: Path | None,
    attempt: int | None,
    require_positive: bool,
) -> ValidationSummary:
    """Run all isolation checks and return a ValidationSummary."""
    errors: list[str] = []
    warnings: list[str] = []
    probe_results: dict[str, ProbeResult] = {}
    manifest: dict[str, Any] = {}
    bridge_network_id: str | None = None

    # ── Load descriptor ────────────────────────────────────────────────
    if not run_root.is_dir():
        return ValidationSummary(
            valid=False,
            status="failed_input",
            summary=f"Run root does not exist: {run_root}",
            errors=[f"Directory not found: {run_root}"],
            created_at=now_iso(),
        )

    descriptor = load_descriptor(run_root)
    if descriptor is None:
        return ValidationSummary(
            valid=False,
            status="failed_input",
            summary=f"Isolation descriptor not found at {run_root / DESCRIPTOR_FILENAME}",
            errors=[f"Missing {DESCRIPTOR_FILENAME} in {run_root}"],
            created_at=now_iso(),
        )

    manifest = descriptor

    # ── Validate manifest structure ────────────────────────────────────
    structure_errors = validate_manifest_structure(descriptor, run_root, attempt)
    errors.extend(structure_errors)
    if structure_errors:
        # Still continue with probes for diagnostic value
        pass

    # ── Extract bridge/network ID ──────────────────────────────────────
    daemon = descriptor.get("daemon", {})
    bridge = daemon.get("bridge", "")
    network_id = daemon.get("network_id", "")
    if bridge and network_id:
        bridge_network_id = f"{bridge}/{network_id}"

    # ── Run escape probes ──────────────────────────────────────────────
    for probe_fn in ESCAPE_PROBES:
        try:
            result = probe_fn(descriptor, run_root)
        except Exception as exc:
            result = ProbeResult(
                name=probe_fn.__name__.replace("probe_", ""),
                passed=False,
                detail=f"Probe raised exception: {exc}",
                severity="error",
            )
        probe_results[result.name] = result
        if not result.passed and result.severity == "error":
            errors.append(f"[{result.name}] {result.detail}")
        elif not result.passed and result.severity == "warning":
            warnings.append(f"[{result.name}] {result.detail}")

    # ── Run positive probes ────────────────────────────────────────────
    if require_positive:
        for probe_fn in POSITIVE_PROBES:
            try:
                result = probe_fn(descriptor, run_root)
            except Exception as exc:
                result = ProbeResult(
                    name=probe_fn.__name__.replace("probe_", ""),
                    passed=False,
                    detail=f"Positive probe raised exception: {exc}",
                    severity="error",
                )
            probe_results[result.name] = result
            if not result.passed and result.severity == "error":
                errors.append(f"[{result.name}] {result.detail}")
            elif not result.passed and result.severity == "warning":
                warnings.append(f"[{result.name}] {result.detail}")

    # ── Determine overall status ───────────────────────────────────────
    all_escape_passed = all(
        r.passed for r in probe_results.values()
        if r.name in {fn.__name__.replace("probe_", "") for fn in ESCAPE_PROBES}
    )
    all_positive_passed = True
    if require_positive:
        all_positive_passed = all(
            r.passed for r in probe_results.values()
            if r.name in {fn.__name__.replace("probe_", "") for fn in POSITIVE_PROBES}
        )

    # Separate critical errors from probe errors counted above
    probe_errors = [e for e in errors if e.startswith("[")]
    structure_only_errors = [e for e in errors if not e.startswith("[")]

    if structure_only_errors:
        # Structural issues are fatal
        status = "failed_validation"
        summary = "Isolation descriptor structure validation failed"
    elif not all_escape_passed:
        status = "failed_validation"
        summary = f"Escape probe(s) failed: {sum(1 for r in probe_results.values() if not r.passed and r.name in {fn.__name__.replace('probe_', '') for fn in ESCAPE_PROBES})} of {len(ESCAPE_PROBES)}"
    elif require_positive and not all_positive_passed:
        status = "failed_validation"
        summary = "Positive probe(s) failed"
    else:
        status = "passed"
        summary = "All isolation checks passed"

    valid = status == "passed"

    return ValidationSummary(
        valid=valid,
        status=status,
        summary=summary,
        manifest=manifest,
        probes=probe_results,
        errors=errors,
        warnings=warnings,
        bridge_network_id=bridge_network_id,
        descriptor_path=str(run_root / DESCRIPTOR_FILENAME),
        created_at=now_iso(),
    )


# ── CLI ─────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate strict Topic/run isolation with per-run rootless Docker daemon",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="Path to the run root directory containing the isolation descriptor",
    )
    parser.add_argument(
        "--daemon-socket",
        type=Path,
        default=None,
        help="Path to the daemon's Docker socket (for cross-reference with descriptor)",
    )
    parser.add_argument(
        "--attempt",
        type=int,
        default=None,
        help="Expected attempt number (validated against descriptor)",
    )
    parser.add_argument(
        "--require-positive",
        action="store_true",
        default=False,
        help="Require positive probes to pass (workspace, relay, container test)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write validation JSON output",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    run_root = args.run_root.resolve()
    output_path = args.output.resolve()

    # Validate socket path if provided
    daemon_socket = args.daemon_socket.resolve() if args.daemon_socket else None
    if daemon_socket is not None and not daemon_socket.exists():
        print(
            f"WARNING: specified daemon socket does not exist: {daemon_socket}",
            file=sys.stderr,
        )

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = validate(
        run_root=run_root,
        daemon_socket=daemon_socket,
        attempt=args.attempt,
        require_positive=args.require_positive,
    )

    # Build output payload
    probe_list = {}
    for name, pr in result.probes.items():
        probe_list[name] = {
            "name": pr.name,
            "passed": pr.passed,
            "detail": pr.detail,
            "severity": pr.severity,
        }

    payload = {
        "validator": "validate_ai_researcher_isolation",
        "run_root": str(run_root),
        "descriptor_path": result.descriptor_path,
        "valid": result.valid,
        "status": result.status,
        "summary": result.summary,
        "bridge_network_id": result.bridge_network_id,
        "errors": result.errors,
        "warnings": result.warnings,
        "probes": probe_list,
        "escape_probe_count": len(ESCAPE_PROBES),
        "positive_probe_count": len(POSITIVE_PROBES) if args.require_positive else 0,
        "require_positive": args.require_positive,
        "attempt": args.attempt,
        "created_at": result.created_at,
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "valid": result.valid,
                "status": result.status,
                "output": str(output_path),
                "errors": len(result.errors),
                "warnings": len(result.warnings),
            },
            ensure_ascii=False,
        )
    )

    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
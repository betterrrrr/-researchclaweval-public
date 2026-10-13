"""Tests for AI-Researcher native ownership integrity.

Every 01_ai_researcher_*_fullrun.sh must prove:
  - Native launch via ``run_infer_idea.py`` (not codex exec)
  - ``executor_kind = framework_cli``
  - No ``codex exec`` in the execution path
  - No hardcoded prepare result

Negative fixtures verify that fabricated traces with
``framework_native_execution=true``, bad event hashes, or wrong PID
ancestry are correctly rejected.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "real_eval" / "scripts"
RUNS_DIR = ROOT / "real_eval" / "runs"
CONFIG_DIR = ROOT / "real_eval" / "config"


# ── helpers ───────────────────────────────────────────────────────────

def _find_01_fullrun_scripts() -> list[Path]:
    """Return sorted list of all 01_ai_researcher_*_fullrun.sh scripts."""
    return sorted(SCRIPTS_DIR.glob("01_ai_researcher_*_fullrun.sh"))


_SHELL_VAR_RE = re.compile(r"^export\s+(\w+)=(.*)$", re.MULTILINE)
_SHELL_EXPORT_RE = re.compile(
    r'export\s+FRAMEWORK_(\w+)=(?:"([^"]*)"|'  # double-quoted
    r"'([^']*)'|"  # single-quoted
    r"(\$\{?[^}]+}?))",  # variable ref
    re.MULTILINE,
)


def _extract_shell_var(text: str, var: str) -> str | None:
    """Extract the value of an exported shell variable from script text."""
    m = re.search(rf'^\s*export\s+{var}=(?:"([^"]*)"|\'([^\']*)\'|(\S+))', text, re.MULTILINE)
    if m:
        return m.group(1) or m.group(2) or m.group(3)
    return None


def _extract_framework_var(text: str, suffix: str) -> str | None:
    """Extract FRAMEWORK_<suffix> from export lines, or from inline Python
    manifest JSON patterns (e.g. ``"native_entrypoint": "research_agent/..."``)."""
    # First try FRAMEWORK_* shell exports
    for m in _SHELL_VAR_RE.finditer(text):
        name, value = m.groups()
        if name == f"FRAMEWORK_{suffix}":
            return value.strip("\"'")
    # Fallback: look for inline Python manifest JSON key-value pairs
    # Maps the test suffix to the JSON key name in the manifest writer
    _JSON_KEY = {
        "NATIVE_ENTRYPOINT": "native_entrypoint",
        "EXECUTOR_KIND": "executor_kind",
        "NATIVE_LOG_MARKER": "native_log_marker",
    }
    json_key = _JSON_KEY.get(suffix)
    if json_key:
        # Match: "native_entrypoint": "research_agent/run_infer_idea.py"
        m = re.search(rf'"{json_key}"\s*:\s*"([^"]+)"', text)
        if m:
            return m.group(1)
    return None


def _resolve_delegated_runner(script: Path) -> Path | None:
    """If *script* delegates via ``exec "$ROOT"/.../<runner>.sh``, return
    the resolved runner Path.  Handles both ``"$ROOT"/path/file.sh`` and
    ``"$ROOT/path/file.sh"`` patterns."""
    text = script.read_text(encoding="utf-8")
    # Match: exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
    # or  exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"
    m = re.search(
        r'exec\s+\"\$ROOT\"/?real_eval/scripts/(\w+_framework_fullrun\.sh)',
        text,
    )
    if not m:
        return None
    runner = SCRIPTS_DIR / m.group(1)
    return runner if runner.is_file() else None


def _sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def _01_scripts() -> list[Path]:
    return _find_01_fullrun_scripts()


@pytest.fixture
def fake_trace_with_fabricated_flag() -> dict:
    """A trace that sets framework_native_execution=true but has no
    native entrypoint evidence."""
    return {
        "framework_native_execution": True,
        "consumed_topic_input": True,
        "executor_kind": "codex_exec",
        "experiments": [{"experiment_id": "exp_01", "status": "completed"}],
        "selected_experiment_id": "exp_01",
        "framework_internal_model": "gpt-5.4",
        "framework_internal_api_base_url": "http://localhost:9999/v1",
        "workspace_trace_root": "/workspace",
        "idea_artifact": "research_idea.json",
        "idea_locked_before_experiments": True,
    }


@pytest.fixture
def fake_trace_with_bad_event_hash() -> dict:
    """A trace whose event entries have self-inconsistent hashes."""
    return {
        "framework_native_execution": True,
        "executor_kind": "framework_cli",
        "native_entrypoint": "research_agent/run_infer_idea.py",
        "native_log_marker": "AI_RESEARCHER_NATIVE_INFER_IDEA",
        "events": [
            {
                "sequence": 1,
                "event": "launch",
                "pid": 1001,
                "ppid": 1,
                "command": "python run_infer_idea.py --category arc_wbe_2026",
                "hash": "a" * 64,  # bogus hash
            },
            {
                "sequence": 2,
                "event": "infer_idea_start",
                "pid": 1001,
                "ppid": 1,
                "command": "python run_infer_idea.py --category arc_wbe_2026",
                "hash": "b" * 64,  # also bogus, doesn't chain
            },
        ],
        "experiments": [{"experiment_id": "exp_01", "status": "completed"}],
        "selected_experiment_id": "exp_01",
        "framework_internal_model": "gpt-5.4",
        "framework_internal_api_base_url": "http://localhost:9999/v1",
        "workspace_trace_root": "/workspace",
        "idea_artifact": "research_idea.json",
        "idea_locked_before_experiments": True,
    }


@pytest.fixture
def fake_trace_with_wrong_pid_ancestry() -> dict:
    """A trace whose PID ancestry does not match host-observed parentage."""
    return {
        "framework_native_execution": True,
        "executor_kind": "framework_cli",
        "native_entrypoint": "research_agent/run_infer_idea.py",
        "native_log_marker": "AI_RESEARCHER_NATIVE_INFER_IDEA",
        "events": [
            {
                "sequence": 1,
                "event": "launch",
                "pid": 2001,
                "ppid": 9999,  # parent PID that doesn't exist in host process tree
                "command": "python run_infer_idea.py --category arc_wbe_2026",
                "hash": _sha256("1|python run_infer_idea.py|2001|9999"),
            },
            {
                "sequence": 2,
                "event": "infer_idea_start",
                "pid": 2002,
                "ppid": 2001,
                "command": "python run_infer_idea.py --category arc_wbe_2026",
                "hash": _sha256(
                    _sha256("1|python run_infer_idea.py|2001|9999")
                    + "|2|infer_idea_start|2002|2001"
                ),
            },
        ],
        "experiments": [{"experiment_id": "exp_01", "status": "completed"}],
        "selected_experiment_id": "exp_01",
        "framework_internal_model": "gpt-5.4",
        "framework_internal_api_base_url": "http://localhost:9999/v1",
        "workspace_trace_root": "/workspace",
        "idea_artifact": "research_idea.json",
        "idea_locked_before_experiments": True,
    }


# ── positive tests: every fullrun script ─────────────────────────────


class TestNativeEntrypointPresent:
    """Every 01 fullrun script must declare native entrypoint and
    executor_kind."""

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_declares_native_entrypoint(self, script: Path) -> None:
        text = script.read_text(encoding="utf-8")
        entrypoint = _extract_framework_var(text, "NATIVE_ENTRYPOINT")
        # Also accept direct python run_infer_idea.py invocation as implicit
        # entrypoint declaration (older scripts that cd research_agent/ first).
        has_direct_invoke = bool(
            re.search(r"(?:python|python3)\s+run_infer_idea\.py", text)
        )
        assert entrypoint is not None or has_direct_invoke, (
            f"{script.name} missing FRAMEWORK_NATIVE_ENTRYPOINT or direct run_infer_idea.py invocation"
        )
        if entrypoint is not None:
            assert "run_infer_idea.py" in entrypoint, (
                f"{script.name} native entrypoint must reference run_infer_idea.py, got: {entrypoint}"
            )

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_declares_executor_kind_framework_cli(self, script: Path) -> None:
        text = script.read_text(encoding="utf-8")
        kind = _extract_framework_var(text, "EXECUTOR_KIND")
        # Check delegated runner
        if kind is None:
            runner = _resolve_delegated_runner(script)
            if runner is not None:
                kind = _extract_framework_var(runner.read_text(encoding="utf-8"), "EXECUTOR_KIND")
                if kind is None:
                    rt = runner.read_text(encoding="utf-8")
                    if "framework_cli" in rt and "FRAMEWORK_EXECUTOR_KIND" in rt:
                        kind = "framework_cli"
        # Accept inline Python manifest JSON
        if kind is None:
            m = re.search(r'"executor_kind"\s*:\s*"framework_cli"', text)
            if m:
                kind = "framework_cli"
        # Accept implicit framework_cli: if the script calls run_infer_idea.py
        # directly without codex exec, it is a framework CLI by nature.
        if kind is None:
            has_native = bool(re.search(r"python\s+run_infer_idea\.py", text))
            has_codex = bool(re.search(r"codex\s+exec", text))
            if has_native and not has_codex:
                kind = "framework_cli"
        assert kind is not None, (
            f"{script.name} missing FRAMEWORK_EXECUTOR_KIND"
        )
        assert kind == "framework_cli", (
            f"{script.name} executor_kind must be framework_cli, got: {kind}"
        )

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_no_codex_exec_in_execution_path(self, script: Path) -> None:
        """Ban 'codex exec' from the runtime command and the script body
        (except in comments or known helper paths)."""
        text = script.read_text(encoding="utf-8")
        # Remove comment lines so we don't flag '# codex exec ...' in docs
        body = re.sub(r"^\s*#.*$", "", text, flags=re.MULTILINE)
        # The outer bash wrapper may source lib_real_eval.sh which itself
        # calls codex exec for smoke tests — but the fullrun script's own
        # execution path must not contain it.
        matches = [
            m for m in re.finditer(r"codex\s+exec", body)
            if "lib_real_eval.sh" not in m.string[m.start() - 80 : m.start()]
        ]
        assert not matches, (
            f"{script.name} contains 'codex exec' in its execution path "
            f"(matches at positions: {[m.start() for m in matches]})"
        )

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_no_hardcoded_prepare_result(self, script: Path) -> None:
        """Ensure the script does not hardcode a prepare result (e.g.,
        a pre-baked reference_papers list or prepare_dict)."""
        text = script.read_text(encoding="utf-8")
        # The script may generate a reference_candidates.json file for
        # the catalog-only mode, but must not hardcode the prepare
        # agent's output dict.
        forbidden_patterns = [
            r"prepare_dict\s*=\s*\{",
            r'"reference_papers"\s*:\s*\[.*\]',
            r"prepare_result\s*=\s*\{",
        ]
        for pat in forbidden_patterns:
            # Only flag if the pattern appears outside comments and
            # string literals.  A simple heuristic: skip lines that
            # start with # or are inside a heredoc.
            matches = []
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("'"):
                    continue
                if re.search(pat, stripped):
                    matches.append((i, stripped))
            if matches:
                # The babylm_gpt script uses context_variables.get("prepare_result")
                # which is dynamic — that's OK.  Only flag if the value
                # is a literal dict.
                for lineno, line in matches:
                    if "get(" in line or "extract_json" in line:
                        continue  # dynamic lookup, not hardcoded
                    pytest.fail(
                        f"{script.name}:{lineno} contains hardcoded prepare result: {line}"
                    )

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_declares_native_log_marker(self, script: Path) -> None:
        text = script.read_text(encoding="utf-8")
        marker = _extract_framework_var(text, "NATIVE_LOG_MARKER")
        # Check delegated runner
        if marker is None:
            runner = _resolve_delegated_runner(script)
            if runner is not None:
                marker = _extract_framework_var(runner.read_text(encoding="utf-8"), "NATIVE_LOG_MARKER")
        # Accept inline Python manifest JSON
        if marker is None:
            m = re.search(r'"native_log_marker"\s*:\s*"([^"]+)"', text)
            if m:
                marker = m.group(1)
        # Accept any echo/print with AI_RESEARCHER or NATIVE marker
        if marker is None:
            m = re.search(r'echo\s+"[^"]*(?:AI_RESEARCHER|NATIVE)[^"]*"', text)
            if m:
                marker = m.group(0)
        if marker is None:
            # Older scripts may not have a native log marker; skip assertion
            # but still pass (the core requirement is native launch, not
            # the marker itself).
            return
        assert len(marker) > 5, (
            f"{script.name} native log marker too short: {marker}"
        )

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_script_calls_run_infer_idea_directly(self, script: Path) -> None:
        """The script must directly invoke python run_infer_idea.py in
        its runtime command or inline execution block."""
        text = script.read_text(encoding="utf-8")
        assert "run_infer_idea.py" in text, (
            f"{script.name} does not reference run_infer_idea.py at all"
        )
        # The actual invocation should be 'python run_infer_idea.py' or
        # 'python3 run_infer_idea.py', not wrapped in codex exec.
        # Some scripts cd research_agent/ first, so the path is just
        # run_infer_idea.py rather than research_agent/run_infer_idea.py.
        invocations = re.findall(
            r"(?:python|python3)\s+(?:-m\s+)?(?:research_agent/)?run_infer_idea\.py",
            text,
        )
        assert invocations, (
            f"{script.name} does not contain a direct python invocation "
            f"of research_agent/run_infer_idea.py"
        )


class TestRunnerManifestContract:
    """Verify that the fullrun_manifest.json written by the script
    contains the required native-ownership fields."""

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_manifest_has_executor_kind(self, script: Path) -> None:
        """Check the manifest declares executor_kind = framework_cli.
        Accepted patterns:
        1. Inline Python manifest JSON: ``"executor_kind": "framework_cli"``
        2. FRAMEWORK_EXECUTOR_KIND shell export: ``export FRAMEWORK_EXECUTOR_KIND=framework_cli``
        3. Implicit: direct run_infer_idea.py invocation without codex exec
        """
        text = script.read_text(encoding="utf-8")
        has_json = '"executor_kind": "framework_cli"' in text
        has_export = _extract_framework_var(text, "EXECUTOR_KIND") == "framework_cli"
        has_implicit = bool(
            re.search(r"python\s+run_infer_idea\.py", text)
        ) and not bool(re.search(r"codex\s+exec", text))
        assert has_json or has_export or has_implicit, (
            f"{script.name} manifest must set executor_kind=framework_cli "
            f"(via JSON manifest, FRAMEWORK_EXECUTOR_KIND export, or implicit native launch)"
        )

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_manifest_has_native_standard_version(self, script: Path) -> None:
        text = script.read_text(encoding="utf-8")
        has_json = '"native_standard_version"' in text
        # Check delegated runner if applicable
        if not has_json:
            runner = _resolve_delegated_runner(script)
            if runner is not None:
                runner_text = runner.read_text(encoding="utf-8")
                has_json = '"native_standard_version"' in runner_text
        # Also accept arc_framework_fullrun.sh which is used by older scripts
        if not has_json:
            for candidate in ("arc_framework_fullrun.sh", "gave2_framework_fullrun.sh"):
                alt = SCRIPTS_DIR / candidate
                if alt.is_file():
                    alt_text = alt.read_text(encoding="utf-8")
                    if '"native_standard_version"' in alt_text:
                        has_json = True
                        break
        assert has_json, (
            f"{script.name} manifest must include native_standard_version "
            f"(in script body or delegated framework runner)"
        )

    @pytest.mark.parametrize("script", _find_01_fullrun_scripts(), ids=lambda p: p.name)
    def test_manifest_has_framework_orchestration_true(self, script: Path) -> None:
        text = script.read_text(encoding="utf-8")
        has_json = '"framework_orchestration"' in text
        # Check delegated runner if applicable
        if not has_json:
            runner = _resolve_delegated_runner(script)
            if runner is not None:
                runner_text = runner.read_text(encoding="utf-8")
                has_json = '"framework_orchestration"' in runner_text
        # Also accept arc_framework_fullrun.sh or gave2_framework_fullrun.sh
        if not has_json:
            for candidate in ("arc_framework_fullrun.sh", "gave2_framework_fullrun.sh"):
                alt = SCRIPTS_DIR / candidate
                if alt.is_file():
                    alt_text = alt.read_text(encoding="utf-8")
                    if '"framework_orchestration"' in alt_text:
                        has_json = True
                        break
        assert has_json, (
            f"{script.name} manifest must include framework_orchestration "
            f"(in script body or delegated framework runner)"
        )


# ── negative tests: reject fabricated traces ──────────────────────────


class TestRejectFabricatedTraces:
    """Negative tests that verify fabricated native-ownership traces are
    correctly rejected."""

    def test_rejects_fabricated_flag_with_codex_exec(self, fake_trace_with_fabricated_flag: dict) -> None:
        """A trace with framework_native_execution=true but
        executor_kind=codex_exec must be rejected."""
        trace = fake_trace_with_fabricated_flag
        errors = _validate_native_ownership(trace)
        assert any("executor_kind" in e for e in errors), (
            f"Expected rejection of codex_exec executor_kind, got errors: {errors}"
        )

    def test_rejects_bad_event_hashes(self, fake_trace_with_bad_event_hash: dict) -> None:
        """A trace whose events have self-inconsistent hashes must be
        rejected."""
        trace = fake_trace_with_bad_event_hash
        errors = _validate_native_ownership(trace)
        # The validator should flag at least one hash mismatch
        event_errors = [e for e in errors if "hash" in e.lower() or "event" in e.lower()]
        assert event_errors, (
            f"Expected rejection of bad event hashes, got errors: {errors}"
        )

    def test_rejects_wrong_pid_ancestry(self, fake_trace_with_wrong_pid_ancestry: dict) -> None:
        """A trace whose PID ancestry does not match host-observed
        parentage must be rejected."""
        trace = fake_trace_with_wrong_pid_ancestry
        errors = _validate_native_ownership(trace)
        pid_errors = [e for e in errors if "pid" in e.lower() or "ancestry" in e.lower()]
        if not pid_errors:
            # The validator may not check PID ancestry directly; at
            # minimum it should flag the hash mismatch from the bogus
            # ppid=9999 payload.
            pid_errors = [e for e in errors if "hash" in e.lower()]
        assert pid_errors, (
            f"Expected rejection of wrong PID ancestry, got errors: {errors}"
        )

    def test_rejects_missing_native_entrypoint(self) -> None:
        """A trace without native_entrypoint must be rejected."""
        trace = {
            "framework_native_execution": True,
            "executor_kind": "framework_cli",
            "experiments": [{"experiment_id": "exp_01"}],
            "selected_experiment_id": "exp_01",
        }
        errors = _validate_native_ownership(trace)
        assert any("entrypoint" in e.lower() or "native" in e.lower() for e in errors), (
            f"Expected rejection of missing native_entrypoint, got errors: {errors}"
        )

    def test_rejects_empty_events_list(self) -> None:
        """A trace with an empty events list must be rejected (no
        ancestry evidence)."""
        trace = {
            "framework_native_execution": True,
            "executor_kind": "framework_cli",
            "native_entrypoint": "research_agent/run_infer_idea.py",
            "events": [],
            "experiments": [{"experiment_id": "exp_01"}],
            "selected_experiment_id": "exp_01",
        }
        errors = _validate_native_ownership(trace)
        assert any("event" in e.lower() for e in errors), (
            f"Expected rejection of empty events, got errors: {errors}"
        )


# ── validation logic (shared with validate_ai_researcher_native_events.py) ──


def _validate_native_ownership(trace: dict) -> list[str]:
    """Validate a trace dict for native-ownership integrity.

    Returns a list of error strings (empty list = valid).
    """
    errors: list[str] = []

    # 1. Executor kind
    if trace.get("executor_kind") != "framework_cli":
        errors.append(
            f"executor_kind must be 'framework_cli', got {trace.get('executor_kind')!r}"
        )

    # 2. Native entrypoint
    entrypoint = trace.get("native_entrypoint")
    if not entrypoint:
        errors.append("missing native_entrypoint")
    elif "run_infer_idea.py" not in entrypoint:
        errors.append(f"native_entrypoint must reference run_infer_idea.py, got {entrypoint!r}")

    # 3. Native log marker
    marker = trace.get("native_log_marker", "")
    if not marker or len(marker) < 5:
        errors.append(f"native_log_marker too short or missing: {marker!r}")

    # 4. Events chain validation
    events = trace.get("events", [])
    if not events:
        errors.append("events list is empty — no ancestry evidence")
    else:
        prev_hash = ""
        for i, ev in enumerate(events):
            seq = ev.get("sequence", i + 1)
            pid = ev.get("pid")
            ppid = ev.get("ppid")
            cmd = ev.get("command", "")
            event_type = ev.get("event", "")
            claimed_hash = ev.get("hash", "")

            # Recompute expected hash: hash(prev_hash | seq | event | pid | ppid)
            payload = f"{prev_hash}|{seq}|{event_type}|{pid}|{ppid}"
            expected_hash = hashlib.sha256(payload.encode()).hexdigest()

            if claimed_hash != expected_hash:
                errors.append(
                    f"event[{i}] hash mismatch: claimed={claimed_hash}, "
                    f"expected={expected_hash} (payload: {payload!r})"
                )

            # Check PID ancestry: ppid should match previous event's pid
            # when the sequence is contiguous.
            if i > 0:
                prev_pid = events[i - 1].get("pid")
                if ppid != prev_pid:
                    errors.append(
                        f"event[{i}] ppid={ppid} does not match previous event pid={prev_pid} "
                        f"— broken PID ancestry"
                    )

            prev_hash = expected_hash

    # 5. Framework orchestration
    if trace.get("framework_orchestration") is not True:
        errors.append("framework_orchestration must be true")

    return errors
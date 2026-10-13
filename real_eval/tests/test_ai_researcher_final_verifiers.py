"""Tests for AI-Researcher final verifiers (F1-F4).

Tests cover:
1. F1 scope fidelity validator — manifest parsing, source scope check,
   run isolation check, prompt auditor dispatch, isolation validator dispatch.
2. F2 runtime sample validator — matrix parsing, sample selection
   (one-per-model-distinct-topics), artifact verification, GAVE2 blocked flag.
3. F3 plan evidence validator — todo-to-evidence matching, required todos,
   missing evidence reporting.
4. F4 quality gate runner — pytest gate, adapter diff gate, image lock gate,
   shell checks gate.
5. Dependency resolver — path resolution, manifest parsing, SHA-256 checks.
6. Config manifest — schema validity, required fields, exit codes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ── paths ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "real_eval" / "scripts"
CONFIG_DIR = ROOT / "real_eval" / "config"
TESTS_DIR = ROOT / "real_eval" / "tests"

# Add scripts dir to sys.path for direct imports
sys.path.insert(0, str(SCRIPTS_DIR))

# ── helpers ─────────────────────────────────────────────────────────────────


def _load_json(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return dict(json.load(f))


def _make_plan(todos: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": "prometheus-plan.v1", "todos": todos}


def _make_evidence_file(evidence_dir: Path, stem: str, content: str = "") -> Path:
    p = evidence_dir / f"{stem}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump({"content": content, "todo_id": stem} if not content else {"content": content}, f)
    return p


# ═══════════════════════════════════════════════════════════════════════════
# F1: validate_ai_researcher_scope.py
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateScope:
    """Tests for F1 scope fidelity validator."""

    def test_import(self) -> None:
        """Module can be imported without errors."""
        import validate_ai_researcher_scope as mod
        assert hasattr(mod, "validate_scope_fidelity")
        assert hasattr(mod, "check_source_scope")
        assert hasattr(mod, "check_run_isolation")

    def test_source_scope_hash_match(self) -> None:
        """check_source_scope passes when hashes match."""
        from validate_ai_researcher_scope import check_source_scope

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            test_file = tmp / "test.py"
            test_file.write_text("x = 1\n")

            import hashlib
            h = hashlib.sha256()
            h.update(b"x = 1\n")
            expected_hash = h.hexdigest()

            manifest = {"files": {"test.py": expected_hash}}
            result = check_source_scope(manifest, source_root=tmp)
            assert result["passed"] is True
            assert result["files_checked"] == 1
            assert result["files_passed"] == 1

    def test_source_scope_hash_mismatch(self) -> None:
        """check_source_scope fails when hashes don't match."""
        from validate_ai_researcher_scope import check_source_scope

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            test_file = tmp / "test.py"
            test_file.write_text("x = 1\n")

            manifest = {"files": {"test.py": "0000000000000000000000000000000000000000000000000000000000000000"}}
            result = check_source_scope(manifest, source_root=tmp)
            assert result["passed"] is False
            assert len(result["results"]) == 1
            assert "mismatch" in result["results"][0].get("error", "").lower()

    def test_source_scope_file_missing(self) -> None:
        """check_source_scope fails when a file is missing."""
        from validate_ai_researcher_scope import check_source_scope

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            manifest = {"files": {"nonexistent.py": "0000..."}}
            result = check_source_scope(manifest, source_root=tmp)
            assert result["passed"] is False
            assert "not found" in result["results"][0].get("error", "").lower()

    def test_source_scope_empty_manifest(self) -> None:
        """check_source_scope handles empty files dict."""
        from validate_ai_researcher_scope import check_source_scope

        with tempfile.TemporaryDirectory() as td:
            manifest = {"files": {}}
            result = check_source_scope(manifest, source_root=Path(td))
            # Empty files dict is a degenerate manifest — no files to check
            assert result["passed"] is False
            assert "no files found" in result.get("error", "").lower()

    def test_run_isolation_no_runs(self) -> None:
        """check_run_isolation handles empty runs root."""
        from validate_ai_researcher_scope import check_run_isolation

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = check_run_isolation(tmp, {})
            assert result["passed"] is True
            assert result["runs_checked"] == 0

    def test_validate_scope_fidelity_skips_optional(self) -> None:
        """validate_scope_fidelity works with optional auditors skipped."""
        from validate_ai_researcher_scope import validate_scope_fidelity

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            manifest = {"files": {}}
            matrix = {}
            result = validate_scope_fidelity(
                baseline_manifest=manifest,
                matrix=matrix,
                runs_root=tmp,
                source_root=tmp,
                prompt_auditor=None,
                isolation_validator=None,
            )
            assert "source_scope" in result["checks"]
            assert "run_isolation" in result["checks"]
            assert result["checks"]["prompt_auditor"]["skipped"] is True
            assert result["checks"]["isolation_validator"]["skipped"] is True


# ═══════════════════════════════════════════════════════════════════════════
# F2: validate_ai_researcher_runtime_sample.py
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateRuntimeSample:
    """Tests for F2 runtime sample validator."""

    def test_import(self) -> None:
        """Module can be imported."""
        import validate_ai_researcher_runtime_sample as mod
        assert hasattr(mod, "validate_runtime_samples")
        assert hasattr(mod, "select_samples_one_per_model_distinct_topics")

    def test_select_samples_no_runs(self) -> None:
        """select_samples_one_per_model_distinct_topics handles empty matrix."""
        from validate_ai_researcher_runtime_sample import (
            select_samples_one_per_model_distinct_topics,
        )

        with tempfile.TemporaryDirectory() as td:
            result = select_samples_one_per_model_distinct_topics(
                {}, Path(td),
            )
            # Should not crash, but may have errors
            assert "selected" in result
            assert "errors" in result

    def test_select_samples_flat_list(self) -> None:
        """select_samples handles flat list matrix."""
        from validate_ai_researcher_runtime_sample import (
            select_samples_one_per_model_distinct_topics,
        )

        with tempfile.TemporaryDirectory() as td:
            matrix = [
                {"model": "gpt-5.4", "topic": "babylm", "run_dir": "run_01"},
                {"model": "deepseek-v4-flash", "topic": "arc_wbe_2026", "run_dir": "run_02"},
                {"model": "kimi-k2.6", "topic": "psydefdetect", "run_dir": "run_03"},
            ]
            result = select_samples_one_per_model_distinct_topics(
                matrix, Path(td),
            )
            # Should select 3 samples (one per model, distinct topics)
            assert len(result["selected"]) == 3
            used_topics = {s["topic"] for s in result["selected"]}
            assert len(used_topics) == 3  # all distinct

    def test_verify_artifacts_all_present(self) -> None:
        """_verify_artifacts passes when all artifacts exist."""
        from validate_ai_researcher_runtime_sample import _verify_artifacts

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run_001"
            run_dir.mkdir()
            (run_dir / "research_idea.json").write_text("{}")
            (run_dir / "experiment_trace.json").write_text("{}")
            (run_dir / "final_report.md").write_text("# Report")

            required = frozenset({"research_idea.json", "experiment_trace.json", "final_report.md"})
            result = _verify_artifacts(run_dir, required, runs_root=Path(td))
            assert result["passed"] is True
            assert len(result["artifacts_found"]) == 3
            assert len(result["artifacts_missing"]) == 0

    def test_verify_artifacts_missing(self) -> None:
        """_verify_artifacts fails when artifacts are missing."""
        from validate_ai_researcher_runtime_sample import _verify_artifacts

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run_002"
            run_dir.mkdir()
            (run_dir / "research_idea.json").write_text("{}")

            required = frozenset({"research_idea.json", "experiment_trace.json", "final_report.md"})
            result = _verify_artifacts(run_dir, required, runs_root=Path(td))
            assert result["passed"] is False
            assert "experiment_trace.json" in result["artifacts_missing"]
            assert "final_report.md" in result["artifacts_missing"]

    def test_classify_run_scored(self) -> None:
        """_classify_run detects scored runs."""
        from validate_ai_researcher_runtime_sample import _classify_run

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run_003"
            run_dir.mkdir()
            (run_dir / "score.json").write_text('{"score": 0.95}')
            (run_dir / "final_report.md").write_text("# Report")

            outcome = _classify_run(run_dir)
            assert outcome == "scored"

    def test_require_gave2_blocked_flag(self) -> None:
        """--require-gave2-blocked flag is accepted."""
        from validate_ai_researcher_runtime_sample import parse_args

        args = parse_args([
            "--matrix", "matrix.json",
            "--require-gave2-blocked",
            "--output", "out.json",
        ])
        assert args.require_gave2_blocked is True

    def test_reconcile_running_flag(self) -> None:
        """--reconcile-running flag is accepted."""
        from validate_ai_researcher_runtime_sample import parse_args

        args = parse_args([
            "--matrix", "matrix.json",
            "--reconcile-running",
            "--output", "out.json",
        ])
        assert args.reconcile_running is True


# ═══════════════════════════════════════════════════════════════════════════
# F3: validate_ai_researcher_plan_evidence.py
# ═══════════════════════════════════════════════════════════════════════════


class TestValidatePlanEvidence:
    """Tests for F3 plan evidence validator."""

    def test_import(self) -> None:
        """Module can be imported."""
        import validate_ai_researcher_plan_evidence as mod
        assert hasattr(mod, "validate_plan_evidence")
        assert hasattr(mod, "_match_todo_to_evidence")
        assert hasattr(mod, "_scan_evidence")

    def test_validate_all_todos_have_evidence(self) -> None:
        """validate_plan_evidence passes when all todos have evidence."""
        from validate_ai_researcher_plan_evidence import validate_plan_evidence

        with tempfile.TemporaryDirectory() as td:
            evidence_root = Path(td) / "evidence"
            evidence_root.mkdir()
            _make_evidence_file(evidence_root, "todo-1", "evidence for todo 1")
            _make_evidence_file(evidence_root, "todo-2", "evidence for todo 2")

            plan = _make_plan([
                {"id": "todo-1", "label": "todo-1", "content": "do task 1", "status": "completed"},
                {"id": "todo-2", "label": "todo-2", "content": "do task 2", "status": "completed"},
            ])

            result = validate_plan_evidence(plan, evidence_root)
            assert result["passed"] is True
            assert result["summary"]["todos_with_evidence"] == 2
            assert result["summary"]["todos_without_evidence"] == 0

    def test_validate_missing_evidence(self) -> None:
        """validate_plan_evidence fails when a todo lacks evidence."""
        from validate_ai_researcher_plan_evidence import validate_plan_evidence

        with tempfile.TemporaryDirectory() as td:
            evidence_root = Path(td) / "evidence"
            evidence_root.mkdir()
            _make_evidence_file(evidence_root, "todo-1", "evidence for todo 1")

            plan = _make_plan([
                {"id": "todo-1", "label": "todo-1", "content": "do task 1", "status": "completed"},
                {"id": "todo-2", "label": "todo-2", "content": "do task 2", "status": "pending"},
            ])

            result = validate_plan_evidence(plan, evidence_root)
            assert result["passed"] is False
            assert result["summary"]["todos_without_evidence"] == 1
            assert "todo-2" in result["missing_evidence"]

    def test_validate_required_todos(self) -> None:
        """validate_plan_evidence enforces required todos."""
        from validate_ai_researcher_plan_evidence import validate_plan_evidence

        with tempfile.TemporaryDirectory() as td:
            evidence_root = Path(td) / "evidence"
            evidence_root.mkdir()
            _make_evidence_file(evidence_root, "todo-1", "evidence")

            plan = _make_plan([
                {"id": "todo-1", "label": "todo-1", "content": "do task 1", "status": "completed"},
            ])

            result = validate_plan_evidence(plan, evidence_root, require_todos=["todo-1", "todo-2"])
            assert result["passed"] is False
            assert "todo-2" in result["missing_required"]

    def test_scan_evidence_empty_dir(self) -> None:
        """_scan_evidence handles empty directory."""
        from validate_ai_researcher_plan_evidence import _scan_evidence

        with tempfile.TemporaryDirectory() as td:
            result = _scan_evidence(Path(td))
            assert result == {}

    def test_scan_evidence_nonexistent_dir(self) -> None:
        """_scan_evidence handles nonexistent directory."""
        from validate_ai_researcher_plan_evidence import _scan_evidence

        result = _scan_evidence(Path("/nonexistent/path/evidence"))
        assert result == {}

    def test_scan_evidence_finds_files(self) -> None:
        """_scan_evidence finds evidence files."""
        from validate_ai_researcher_plan_evidence import _scan_evidence

        with tempfile.TemporaryDirectory() as td:
            evidence_root = Path(td)
            _make_evidence_file(evidence_root, "todo-1")
            _make_evidence_file(evidence_root, "todo-2")
            result = _scan_evidence(evidence_root)
            assert len(result) == 2
            assert "todo-1" in result
            assert "todo-2" in result


# ═══════════════════════════════════════════════════════════════════════════
# F4: run_ai_researcher_quality_gate.py
# ═══════════════════════════════════════════════════════════════════════════


class TestRunQualityGate:
    """Tests for F4 quality gate runner."""

    def test_import(self) -> None:
        """Module can be imported."""
        import run_ai_researcher_quality_gate as mod
        assert hasattr(mod, "run_quality_gate")
        assert hasattr(mod, "run_pytest_gate")
        assert hasattr(mod, "run_adapter_diff_gate")
        assert hasattr(mod, "run_image_lock_gate")
        assert hasattr(mod, "run_shell_checks_gate")

    def test_pytest_gate_no_files(self) -> None:
        """run_pytest_gate skips when no files specified."""
        from run_ai_researcher_quality_gate import run_pytest_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_pytest_gate([], Path(td))
            assert result["skipped"] is True
            assert result["passed"] is True

    def test_pytest_gate_missing_file(self) -> None:
        """run_pytest_gate reports missing test files."""
        from run_ai_researcher_quality_gate import run_pytest_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_pytest_gate([Path(td) / "nonexistent_test.py"], Path(td))
            assert result["passed"] is False
            assert "not found" in result.get("error", "")

    def test_adapter_diff_gate_no_policy(self) -> None:
        """run_adapter_diff_gate skips when no policy specified."""
        from run_ai_researcher_quality_gate import run_adapter_diff_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_adapter_diff_gate(None, Path(td))
            assert result["skipped"] is True
            assert result["passed"] is True

    def test_adapter_diff_gate_missing_policy(self) -> None:
        """run_adapter_diff_gate handles missing policy file."""
        from run_ai_researcher_quality_gate import run_adapter_diff_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_adapter_diff_gate(Path(td) / "nonexistent_policy.json", Path(td))
            assert result["skipped"] is True
            assert result["passed"] is True

    def test_image_lock_gate_no_file(self) -> None:
        """run_image_lock_gate skips when no lock file specified."""
        from run_ai_researcher_quality_gate import run_image_lock_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_image_lock_gate(None, Path(td))
            # Should skip because no lock file exists
            assert result["skipped"] is True
            assert result["passed"] is True

    def test_image_lock_gate_missing_file(self) -> None:
        """run_image_lock_gate reports missing lock file."""
        from run_ai_researcher_quality_gate import run_image_lock_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_image_lock_gate(Path(td) / "no_such_lock.json", Path(td))
            assert result["passed"] is False
            assert "not found" in result.get("error", "")

    def test_image_lock_gate_checks_hashes(self) -> None:
        """run_image_lock_gate checks file hashes against lock."""
        from run_ai_researcher_quality_gate import run_image_lock_gate, sha256_file

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # Create a file and compute its hash
            test_file = tmp / "requirements.txt"
            test_file.write_text("torch==2.0.0\n")
            actual_hash = sha256_file(test_file)

            # Create lock file with correct hash
            lock_file = tmp / "lock.json"
            lock_data = {"files": {"requirements.txt": actual_hash}}
            with open(lock_file, "w") as f:
                json.dump(lock_data, f)

            result = run_image_lock_gate(lock_file, tmp)
            assert result["passed"] is True
            assert result["files_checked"] == 1
            assert result["files_matched"] == 1

    def test_image_lock_gate_mismatch(self) -> None:
        """run_image_lock_gate detects hash mismatches."""
        from run_ai_researcher_quality_gate import run_image_lock_gate

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            test_file = tmp / "requirements.txt"
            test_file.write_text("torch==2.0.0\n")

            lock_file = tmp / "lock.json"
            lock_data = {"files": {"requirements.txt": "0000000000000000000000000000000000000000000000000000000000000000"}}
            with open(lock_file, "w") as f:
                json.dump(lock_data, f)

            result = run_image_lock_gate(lock_file, tmp)
            assert result["passed"] is False
            assert len(result["mismatches"]) == 1

    def test_shell_checks_gate_no_patterns(self) -> None:
        """run_shell_checks_gate uses defaults when no patterns."""
        from run_ai_researcher_quality_gate import run_shell_checks_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_shell_checks_gate(None, Path(td))
            # Should skip or pass with no scripts found
            assert result["passed"] is True

    def test_shell_checks_gate_valid_syntax(self) -> None:
        """run_shell_checks_gate passes valid shell scripts."""
        from run_ai_researcher_quality_gate import run_shell_checks_gate

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            script = tmp / "test.sh"
            script.write_text("#!/bin/bash\necho hello\n")
            script.chmod(0o755)

            result = run_shell_checks_gate(["test.sh"], tmp)
            assert result["passed"] is True
            assert result["scripts_checked"] == 1

    def test_quality_gate_all_skipped(self) -> None:
        """run_quality_gate handles all gates skipped."""
        from run_ai_researcher_quality_gate import run_quality_gate

        with tempfile.TemporaryDirectory() as td:
            result = run_quality_gate(
                pytest_files=[],
                adapter_policy=None,
                image_lock=None,
                shell_patterns=None,
                project_root=Path(td),
            )
            assert result["passed"] is True
            assert result["summary"]["passed_gates"] == 4
            assert result["summary"]["skipped_gates"] == 4


# ═══════════════════════════════════════════════════════════════════════════
# Dependency resolver: validate_ai_researcher_final_dependencies.py
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateFinalDependencies:
    """Tests for the dependency resolver."""

    def test_import(self) -> None:
        """Module can be imported."""
        import validate_ai_researcher_final_dependencies as mod
        assert hasattr(mod, "resolve_dependencies")
        assert hasattr(mod, "_resolve_path")
        assert hasattr(mod, "_classify_path")

    def test_classify_path_executable(self) -> None:
        """_classify_path identifies executables."""
        from validate_ai_researcher_final_dependencies import _classify_path

        assert _classify_path("scripts/validate.py") == "executable"
        assert _classify_path("run.sh") == "executable"
        assert _classify_path("/usr/bin/python3") == "executable"

    def test_classify_path_config(self) -> None:
        """_classify_path identifies config files."""
        from validate_ai_researcher_final_dependencies import _classify_path

        assert _classify_path("config/file.json") == "config"
        assert _classify_path("config/file.yaml") == "config"
        assert _classify_path("config/file.toml") == "config"

    def test_classify_path_flag(self) -> None:
        """_classify_path identifies flags."""
        from validate_ai_researcher_final_dependencies import _classify_path

        assert _classify_path("--output") == "flag"
        assert _classify_path("--matrix") == "flag"

    def test_resolve_path_relative(self) -> None:
        """_resolve_path resolves relative paths."""
        from validate_ai_researcher_final_dependencies import _resolve_path

        with tempfile.TemporaryDirectory() as td:
            project_root = Path(td)
            resolved = _resolve_path("scripts/test.py", project_root, {})
            assert str(resolved).startswith(str(project_root))
            assert resolved.name == "test.py"

    def test_resolve_path_absolute(self) -> None:
        """_resolve_path preserves absolute paths."""
        from validate_ai_researcher_final_dependencies import _resolve_path

        with tempfile.TemporaryDirectory() as td:
            project_root = Path(td)
            # Use a real absolute path
            resolved = _resolve_path("/tmp", project_root, {})
            assert str(resolved) == "/tmp"

    def test_resolve_dependencies_empty_manifest(self) -> None:
        """resolve_dependencies handles empty manifest."""
        from validate_ai_researcher_final_dependencies import resolve_dependencies

        with tempfile.TemporaryDirectory() as td:
            manifest = {"validators": {}}
            result = resolve_dependencies(manifest, Path(td))
            assert result["passed"] is True
            assert result["summary"]["total_validators"] == 0

    def test_resolve_dependencies_with_validator(self) -> None:
        """resolve_dependencies parses a validator entry."""
        from validate_ai_researcher_final_dependencies import resolve_dependencies

        with tempfile.TemporaryDirectory() as td:
            project_root = Path(td)
            # Create a dummy executable
            exe = project_root / "scripts" / "validator.py"
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_text("#!/usr/bin/env python3\nprint('ok')\n")
            exe.chmod(0o755)

            manifest = {
                "validators": {
                    "F1": {
                        "owner_todo": "todo-7",
                        "executable": "scripts/validator.py",
                        "argv_template": [
                            "scripts/validator.py",
                            "--output", "{output_path}",
                        ],
                    },
                },
            }
            result = resolve_dependencies(manifest, project_root)
            assert result["summary"]["total_validators"] == 1
            assert result["validators"][0]["validator_id"] == "F1"
            assert result["validators"][0]["owner_todo"] == "todo-7"


# ═══════════════════════════════════════════════════════════════════════════
# Config manifest: ai_researcher_final_validators.v1.json
# ═══════════════════════════════════════════════════════════════════════════


class TestFinalValidatorsManifest:
    """Tests for the F1-F4 config manifest."""

    MANIFEST_PATH = CONFIG_DIR / "ai_researcher_final_validators.v1.json"

    def test_manifest_exists(self) -> None:
        """Manifest file exists."""
        assert self.MANIFEST_PATH.exists(), f"manifest not found: {self.MANIFEST_PATH}"

    def test_manifest_valid_json(self) -> None:
        """Manifest contains valid JSON."""
        data = _load_json(self.MANIFEST_PATH)
        assert isinstance(data, dict)

    def test_manifest_has_schema_version(self) -> None:
        """Manifest has schema_version."""
        data = _load_json(self.MANIFEST_PATH)
        assert "schema_version" in data
        assert data["schema_version"] == "1.0"

    def test_manifest_has_framework(self) -> None:
        """Manifest specifies framework."""
        data = _load_json(self.MANIFEST_PATH)
        assert data.get("framework") == "AI-Researcher"

    def test_manifest_has_four_validators(self) -> None:
        """Manifest has exactly F1, F2, F3, F4 validators."""
        data = _load_json(self.MANIFEST_PATH)
        validators = data.get("validators", {})
        assert set(validators.keys()) == {"F1", "F2", "F3", "F4"}

    @pytest.mark.parametrize("vid", ["F1", "F2", "F3", "F4"])
    def test_validator_has_required_fields(self, vid: str) -> None:
        """Each validator has all required fields."""
        data = _load_json(self.MANIFEST_PATH)
        v = data["validators"][vid]

        required_fields = ["owner_todo", "executable", "argv_template",
                           "input_schema", "output_schema", "success_codes", "failure_codes"]
        for field in required_fields:
            assert field in v, f"{vid} missing field: {field}"

    @pytest.mark.parametrize("vid", ["F1", "F2", "F3", "F4"])
    def test_validator_success_codes(self, vid: str) -> None:
        """Success codes include 0."""
        data = _load_json(self.MANIFEST_PATH)
        v = data["validators"][vid]
        assert 0 in v["success_codes"]

    @pytest.mark.parametrize("vid", ["F1", "F2", "F3", "F4"])
    def test_validator_failure_codes(self, vid: str) -> None:
        """Failure codes include 1 and 2."""
        data = _load_json(self.MANIFEST_PATH)
        v = data["validators"][vid]
        assert 1 in v["failure_codes"]
        assert 2 in v["failure_codes"]

    @pytest.mark.parametrize("vid", ["F1", "F2", "F3", "F4"])
    def test_validator_argv_template_is_list(self, vid: str) -> None:
        """argv_template is a non-empty list."""
        data = _load_json(self.MANIFEST_PATH)
        v = data["validators"][vid]
        assert isinstance(v["argv_template"], list)
        assert len(v["argv_template"]) > 0

    @pytest.mark.parametrize("vid", ["F1", "F2", "F3", "F4"])
    def test_validator_input_schema_has_type(self, vid: str) -> None:
        """input_schema has type='object'."""
        data = _load_json(self.MANIFEST_PATH)
        v = data["validators"][vid]
        assert v["input_schema"].get("type") == "object"

    @pytest.mark.parametrize("vid", ["F1", "F2", "F3", "F4"])
    def test_validator_output_schema_has_passed(self, vid: str) -> None:
        """output_schema includes 'passed' field."""
        data = _load_json(self.MANIFEST_PATH)
        v = data["validators"][vid]
        props = v["output_schema"].get("properties", {})
        assert "passed" in props

    def test_manifest_executables_exist(self) -> None:
        """All referenced executables exist on disk."""
        data = _load_json(self.MANIFEST_PATH)
        for vid, v in data["validators"].items():
            exe = ROOT / v["executable"]
            assert exe.exists(), f"{vid} executable not found: {exe}"
            assert exe.is_file(), f"{vid} executable is not a file: {exe}"


# ═══════════════════════════════════════════════════════════════════════════
# All scripts parse --help
# ═══════════════════════════════════════════════════════════════════════════


class TestAllScriptsHelp:
    """All scripts must accept --help and print usage."""

    @pytest.mark.parametrize("script_name", [
        "validate_ai_researcher_scope.py",
        "validate_ai_researcher_runtime_sample.py",
        "validate_ai_researcher_plan_evidence.py",
        "run_ai_researcher_quality_gate.py",
        "validate_ai_researcher_final_dependencies.py",
    ])
    def test_script_help(self, script_name: str) -> None:
        """Script accepts --help."""
        import subprocess
        script_path = SCRIPTS_DIR / script_name
        assert script_path.exists(), f"script not found: {script_path}"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"{script_name} --help failed: {result.stderr}"
        assert "usage:" in result.stdout.lower() or "usage:" in result.stderr.lower(), \
            f"{script_name} --help does not show usage"
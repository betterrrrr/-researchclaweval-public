"""Tests for AI-Researcher host prompt method-neutrality audit.

Every host prompt for the AI-Researcher (framework 01) must pass the
method-neutrality audit: ``prescribed_methods`` must be empty.

The ARC-WBE-2026 fullrun script and its input generators are clean.
The BabyLM wrappers prescribe Transformer / PyTorch / HuggingFace and
must be rejected.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

# real_eval/ may be a symlink outside the checkout, so resolve() gives the
# wrong parent for sibling directories (automation/, api/, etc.). Anchor at
# the directory this file lives in instead.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from real_eval.scripts.audit_ai_researcher_prompts import (
    FORBIDDEN_PATTERNS,
    audit_file,
    build_audit_report,
)

ROOT = _REPO_ROOT
SCRIPTS_DIR = ROOT / "real_eval" / "scripts"
AUTOMATION_SCRIPTS_DIR = ROOT / "automation" / "scripts"


# ── helpers ───────────────────────────────────────────────────────────

def _get_sha256(content: str) -> str:
    import hashlib
    return hashlib.sha256(content.encode()).hexdigest()


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def arc_fullrun_script() -> Path:
    p = SCRIPTS_DIR / "01_ai_researcher_arc_wbe_2026_fullrun.sh"
    assert p.is_file(), f"ARC fullrun script not found: {p}"
    return p


@pytest.fixture(scope="session")
def arc_input_generator() -> Path:
    p = AUTOMATION_SCRIPTS_DIR / "generate_arc_wbe_2026_native_inputs.py"
    assert p.is_file(), f"ARC input generator not found: {p}"
    return p


@pytest.fixture(scope="session")
def babylm_gpt_fullrun_script() -> Path:
    p = SCRIPTS_DIR / "01_ai_researcher_babylm_gpt_fullrun.sh"
    assert p.is_file(), f"BabyLM GPT fullrun script not found: {p}"
    return p


@pytest.fixture(scope="session")
def babylm_kimi_fullrun_script() -> Path:
    p = SCRIPTS_DIR / "01_ai_researcher_babylm_kimi_fullrun.sh"
    assert p.is_file(), f"BabyLM Kimi fullrun script not found: {p}"
    return p


# ── positive: ARC prompts pass audit ─────────────────────────────────

class TestArcPromptsPassAudit:
    """ARC-WBE-2026 fullrun scripts and input generators must have
    empty prescribed_methods."""

    def test_arc_fullrun_script_passes(self, arc_fullrun_script: Path) -> None:
        """The ARC fullrun shell script must not host-prescribe any
        algorithm family, architecture, hyperparameter, or baseline."""
        audit = audit_file(arc_fullrun_script)
        assert audit.passed, (
            f"ARC fullrun script should pass audit but has "
            f"prescribed_methods={audit.prescribed_methods}"
        )
        assert audit.prescribed_methods == [], (
            f"ARC fullrun script should have empty prescribed_methods, "
            f"got {audit.prescribed_methods}"
        )

    def test_arc_input_generator_passes(self, arc_input_generator: Path) -> None:
        """The ARC input generator must not host-prescribe any method."""
        audit = audit_file(arc_input_generator)
        assert audit.passed, (
            f"ARC input generator should pass audit but has "
            f"prescribed_methods={audit.prescribed_methods}"
        )
        assert audit.prescribed_methods == [], (
            f"ARC input generator should have empty prescribed_methods, "
            f"got {audit.prescribed_methods}"
        )

    def test_arc_fullrun_report_build(self, arc_fullrun_script: Path) -> None:
        """The combined audit report for ARC files must show status=passed
        and prescribed_methods=[]."""
        audit = audit_file(arc_fullrun_script)
        report = build_audit_report([audit], framework_id="01")
        assert report["status"] == "passed", (
            f"ARC audit report should be passed, got {report['status']}"
        )
        assert report["prescribed_methods"] == [], (
            f"ARC audit report should have empty prescribed_methods, "
            f"got {report['prescribed_methods']}"
        )
        assert report["method_choice_owned_by_framework"] is True


# ── negative: BabyLM prompts fail audit ──────────────────────────────

class TestBabylmPromptsFailAudit:
    """BabyLM wrapper scripts prescribe Transformer / PyTorch /
    HuggingFace and must be rejected."""

    def test_babylm_gpt_fullrun_fails(self, babylm_gpt_fullrun_script: Path) -> None:
        """The BabyLM GPT fullrun script prescribes Transformer, PyTorch,
        and HuggingFace — it must fail the audit."""
        audit = audit_file(babylm_gpt_fullrun_script)
        assert not audit.passed, (
            "BabyLM GPT fullrun script MUST fail audit (it prescribes "
            "Transformer/PyTorch/HuggingFace)"
        )
        assert len(audit.prescribed_methods) > 0, (
            "BabyLM GPT fullrun script must have at least one "
            "prescribed_method"
        )

    def test_babylm_gpt_has_transformer_finding(self, babylm_gpt_fullrun_script: Path) -> None:
        """The audit must find Transformer as a forbidden constraint."""
        audit = audit_file(babylm_gpt_fullrun_script)
        transformer_findings = [
            f for f in audit.findings
            if f.classification == "forbidden" and "Transformer" in f.label
        ]
        assert transformer_findings, (
            "BabyLM GPT audit must find Transformer as a forbidden "
            "constraint"
        )

    def test_babylm_gpt_has_pytorch_finding(self, babylm_gpt_fullrun_script: Path) -> None:
        """The audit must find PyTorch as a forbidden constraint."""
        audit = audit_file(babylm_gpt_fullrun_script)
        pytorch_findings = [
            f for f in audit.findings
            if f.classification == "forbidden" and "PyTorch" in f.label
        ]
        assert pytorch_findings, (
            "BabyLM GPT audit must find PyTorch as a forbidden "
            "constraint"
        )

    def test_babylm_gpt_has_huggingface_finding(self, babylm_gpt_fullrun_script: Path) -> None:
        """The audit must find HuggingFace as a forbidden constraint."""
        audit = audit_file(babylm_gpt_fullrun_script)
        hf_findings = [
            f for f in audit.findings
            if f.classification == "forbidden" and "HuggingFace" in f.label
        ]
        assert hf_findings, (
            "BabyLM GPT audit must find HuggingFace as a forbidden "
            "constraint"
        )

    def test_babylm_gpt_has_neural_network_finding(self, babylm_gpt_fullrun_script: Path) -> None:
        """The audit must find 'neural network' as a forbidden algorithm
        family prescription."""
        audit = audit_file(babylm_gpt_fullrun_script)
        nn_findings = [
            f for f in audit.findings
            if f.classification == "forbidden" and "neural_network" in f.label
        ]
        assert nn_findings, (
            "BabyLM GPT audit must find 'neural network' as a forbidden "
            "algorithm family prescription"
        )

    def test_babylm_gpt_report_shows_failed(self, babylm_gpt_fullrun_script: Path) -> None:
        """The combined audit report for BabyLM GPT must show status=failed
        and non-empty prescribed_methods with Transformer/PyTorch/HF."""
        audit = audit_file(babylm_gpt_fullrun_script)
        report = build_audit_report([audit], framework_id="01")
        assert report["status"] == "failed", (
            f"BabyLM GPT audit report should be failed, got "
            f"{report['status']}"
        )
        assert len(report["prescribed_methods"]) > 0, (
            "BabyLM GPT audit report should have non-empty "
            "prescribed_methods"
        )
        # Verify the specific labels are present
        labels = " ".join(report["prescribed_methods"]).lower()
        assert "transformer" in labels, (
            f"BabyLM GPT prescribed_methods must include Transformer, "
            f"got: {report['prescribed_methods']}"
        )
        assert "pytorch" in labels, (
            f"BabyLM GPT prescribed_methods must include PyTorch, "
            f"got: {report['prescribed_methods']}"
        )
        assert "huggingface" in labels, (
            f"BabyLM GPT prescribed_methods must include HuggingFace, "
            f"got: {report['prescribed_methods']}"
        )

    def test_babylm_kimi_fullrun_fails(self, babylm_kimi_fullrun_script: Path) -> None:
        """The BabyLM Kimi fullrun script also prescribes Transformer /
        PyTorch / HuggingFace — it must fail the audit."""
        audit = audit_file(babylm_kimi_fullrun_script)
        assert not audit.passed, (
            "BabyLM Kimi fullrun script MUST fail audit (it prescribes "
            "Transformer/PyTorch/HuggingFace)"
        )
        assert len(audit.prescribed_methods) > 0, (
            "BabyLM Kimi fullrun script must have at least one "
            "prescribed_method"
        )


# ── output format compliance ─────────────────────────────────────────

class TestAuditOutputFormat:
    """The audit output must conform to native_prompt_audit.v1 format."""

    def test_output_has_required_fields(self, arc_fullrun_script: Path) -> None:
        audit = audit_file(arc_fullrun_script)
        report = build_audit_report([audit], framework_id="01")
        required_top = [
            "standard_version",
            "framework_id",
            "status",
            "method_choice_owned_by_framework",
            "prescribed_methods",
            "reviewed_host_constraints",
            "prompt_files",
        ]
        for key in required_top:
            assert key in report, (
                f"Audit report missing required field: {key}"
            )

    def test_prompt_files_have_sha256(self, arc_fullrun_script: Path) -> None:
        audit = audit_file(arc_fullrun_script)
        report = build_audit_report([audit], framework_id="01")
        for pf in report["prompt_files"]:
            assert "path" in pf, "prompt_files entry missing 'path'"
            assert "sha256" in pf, "prompt_files entry missing 'sha256'"
            assert len(pf["sha256"]) == 64, (
                f"SHA-256 must be 64 hex chars, got {len(pf['sha256'])} "
                f"for {pf['path']}"
            )
            assert re.match(r"^[a-f0-9]{64}$", pf["sha256"]), (
                f"SHA-256 must be lowercase hex, got {pf['sha256']} "
                f"for {pf['path']}"
            )

    def test_prescribed_methods_is_list(self, babylm_gpt_fullrun_script: Path) -> None:
        audit = audit_file(babylm_gpt_fullrun_script)
        report = build_audit_report([audit], framework_id="01")
        assert isinstance(report["prescribed_methods"], list), (
            "prescribed_methods must be a list"
        )
        # When the audit fails, the list must be non-empty
        assert len(report["prescribed_methods"]) > 0, (
            "Failed audit must have non-empty prescribed_methods"
        )

    def test_status_is_passed_or_failed(self, arc_fullrun_script: Path,
                                        babylm_gpt_fullrun_script: Path) -> None:
        arc_audit = audit_file(arc_fullrun_script)
        babylm_audit = audit_file(babylm_gpt_fullrun_script)
        arc_report = build_audit_report([arc_audit])
        babylm_report = build_audit_report([babylm_audit])
        assert arc_report["status"] == "passed"
        assert babylm_report["status"] == "failed"


# ── forbidden patterns correctness ───────────────────────────────────

class TestForbiddenPatterns:
    """Verify that the FORBIDDEN_PATTERNS list in the audit module is
    correctly configured."""

    def test_forbidden_patterns_detect_transformer(self) -> None:
        """The patterns must detect 'Transformer' in a line."""
        for pat, label in FORBIDDEN_PATTERNS:
            if "Transformer" in label:
                assert pat.search("The model must be a Transformer"), (
                    f"Pattern {pat} should match 'Transformer'"
                )
                break
        else:
            pytest.fail("No FORBIDDEN_PATTERN for Transformer found")

    def test_forbidden_patterns_detect_pytorch(self) -> None:
        """The patterns must detect 'PyTorch' in a line."""
        for pat, label in FORBIDDEN_PATTERNS:
            if "PyTorch" in label:
                assert pat.search("Use PyTorch for training"), (
                    f"Pattern {pat} should match 'PyTorch'"
                )
                break
        else:
            pytest.fail("No FORBIDDEN_PATTERN for PyTorch found")

    def test_forbidden_patterns_detect_huggingface(self) -> None:
        """The patterns must detect 'HuggingFace' in a line."""
        for pat, label in FORBIDDEN_PATTERNS:
            if "HuggingFace" in label:
                assert pat.search("from HuggingFace Transformers"), (
                    f"Pattern {pat} should match 'HuggingFace'"
                )
                break
        else:
            pytest.fail("No FORBIDDEN_PATTERN for HuggingFace found")

    def test_allowed_patterns_do_not_false_positive(self) -> None:
        """Allowed patterns like 'dataset_root' must not trigger
        forbidden classification."""
        # The audit module's _classify_line should handle this correctly
        # by checking forbidden first, then allowed.
        from real_eval.scripts.audit_ai_researcher_prompts import _classify_line
        clean_line = "dataset_root = /data/arc_wbe_2026"
        findings = _classify_line(clean_line, 1)
        forbidden = [f for f in findings if f.classification == "forbidden"]
        assert not forbidden, (
            f"'dataset_root' should not be classified as forbidden, "
            f"got {forbidden}"
        )
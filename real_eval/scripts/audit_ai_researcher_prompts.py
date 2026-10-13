#!/usr/bin/env python3
"""Audit host prompts for method neutrality.

Scans prompt files (shell scripts, markdown, JSON, Python metaprompts)
and classifies every host-imposed constraint as allowed or forbidden per
the Versioned Native Evaluation Standard.

Outputs native_prompt_audit.v1 format JSON with ``prescribed_methods: []``
when the prompt is clean, or a non-empty list when the host prescribes
an algorithm family, architecture, hyperparameters, baseline, experiment
order, or selected method.

Usage:
    python3 audit_ai_researcher_prompts.py <path> [<path> ...]

Each <path> may be a file or a directory (scanned recursively for
``.sh``, ``.md``, ``.json``, ``.py``, ``.yaml``, ``.yml``, ``.toml``).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


# ── allowed / forbidden patterns ──────────────────────────────────────

# Allowed host constraints — the host may fix these.
# Each entry is a (regex, label) pair.
ALLOWED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"topic[_\s]?(question|id|label)", re.IGNORECASE), "topic_question"),
    (re.compile(r"(dataset|data)[_\s]?(root|mount|path|visible)", re.IGNORECASE), "data_visibility"),
    (re.compile(r"(train[_\s]?validation|split)", re.IGNORECASE), "train_validation_split"),
    (re.compile(r"(official[_\s]?)?metric", re.IGNORECASE), "official_metric"),
    (re.compile(r"(compute|wall[_\s]?clock|request)[_\s]?budget", re.IGNORECASE), "compute_budget"),
    (re.compile(r"experiment[_\s]?(count|budget|limit|range)", re.IGNORECASE), "experiment_count_range"),
    (re.compile(r"(available|allowed)[_\s]?(dependencies|imports|packages)", re.IGNORECASE), "available_dependencies"),
    (re.compile(r"(network|safety)[_\s]?policy", re.IGNORECASE), "network_policy"),
    (re.compile(r"output[_\s]?schema", re.IGNORECASE), "output_schema"),
    (re.compile(r"(result[_\s]?field|required[_\s]?result)", re.IGNORECASE), "output_schema"),
    (re.compile(r"framework[_\s]?owns", re.IGNORECASE), "method_choice_owned_by_framework"),
]

# Forbidden host constraints — these MUST NOT appear in a host prompt.
# When detected, the matching text is recorded as a prescribed_method.
FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Algorithm families
    (re.compile(r"Transformer", re.IGNORECASE), "algorithm_family:Transformer"),
    (re.compile(r"\b(LSTM|GRU|RNN)\b", re.IGNORECASE), "algorithm_family:RNN"),
    (re.compile(r"\bCNN\b", re.IGNORECASE), "algorithm_family:CNN"),
    (re.compile(r"neural\s+network", re.IGNORECASE), "algorithm_family:neural_network"),
    (re.compile(r"n-gram|ngram|count.based", re.IGNORECASE), "algorithm_family:n_gram"),
    (re.compile(r"GPT[-\s]?(style|architecture|model)", re.IGNORECASE), "algorithm_family:GPT"),
    (re.compile(r"decoder.only", re.IGNORECASE), "algorithm_family:decoder_only"),
    # Model architectures
    (re.compile(r"model\s+(must|should|has to|needs to|shall)\s+be\s+a", re.IGNORECASE), "model_architecture:prescribed_model_type"),
    (re.compile(r"model architecture", re.IGNORECASE), "model_architecture"),
    # Libraries/frameworks that prescribe method
    (re.compile(r"PyTorch", re.IGNORECASE), "framework:PyTorch"),
    (re.compile(r"HuggingFace", re.IGNORECASE), "framework:HuggingFace"),
    (re.compile(r"scikit-learn|sklearn", re.IGNORECASE), "framework:sklearn"),
    (re.compile(r"TensorFlow|Keras", re.IGNORECASE), "framework:TensorFlow"),
    # Hyperparameters
    (re.compile(r"(learning.rate|batch.size|dropout|num.layers|hidden.size|num.heads)", re.IGNORECASE), "hyperparameters"),
    # Baselines
    (re.compile(r"(baseline|baseline_name)", re.IGNORECASE), "baseline"),
    # Experiment order / sequence
    (re.compile(r"(experiment.sequence|experiment.order|run\s+in\s+order)", re.IGNORECASE), "experiment_sequence"),
    # Selected method
    (re.compile(r"selected[_\s]?method", re.IGNORECASE), "selected_method"),
    # Prescribed method language
    (re.compile(r"the\s+model\s+(should|must|shall|has.to|needs.to)\s+be", re.IGNORECASE), "prescribed_method"),
    (re.compile(r"must\s+be\s+a\s+neural", re.IGNORECASE), "prescribed_method:must_be_neural"),
    (re.compile(r"not\s+an?\s+(n.gram|count.based)", re.IGNORECASE), "prescribed_method:not_n_gram"),
]

# Patterns that are purely declarative / self-referential — excluded from
# classification (they describe the audit or the standard itself).
_IGNORE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"prescribed_methods", re.IGNORECASE),
    re.compile(r"method_choice_owned_by_framework", re.IGNORECASE),
    re.compile(r"algorithm_family", re.IGNORECASE),
    re.compile(r"feature_representation", re.IGNORECASE),
    re.compile(r"model_architecture", re.IGNORECASE),
    re.compile(r"hyperparameters", re.IGNORECASE),
    re.compile(r"experiment_sequence|experiment.order", re.IGNORECASE),
    re.compile(r"selected_method", re.IGNORECASE),
    re.compile(r"allowed_host_constraints", re.IGNORECASE),
    re.compile(r"forbidden_host_constraints", re.IGNORECASE),
    re.compile(r"host_method_prescription_forbidden", re.IGNORECASE),
    re.compile(r"host.prescribe", re.IGNORECASE),
    re.compile(r"host.prescription", re.IGNORECASE),
    re.compile(r"must not prescribe", re.IGNORECASE),
    re.compile(r"do not prescribe", re.IGNORECASE),
    re.compile(r"does not prescribe", re.IGNORECASE),
    re.compile(r"no host.prescribed", re.IGNORECASE),
    re.compile(r"method.prescription", re.IGNORECASE),
    re.compile(r"framework.owns", re.IGNORECASE),
    re.compile(r"the host does not prescribe", re.IGNORECASE),
    re.compile(r"no host-prescribed", re.IGNORECASE),
    re.compile(r"no (algorithm|architecture|hyperparameter|baseline|experiment order|selected method)", re.IGNORECASE),
    re.compile(r"the framework owns the", re.IGNORECASE),
    re.compile(r"the framework must choose", re.IGNORECASE),
    re.compile(r"not prescribed", re.IGNORECASE),
    re.compile(r"method.policy", re.IGNORECASE),
    re.compile(r"framework_owns_method_choice", re.IGNORECASE),
    # Dataset/task descriptions that mention a domain but do not prescribe
    re.compile(r"Transformer MLP", re.IGNORECASE),
    re.compile(r"layer.*Transformer", re.IGNORECASE),
    re.compile(r"white.box estimation.*Transformer", re.IGNORECASE),
    # Allowed-imports / dependency lists — these enumerate what is available,
    # not what the framework must use.
    re.compile(r"allowed_imports", re.IGNORECASE),
    re.compile(r"available[_\s]?(dependencies|imports|packages)", re.IGNORECASE),
    re.compile(r"pip install", re.IGNORECASE),
    re.compile(r"install.*(torch|transformers|datasets)", re.IGNORECASE),
]


def _is_ignored(text: str) -> bool:
    """Return True if *text* is a self-referential or declarative statement
    that should be excluded from classification."""
    for pat in _IGNORE_PATTERNS:
        if pat.search(text):
            return True
    return False


# ── audit record ──────────────────────────────────────────────────────

@dataclass
class ConstraintFinding:
    """A single constraint found in a prompt file."""
    line: int
    text: str
    classification: str  # "allowed" or "forbidden"
    label: str


@dataclass
class FileAudit:
    """Audit result for a single prompt file."""
    path: str
    sha256: str
    findings: list[ConstraintFinding] = field(default_factory=list)
    prescribed_methods: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Pass if no forbidden constraints found."""
        return not any(f.classification == "forbidden" for f in self.findings)


# ── scanning ──────────────────────────────────────────────────────────

_PROMPT_EXTENSIONS = {".sh", ".md", ".json", ".py", ".yaml", ".yml", ".toml"}


def _iter_prompt_files(paths: list[str]) -> Iterator[Path]:
    """Yield all prompt files from the given paths."""
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw).resolve()
        if not p.exists():
            print(f"  [WARN] path does not exist: {p}", file=sys.stderr)
            continue
        if p.is_file():
            if p.suffix in _PROMPT_EXTENSIONS and p not in seen:
                seen.add(p)
                yield p
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix in _PROMPT_EXTENSIONS and child not in seen:
                    # Skip __pycache__
                    if "__pycache__" in child.parts:
                        continue
                    seen.add(child)
                    yield child


def _sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode()
    return hashlib.sha256(content).hexdigest()


def _classify_line(line: str, line_no: int) -> list[ConstraintFinding]:
    """Classify a single line of text.

    Returns a list of ConstraintFinding (usually 0 or 1).
    """
    findings: list[ConstraintFinding] = []
    stripped = line.strip()

    # Skip comments, empty lines, and purely ignorable lines
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return findings
    if _is_ignored(stripped):
        return findings

    # Check forbidden first (fail closed)
    for pat, label in FORBIDDEN_PATTERNS:
        if pat.search(stripped):
            findings.append(ConstraintFinding(
                line=line_no,
                text=stripped[:120],
                classification="forbidden",
                label=label,
            ))
            # Still continue checking allowed — one line may have both
            # (unlikely, but be thorough).

    # Check allowed
    for pat, label in ALLOWED_PATTERNS:
        if pat.search(stripped):
            findings.append(ConstraintFinding(
                line=line_no,
                text=stripped[:120],
                classification="allowed",
                label=label,
            ))

    return findings


def audit_file(path: Path) -> FileAudit:
    """Audit a single prompt file."""
    content = path.read_text(encoding="utf-8", errors="replace")
    sha = _sha256(content)
    audit = FileAudit(path=str(path), sha256=sha)

    for i, line in enumerate(content.splitlines(), 1):
        findings = _classify_line(line, i)
        for f in findings:
            audit.findings.append(f)
            if f.classification == "forbidden":
                audit.prescribed_methods.append(f.label)

    # Deduplicate prescribed_methods while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for m in audit.prescribed_methods:
        if m not in seen:
            seen.add(m)
            deduped.append(m)
    audit.prescribed_methods = deduped

    return audit


# ── output ────────────────────────────────────────────────────────────

def build_audit_report(
    file_audits: list[FileAudit],
    framework_id: str = "01",
) -> dict:
    """Build a native_prompt_audit.v1 format JSON report.

    The overall status is ``passed`` only when every file audit passes.
    """
    overall_passed = all(fa.passed for fa in file_audits)
    all_prescribed: list[str] = []
    seen_pm: set[str] = set()
    for fa in file_audits:
        for m in fa.prescribed_methods:
            if m not in seen_pm:
                seen_pm.add(m)
                all_prescribed.append(m)

    # Build reviewed_host_constraints from all findings
    reviewed: set[str] = set()
    for fa in file_audits:
        for f in fa.findings:
            if f.classification == "allowed":
                reviewed.add(f.label)

    # Default allowed list (always present)
    default_allowed = [
        "topic_question",
        "data_visibility",
        "train_validation_split",
        "official_metric",
        "compute_budget",
        "wall_clock_budget",
        "request_budget",
        "experiment_count_range",
        "available_dependencies",
        "network_policy",
        "safety_policy",
        "output_schema",
    ]
    for d in default_allowed:
        reviewed.add(d)

    report = {
        "standard_version": "1.0",
        "framework_id": framework_id,
        "status": "passed" if overall_passed else "failed",
        "method_choice_owned_by_framework": overall_passed,
        "prescribed_methods": all_prescribed,
        "reviewed_host_constraints": sorted(reviewed),
        "prompt_files": [
            {
                "path": fa.path,
                "sha256": fa.sha256,
                "passed": fa.passed,
                "prescribed_methods": fa.prescribed_methods,
                "findings": [
                    {
                        "line": f.line,
                        "text": f.text,
                        "classification": f.classification,
                        "label": f.label,
                    }
                    for f in fa.findings
                ],
            }
            for fa in file_audits
        ],
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return report


# ── CLI ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__, file=sys.stderr)
        return 0 if "-h" in argv else 1

    file_audits: list[FileAudit] = []
    for prompt_file in _iter_prompt_files(argv):
        fa = audit_file(prompt_file)
        file_audits.append(fa)
        status = "PASS" if fa.passed else "FAIL"
        print(f"  [{status}] {fa.path}  (sha256={fa.sha256[:16]}...)", file=sys.stderr)
        if fa.prescribed_methods:
            for pm in fa.prescribed_methods:
                print(f"         prescribed: {pm}", file=sys.stderr)

    if not file_audits:
        print("  [ERROR] no prompt files found to audit", file=sys.stderr)
        return 1

    report = build_audit_report(file_audits)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
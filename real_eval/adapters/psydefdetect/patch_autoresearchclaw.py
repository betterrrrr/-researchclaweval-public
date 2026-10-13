#!/usr/bin/env python3
"""Apply the runtime-only PsyDefDetect contract adapter to AutoResearchClaw."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

_log = logging.getLogger(__name__)

COMPATIBILITY_MARKERS = {
    "researchclaw/agents/benchmark_agent/surveyor.py": (
        "        domain_ids = self._match_domains(topic)\n"
        "        if hypothesis:\n"
        "            domain_ids = list(dict.fromkeys(\n"
        "                domain_ids + self._match_domains(hypothesis)\n"
        "            ))",
    ),
    "researchclaw/pipeline/stage_impls/_experiment_design.py": (
        "_max_conditions = 8  # default for budgets ≤ 3600s",
    ),
    "researchclaw/pipeline/code_agent.py": (
        "def _hard_validate(",
    ),
    "researchclaw/pipeline/stage_impls/_literature.py": (
        "def _execute_literature_collect(",
    ),
    "researchclaw/pipeline/stage_impls/_execution.py": (
        "def _execute_experiment_run(",
        "def _execute_iterative_refine(",
    ),
}


def check_version_compatibility(root: Path) -> bool:
    """Warn when the copied native source no longer resembles this adapter's target.

    Package metadata is often unavailable in copied AutoResearchClaw workspaces, so
    this advisory check uses the stable native markers that the adapter depends on.
    Exact insertion-point checks in ``PATCH_SOURCE`` remain authoritative.
    """
    missing: list[str] = []
    for relative_path, markers in COMPATIBILITY_MARKERS.items():
        path = root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            missing.append(relative_path)
            continue
        if any(marker not in text for marker in markers):
            missing.append(relative_path)
    if missing:
        _log.warning(
            "AutoResearchClaw PsyDefDetect source compatibility warning: expected "
            "native markers are missing from %s; continuing to exact patch checks.",
            ", ".join(missing),
        )
        return False
    return True


PATCH_SOURCE = ''  # PLACEHOLDER - will be reconstructed

def apply_patch(root: Path) -> None:
    """Patch a copied AutoResearchClaw workspace for the PsyDefDetect contract."""
    patch_workspace(root)


def patch_workspace(root: Path) -> None:
    execute_patch_source(root)


def execute_patch_source(root: Path) -> None:
    paths = (
        'researchclaw/data/benchmark_knowledge.yaml',
        'psydefdetect_benchmark_knowledge.yaml',
        'researchclaw/agents/benchmark_agent/surveyor.py',
        'researchclaw/pipeline/stage_impls/_experiment_design.py',
        'researchclaw/pipeline/code_agent.py',
        'researchclaw/pipeline/stage_impls/_code_generation.py',
        'researchclaw/pipeline/stage_impls/_literature.py',
        'researchclaw/experiment/agentic_sandbox.py',
        'researchclaw/experiment/sandbox.py',
        'researchclaw/pipeline/stage_impls/_execution.py',
        'researchclaw/pipeline/stage_impls/_analysis.py',
        'researchclaw/literature/novelty.py',
        'researchclaw/pipeline/stage_impls/_code_generation.py',
    )
    previous_argv = sys.argv
    sys.argv = [str(root), *(str(root / relative) for relative in paths)]
    try:
        exec(compile(PATCH_SOURCE, str(root / ".psydefdetect_adapter.py"), "exec"), {})
    finally:
        sys.argv = previous_argv


def main(argv: Sequence[str]) -> int:
    """Apply the adapter to the workspace passed by the thin shell runner."""
    if len(argv) != 2:
        raise SystemExit("usage: patch_autoresearchclaw.py WORKSPACE")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    root = Path(argv[1])
    check_version_compatibility(root)
    apply_patch(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

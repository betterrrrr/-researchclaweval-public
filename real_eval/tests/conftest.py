"""Skips for contract tests that inspect upstream framework sources.

setup.sh clones the framework checkouts into the repository root. Several tests
here read those sources to prove the recorded adapter still matches upstream.
Without the checkouts those tests cannot run — but the control-plane tests
still can, so instead of failing they report as skipped.

Run `bash setup.sh --quick` to fetch the checkouts this repository ships
recipes for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Map the slug used in test file names to the directory the checkout lands in.
SLUG_TO_DIR = {
    "ai_researcher": "AI-Researcher",
    "ai_scientist_v2": "AI-Scientist-v2",
    "autoresearchclaw": "AutoResearchClaw",
    "deepscientist": "DeepScientist",
    "drclaw": "dr-claw",
    "dr_claw": "dr-claw",
    "evoscientist": "EvoScientist",
    "aris": "Auto-claude-code-research-in-sleep",
}


def _registered_source_dirs() -> dict[str, str]:
    """Prefer the registry's own mapping when it is readable."""
    path = ROOT / "real_eval" / "registry" / "frameworks.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        row["id"]: row["source_dir"]
        for row in payload.get("frameworks", [])
        if "source_dir" in row
    }


def _known_failures() -> set[str]:
    """Test ids recorded as currently disagreeing with the implementation."""
    path = Path(__file__).with_name("known_failures.txt")
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def pytest_collection_modifyitems(config, items) -> None:
    registered = _registered_source_dirs()
    known = _known_failures()
    for item in items:
        name = Path(str(item.fspath)).name
        for slug, dirname in SLUG_TO_DIR.items():
            if slug not in name:
                continue
            candidates = {dirname, *[d for d in registered.values()]}
            if any((ROOT / candidate).exists() for candidate in candidates):
                continue
            item.add_marker(
                pytest.mark.skip(
                    reason=f"requires the {dirname} checkout (run: bash setup.sh --quick)"
                )
            )
            break

        if item.nodeid in known:
            item.add_marker(
                pytest.mark.xfail(
                    reason="recorded in known_failures.txt: implementation and test "
                    "do not yet agree",
                    strict=False,
                )
            )

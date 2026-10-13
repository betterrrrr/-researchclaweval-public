from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TOP_LEVEL = {
    ".framework-refresh",
    ".sdd",
    "AI-Researcher",
    "AI-Scientist-v2",
    "Auto-claude-code-research-in-sleep",
    "AutoResearchClaw",
    "DeepScientist",
    "EvoScientist",
    "api",
    "data",
    "dr-claw",
    "external",
    "recovery",
}
SECRET_PATTERN = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,}|"
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
)


def public_files() -> list[Path]:
    ignored_parts = {".git", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not ignored_parts.intersection(path.relative_to(ROOT).parts)
    ]


def test_private_top_level_directories_are_absent() -> None:
    assert not {path.name for path in ROOT.iterdir()} & FORBIDDEN_TOP_LEVEL


def test_public_files_have_no_machine_paths_or_secret_literals() -> None:
    private_roots = (
        "/home/" + "jianbiao" + "/researchclaweval",
        "/home/" + "guanghao" + "/researchclaweval",
    )
    for path in public_files():
        assert path.stat().st_size <= 5 * 1024 * 1024, path
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert all(root not in text for root in private_roots), path
        assert SECRET_PATTERN.search(text) is None, path


def test_no_bare_account_names() -> None:
    """A bare account name leaks the same way a full path does.

    This module and scripts/check_public_boundary.sh name these accounts by
    construction, so they are the only files allowed to contain them.
    """
    allowed = {
        Path(__file__).resolve(),
        ROOT / "scripts" / "check_public_boundary.sh",
    }
    accounts = ("jianb" + "iao", "guang" + "hao")
    for path in public_files():
        if path.resolve() in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert all(account not in text for account in accounts), path

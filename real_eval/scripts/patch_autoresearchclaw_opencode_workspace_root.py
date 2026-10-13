"""Make OpenCode write its output where the bridge actually looks for it.

Problem
-------
`OpenCodeBridge._prepare_workspace()` builds a scratch directory and
`_invoke_opencode()` runs `opencode run ... ` with `cwd=<that directory>`, then
`_collect_files(workspace)` reads the generated `.py` files back from it.

OpenCode does not treat that cwd as the project root.  It resolves the project
to HOME (`/workspace` in these runs) and writes its output there, so the beast
workspace ends up holding only the prepared context files:

    Beast mode: OpenCode succeeded but no main.py found (files: [])

The captured transcript (see
patch_autoresearchclaw_opencode_no_main_diagnostics.py) makes this explicit —
the run finishes cleanly, with no error events, and reports success:

    "filePath":"/workspace/main.py"
    "filePath":"/workspace/estimator.py"
    "filePath":"/workspace/requirements.txt"
    "Implemented the ARC-WBE experiment in `/workspace` ...
     Validation passed: compilation, JSON artifacts, all prediction
     shape/finite smoke tests, and full six-condition execution."

So the work is done correctly and then thrown away, and Beast Mode falls back
to CodeAgent on every stage.

Fix
---
1. Pass `--dir <workspace>` to `opencode run` so the project root is pinned to
   the scratch directory instead of HOME.
2. Belt and braces: if the workspace still has no `main.py`, recover whatever
   OpenCode wrote into HOME during this attempt (top level only, so the
   framework's own tree is never picked up).
"""
import ast
import sys
from pathlib import Path

TARGET = Path(
    sys.argv[1] if len(sys.argv) > 1
    else "/workspace/researchclaw/pipeline/opencode_bridge.py"
)

MARKER = "_recover_from_home"

# --- Site 1: pin the project root on the CLI --------------------------------
OLD_1 = """        cmd = [opencode_cmd, "run", "-m", resolved_model, "--format", "json", prompt]
"""
NEW_1 = """        # patched: pin the project root. Without --dir OpenCode resolves the
        # project to HOME instead of this cwd and writes its output there,
        # leaving the beast workspace empty ("no main.py found").
        cmd = [
            opencode_cmd, "run", "-m", resolved_model, "--format", "json",
            "--dir", str(workspace), prompt,
        ]
"""

# --- Site 2: recover output written into HOME -------------------------------
OLD_2 = """            if success:
                files = self._collect_files(workspace)
                if "main.py" not in files:
"""
NEW_2 = """            if success:
                files = self._collect_files(workspace)
                if "main.py" not in files:
                    # patched: OpenCode may have written the experiment into
                    # HOME rather than this workspace; recover it before
                    # declaring the attempt a failure.
                    files = self._recover_from_home(files, workspace)
                if "main.py" not in files:
"""

# --- Site 3: the recovery helper -------------------------------------------
OLD_3 = """    @staticmethod
    def _collect_files(workspace: Path) -> dict[str, str]:
"""
NEW_3 = """    @staticmethod
    def _recover_from_home(
        files: dict[str, str],
        workspace: Path,
    ) -> dict[str, str]:
        \"\"\"Patched: salvage output OpenCode wrote into HOME, not the workspace.

        Only top-level files of HOME are considered, and the framework's own
        tree is skipped, so this cannot pick up unrelated Python sources.
        \"\"\"
        try:
            home = Path(os.environ.get("HOME", "") or "")
            if not home.is_dir() or home.resolve() == workspace.resolve():
                return files

            started_at = workspace.stat().st_mtime if workspace.exists() else 0.0
            recovered = dict(files)
            skip_dirs = {
                "researchclaw", "real_eval", "artifacts", "automation",
                "data", "knowledge", ".config", ".local", ".cache", "bin",
            }
            for child in sorted(home.iterdir()):
                if not child.is_file():
                    continue
                if child.suffix != ".py" and child.name not in (
                    "requirements.txt", "setup.py", "pyproject.toml",
                ):
                    continue
                if child.name in skip_dirs:
                    continue
                try:
                    if child.stat().st_mtime < started_at - 1.0:
                        continue
                except OSError:
                    continue
                if child.suffix == ".py" and child.name in recovered:
                    continue
                try:
                    recovered[child.name] = child.read_text(
                        encoding="utf-8", errors="replace",
                    )
                except OSError:
                    continue

            if "main.py" in recovered and "main.py" not in files:
                logger.warning(
                    "Beast mode: recovered %d file(s) from HOME %s "
                    "(OpenCode wrote outside the workspace)",
                    len(recovered) - len(files), home,
                )
            return recovered
        except OSError as exc:  # noqa: BLE001
            logger.warning("Beast mode: HOME recovery failed: %s", exc)
            return files

    @staticmethod
    def _collect_files(workspace: Path) -> dict[str, str]:
"""

if not TARGET.exists():
    raise SystemExit(f"[oc-workspace-root] target not found: {TARGET}")

text = TARGET.read_text(encoding="utf-8")

if MARKER in text:
    print(f"[oc-workspace-root] already patched: {TARGET}")
    raise SystemExit(0)

for label, old in (("1(--dir)", OLD_1), ("2(call site)", OLD_2), ("3(helper)", OLD_3)):
    if old not in text:
        raise SystemExit(f"[oc-workspace-root] site {label} not matched - source changed?")

text = text.replace(OLD_1, NEW_1, 1)
text = text.replace(OLD_2, NEW_2, 1)
text = text.replace(OLD_3, NEW_3, 1)
TARGET.write_text(text, encoding="utf-8")

final = TARGET.read_text(encoding="utf-8")
ast.parse(final)
assert MARKER in final
assert '"--dir"' in final
print(f"[oc-workspace-root] patched {TARGET}")
print("[oc-workspace-root] verified: --dir pinned + HOME recovery installed")

"""Keep the evidence when OpenCode "succeeds" but produces no main.py.

Problem
-------
After the model-resolution fix (patch_autoresearchclaw_opencode_global_config.py)
Beast Mode no longer dies in ~1.6s, but some attempts now report:

    Beast mode: OpenCode succeeded but no main.py found (files: [])

i.e. `_invoke_opencode` returned rc==0, yet `_collect_files(workspace)` found
zero Python files.  On this branch the bridge

  * never writes OpenCode's stdout/stderr anywhere (the transcript is only
    persisted on the success path, further down), and
  * deletes the generated workspace (`shutil.rmtree`) before retrying.

So every occurrence destroys its own evidence and the cause cannot be
determined after the fact.  Observed attempt durations vary widely (30s, 91s,
557s), so it is neither a stable timeout nor a stable fast-fail.

Fix
---
On this branch, before the existing cleanup, persist:
  * `opencode_no_main_attempt<N>.txt`          — full stdout+stderr transcript
  * `opencode_no_main_attempt<N>.listing.txt`  — workspace file manifest plus
                                                 the prepared context files
and keep the workspace instead of removing it.

Diagnostics only: control flow, retry behaviour and return values are
unchanged.  The workspace is left behind on purpose so it can be inspected;
remove the `opencode_beast_*` directories under the stage dir when done.
"""
import ast
import sys
from pathlib import Path

TARGET = Path(
    sys.argv[1] if len(sys.argv) > 1
    else "/workspace/researchclaw/pipeline/opencode_bridge.py"
)

MARKER = "opencode_no_main_"

OLD = """                if "main.py" not in files:
                    logger.warning(
                        "Beast mode: OpenCode succeeded but no main.py found "
                        "(files: %s)", list(files.keys()),
                    )
                    last_error = "No main.py in OpenCode output"
                    # Cleanup failed workspace
                    if self._workspace_cleanup and workspace.exists():
                        shutil.rmtree(workspace, ignore_errors=True)
                    continue
"""

NEW = """                if "main.py" not in files:
                    logger.warning(
                        "Beast mode: OpenCode succeeded but no main.py found "
                        "(files: %s)", list(files.keys()),
                    )
                    # patched: persist the transcript + workspace manifest and
                    # KEEP the workspace.  Previously both were discarded here,
                    # which made this failure impossible to diagnose.
                    try:
                        _diag = f"attempt{attempt + 1}"
                        (stage_dir / f"opencode_no_main_{_diag}.txt").write_text(
                            log or "", encoding="utf-8",
                        )
                        _lines: list[str] = []
                        if workspace.exists():
                            for _p in sorted(workspace.rglob("*")):
                                try:
                                    _rel = _p.relative_to(workspace)
                                except ValueError:
                                    continue
                                if ".git" in _rel.parts:
                                    continue
                                if _p.is_dir():
                                    _lines.append(f"d {_rel}")
                                else:
                                    try:
                                        _sz = _p.stat().st_size
                                    except OSError:
                                        _sz = -1
                                    _lines.append(f"f {_rel} ({_sz} bytes)")
                            for _extra in (
                                "opencode.json", "EXPERIMENT_PLAN.yaml",
                                "GUIDANCE.md",
                            ):
                                _ep = workspace / _extra
                                if _ep.is_file():
                                    _lines.append(
                                        f"\\n===== {_extra} =====\\n"
                                        + _ep.read_text(
                                            encoding="utf-8", errors="replace",
                                        )[:4000]
                                    )
                        (stage_dir / f"opencode_no_main_{_diag}.listing.txt").write_text(
                            "\\n".join(_lines) or "(workspace empty)",
                            encoding="utf-8",
                        )
                        logger.warning(
                            "Beast mode: diagnostics written to %s (workspace kept: %s)",
                            stage_dir / f"opencode_no_main_{_diag}.txt", workspace,
                        )
                    except OSError as _dexc:
                        logger.warning(
                            "Beast mode: diagnostics write failed: %s", _dexc,
                        )
                    last_error = "No main.py in OpenCode output"
                    # patched: workspace intentionally NOT removed here (was rmtree)
                    continue
"""

if not TARGET.exists():
    raise SystemExit(f"[oc-no-main-diag] target not found: {TARGET}")

text = TARGET.read_text(encoding="utf-8")

if MARKER in text:
    print(f"[oc-no-main-diag] already patched: {TARGET}")
    raise SystemExit(0)

if OLD not in text:
    raise SystemExit("[oc-no-main-diag] anchor not matched - source changed?")

text = text.replace(OLD, NEW, 1)
TARGET.write_text(text, encoding="utf-8")

final = TARGET.read_text(encoding="utf-8")
ast.parse(final)
assert MARKER in final
assert "shutil.rmtree(workspace, ignore_errors=True)\n                    continue" not in final
print(f"[oc-no-main-diag] patched {TARGET}")
print("[oc-no-main-diag] verified: transcript+manifest persisted, workspace kept")

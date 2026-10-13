"""Patch researchclaw's PromptManager._load_extras to handle long text values.

Bug: Path(text).expanduser().exists() raises OSError [Errno 36] for text > 255 chars
because os.stat() has a 255-byte filename limit. This crashes the pipeline when
extra_prompts values are long strings (e.g., ARC weights-only contract).

Fix: catch OSError in candidate.exists() and treat as non-file path.
"""
import re
from pathlib import Path

target = Path(__file__).resolve().parent.parent / "researchclaw" / "prompts" / "manager.py"
if not target.exists():
    # Try alternate locations
    for p in [Path("/workspace/researchclaw/prompts/manager.py"),
              Path.cwd() / "researchclaw/prompts/manager.py"]:
        if p.exists():
            target = p
            break

if not target.exists():
    raise SystemExit(f"manager.py not found (tried: {target})")

text = target.read_text(encoding="utf-8")

old = """            candidate = Path(text).expanduser()
            if candidate.exists() and candidate.is_file():"""

new = """            candidate = Path(text).expanduser()
            try:
                _exists = candidate.exists() and candidate.is_file()
            except OSError:
                _exists = False
            if _exists:"""

if old not in text:
    raise SystemExit(f"manager.py patch target not found in {target}")

text = text.replace(old, new, 1)
target.write_text(text, encoding="utf-8")
print(f"Patched {target}: OSError in _load_extras is now caught")
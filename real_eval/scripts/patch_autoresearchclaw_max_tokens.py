"""Raise AutoResearchClaw code-generation output budgets.

Problem: `_code_generation.py` only raises the code-generation `max_tokens`
to 16384 for models whose name starts with "gpt-5", "o3" or "o4":

    _code_max_tokens = sp.max_tokens or 8192
    if any(config.llm.primary_model.startswith(p) for p in ("gpt-5", "o3", "o4")):
        _code_max_tokens = max(_code_max_tokens, 16384)

Any other model (e.g. "GPT-6-Luna") silently gets only 8192 output tokens.
Large experiment files (BabyLM transformer ~42 KB, ARC estimator) then get
TRUNCATED mid-string, producing `SyntaxError: unterminated string literal`
and a failed Stage 12 after all retries.

This patch raises the default budget for every model:
  - default code budget     8192  -> 32768
  - unconditional floor     -> 32768 (case-insensitive; no name-prefix gate)
"""
from pathlib import Path

CODE_GEN = Path("/workspace/researchclaw/pipeline/stage_impls/_code_generation.py")

OLD_DEFAULT = "    _code_max_tokens = 8192\n"
NEW_DEFAULT = "    _code_max_tokens = 32768\n"

# Site A: initial default before Beast Mode / CodeAgent dispatch
OLD_A = "    _code_max_tokens = 8192\n"

# Site B: nested `if any(...)` form used on the sandbox path
OLD_B = (
    '        if any(\n'
    '            config.llm.primary_model.startswith(p)\n'
    '            for p in ("gpt-5", "o3", "o4")\n'
    '        ):\n'
    '            _code_max_tokens = 16384\n'
)
NEW_B = (
    '        # patched: raise budget for ALL models (was gpt-5/o3/o4 only)\n'
    '        _code_max_tokens = max(_code_max_tokens, 32768)\n'
)

# Site C: single-line `if any(...)` form on the CodeAgent path
OLD_C = (
    '        _code_max_tokens = sp.max_tokens or 8192\n'
    '        if any(config.llm.primary_model.startswith(p) for p in ("gpt-5", "o3", "o4")):\n'
    '            _code_max_tokens = max(_code_max_tokens, 16384)\n'
)
NEW_C = (
    '        _code_max_tokens = sp.max_tokens or 32768\n'
    '        # patched: raise budget for ALL models (was gpt-5/o3/o4 only)\n'
    '        _code_max_tokens = max(_code_max_tokens, 32768)\n'
)

if not CODE_GEN.exists():
    raise SystemExit(f"[max_tokens] target not found: {CODE_GEN}")

text = CODE_GEN.read_text(encoding="utf-8")
applied = []

if OLD_C in text:
    text = text.replace(OLD_C, NEW_C, 1)
    applied.append("C(code_agent default 8192->32768 + floor 32768)")

if OLD_B in text:
    text = text.replace(OLD_B, NEW_B, 1)
    applied.append("B(sandbox gpt-5-gate -> unconditional 32768)")

# Site A: only the bare initialiser, after B/C already rewrote their copies
if OLD_A in text:
    text = text.replace(OLD_A, NEW_DEFAULT, 1)
    applied.append("A(initial default 8192->32768)")

if not applied:
    raise SystemExit("[max_tokens] no insertion point matched - source changed?")

CODE_GEN.write_text(text, encoding="utf-8")
print(f"[max_tokens] patched {CODE_GEN.name}: {', '.join(applied)}")

# Verify no bare 8192 default remains on the code path
remaining = text.count("sp.max_tokens or 8192") + text.count("_code_max_tokens = 8192")
if remaining:
    raise SystemExit(f"[max_tokens] {remaining} old default(s) still present")
print("[max_tokens] verified: no 8192 code-generation default remains")

"""Patch: Retry code generation from scratch when validation fails.
Instead of returning FAILED, recursively call _execute_code_generation
with previous errors included in topic. Max AUTORESEARCHCLAW_MAX_CODE_RETRY (default 3).
Retry counter stored in stage_dir/.code_retry_count.
"""
import os
from pathlib import Path

target = Path("/workspace/researchclaw/pipeline/stage_impls/_code_generation.py")
if not target.exists():
    for p in [
        Path.cwd() / "researchclaw" / "pipeline" / "stage_impls" / "_code_generation.py",
        Path.cwd() / "AutoResearchClaw" / "researchclaw" / "pipeline" / "stage_impls" / "_code_generation.py",
        Path(__file__).resolve().parent.parent / "AutoResearchClaw" / "researchclaw" / "pipeline" / "stage_impls" / "_code_generation.py",
    ]:
        if p.exists(): target = p; break
if not target.exists():
    print("[patch] _code_generation.py not found"); raise SystemExit(0)

text = target.read_text(encoding="utf-8")

# Build the old block - the indentation before 'if _has_critical:' is 8 spaces
NL = '\n'
old = (
    '        if _has_critical:\n'
    '            logger.error(\n'
    f'                "Stage 10: CRITICAL validation issues remain after %d repair "{NL}'
    '                "attempts. Blocking stage.", max_repair,\n'
    '            )\n'
    '            (stage_dir / "validation_report.md").write_text(\n'
    f'                "# Code Validation Report\\n\\n"{NL}'
    '                f"**Status**: BLOCKED — critical issues remain after {max_repair} repairs\\n\\n"\n'
    '                + "\\n".join(f"- {e}" for e in validation_log),\n'
    '                encoding="utf-8",\n'
    '            )\n'
    '            return StageResult(\n'
    '                stage=Stage.CODE_GENERATION,\n'
    '                status=StageStatus.FAILED,\n'
    '                artifacts=("validation_report.md",),\n'
    '                evidence_refs=(),\n'
    '            )'
)

# Check using fstring-style matching (the actual code has f-string with max_repair)
# Use a regex-like approach
import re
# Escape the old pattern for regex matching
pattern_lines = [
    r'        if _has_critical:',
    r'            logger\.error\(',
    r'                "Stage 10: CRITICAL validation issues remain after %d repair "',
    r'                "attempts\. Blocking stage\.", max_repair,',
    r'            \)',
    r'            \(stage_dir / "validation_report\.md"\)\.write_text\(',
    r'                "# Code Validation Report\\n\\n"',
    r'                f"\*\*Status\*\*: BLOCKED — critical issues remain after \{max_repair\} repairs\\n\\n"',
    r'                \+ "\\n"\.join\(f"- {e}" for e in validation_log\),',
    r'                encoding="utf-8",',
    r'            \)',
    r'            return StageResult\(',
    r'                stage=Stage\.CODE_GENERATION,',
    r'                status=StageStatus\.FAILED,',
    r'                artifacts=\("validation_report\.md",\),',
    r'                evidence_refs=\(\),',
    r'            \)',
]
pattern = '\\n'.join(pattern_lines)
match = re.search(pattern, text)
if not match:
    print("[patch] FAILED block not found via regex!")
    print("[patch] Showing first occurrence of 'if _has_critical:':")
    idx = text.find('if _has_critical:')
    if idx >= 0:
        lines = text[idx:].split('\\n')
        for i, l in enumerate(lines[:20]):
            print(f"  {i}: {l!r}")
    raise SystemExit(1)

old_block = match.group(0)
start, end = match.start(), match.end()
print(f"[patch] Found FAILED block at {start}-{end}")

# Build the new block with the same indentation
new = (
    '        if _has_critical:\n'
    '            _retry_count_file = stage_dir / ".code_retry_count"\n'
    '            _retry_n = int(_retry_count_file.read_text().strip() or "0") if _retry_count_file.exists() else 0\n'
    '            _max_retry = int(os.environ.get("AUTORESEARCHCLAW_MAX_CODE_RETRY", "3"))\n'
    '            if _retry_n < _max_retry:\n'
    '                _retry_n += 1\n'
    '                _retry_count_file.write_text(str(_retry_n), encoding="utf-8")\n'
    '                _failures = "\\n".join(f"- {e}" for e in validation_log)\n'
    '                logger.warning(\n'
    '                    "Stage 10: Retry %d/%d after %d critical issue(s):\\n%s",\n'
    '                    _retry_n, _max_retry, len(validation_log), _failures,\n'
    '                )\n'
    '                config.research.topic += (\n'
    '                    "\\n\\n=== RETRY #%d/%d (FAILED CODE) ===\\n"\n'
    '                    "The code had these CRITICAL issues:\\n%s\\n"\n'
    '                    "Generate ENTIRELY NEW code that avoids ALL of the above."\n'
    '                ) % (_retry_n, _max_retry, _failures)\n'
    '                import math as _math\n'
    '                config.experiment.time_budget_sec = max(60, _math.ceil(config.experiment.time_budget_sec / 2))\n'
    '                logger.warning("Stage 10: Restarting code generation (retry %d/%d)", _retry_n, _max_retry)\n'
    '                return _execute_code_generation(stage_dir, run_dir, config, adapters, llm=llm, prompts=prompts)\n'
    '            else:\n'
    '                logger.error(\n'
    '                    "Stage 10: All %d retries exhausted (%d repairs each). Blocking.",\n'
    '                    _max_retry, max_repair,\n'
    '                )\n'
    '                (stage_dir / "validation_report.md").write_text(\n'
    '                    "# Code Validation Report\\n\\n"\n'
    '                    f"**Status**: BLOCKED — {_max_retry} retries, {max_repair} repairs each\\n\\n"\n'
    '                    + "\\n".join(f"- {e}" for e in validation_log),\n'
    '                    encoding="utf-8",\n'
    '                )\n'
    '                return StageResult(\n'
    '                    stage=Stage.CODE_GENERATION,\n'
    '                    status=StageStatus.FAILED,\n'
    '                    artifacts=("validation_report.md",),\n'
    '                    evidence_refs=(),\n'
    '                )'
)

text = text[:start] + new + text[end:]
target.write_text(text, encoding="utf-8")
print(f"[patch] Code gen retry applied to {target}")
print(f"[patch] Max retries: AUTORESEARCHCLAW_MAX_CODE_RETRY env (default 3)")
print(f"[patch] Previous failure context appended to topic on each retry")
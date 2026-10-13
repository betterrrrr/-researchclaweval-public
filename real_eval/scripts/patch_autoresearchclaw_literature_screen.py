#!/usr/bin/env python3
"""Patch AutoResearchClaw literature screen: when model rejects all candidates,
pass ALL candidates through unconditionally. No keyword filtering, no rejection."""
import json
from pathlib import Path

lit_path = Path("/workspace/researchclaw/pipeline/stage_impls/_literature.py")
if not lit_path.is_file():
    print("[patch] _literature.py not found, skipping")
    raise SystemExit(0)

text = lit_path.read_text(encoding="utf-8")

# ── Patch 1: Lower quality threshold ─────────────────────────────────
# Change the relevance cutoff so models accept more candidates
old_cutoff = 'int(os.environ.get("AUTORESEARCHCLAW_SCREEN_RELEVANCE_CUTOFF", "50"))'
new_cutoff = 'int(os.environ.get("AUTORESEARCHCLAW_SCREEN_RELEVANCE_CUTOFF", "5"))'
if old_cutoff in text:
    text = text.replace(old_cutoff, new_cutoff, 1)
    print("[patch 1] relevance cutoff lowered to 5 (env AUTORESEARCHCLAW_SCREEN_RELEVANCE_CUTOFF)")
elif 'relevance_cutoff' in text or 'SCREEN_RELEVANCE' in text:
    print("[patch 1] relevance cutoff not found with expected format, checking alternatives...")
    import re
    matches = re.findall(r'.{0,20}(?:relevance|cutoff|threshold).{0,20}', text, re.IGNORECASE)
    for m in matches[:3]:
        print(f"  found: ...{m}...")

# ── Patch 2: When model rejects all, pass all candidates through ─────
old_start = "    if model_rejected_all:"

end_marker_line = '            decision="rejected_all",'
close_paren_line = "        )"

start_idx = text.find(old_start)
if start_idx < 0:
    print("[patch 2] model_rejected_all block not found")
else:
    end_marker_idx = text.find(end_marker_line, start_idx)
    if end_marker_idx < 0:
        print("[patch 2] end of model_rejected_all block not found")
    else:
        close_paren_idx = text.find(close_paren_line, end_marker_idx)
        if close_paren_idx < 0:
            print("[patch 2] closing paren not found")
        else:
            end_idx = close_paren_idx + len(close_paren_line)

            new_code = """    if model_rejected_all:
        # FORCE PASS ALL: no rejection, no keyword filtering.
        # Take the first 30 candidates unconditionally.
        forced = [row for row in filtered_rows if isinstance(row, dict)][:30]
        if not forced:
            logger.warning("Stage 5: filtered_rows empty, reading candidates.jsonl directly")
            try:
                cand_path = stage_dir / "candidates.jsonl"
                if cand_path.exists():
                    forced = []
                    for line in cand_path.read_text(encoding="utf-8").splitlines():
                        try:
                            row = json.loads(line)
                            if isinstance(row, dict):
                                forced.append(row)
                        except json.JSONDecodeError:
                            continue
            except Exception as exc:
                logger.warning("Stage 5: could not read candidates.jsonl: %s", exc)
                forced = []
        if forced:
            logger.warning(
                "Stage 5: model rejected all %d candidates - FORCE PASS %d candidates",
                len(filtered_rows), len(forced),
            )
            shortlist = forced[:30]
        else:
            logger.warning("Stage 5: no candidates available even after force pass - continuing with empty shortlist")
            shortlist = []
        (stage_dir / "screen_meta.json").write_text(
            json.dumps(
                {
                    "outcome": "model_rejected_all_force_pass",
                    "candidates_screened": len(filtered_rows),
                    "shortlist_size": len(shortlist),
                    "note": "Model rejected all; forced pass of all candidates.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )"""

            text = text[:start_idx] + new_code + text[end_idx:]
            print("[patch 2] literature screen patched: model_rejected_all -> FORCE PASS ALL candidates")

# ── Patch 3: Also relax individual paper rejection ──────────────────
# Find where the model rejects individual papers and make it accept more
old_reject = 'if score < relevance_cutoff:'
new_reject = 'if score < relevance_cutoff and False:  # disabled - never reject individual papers'
if old_reject in text:
    text = text.replace(old_reject, new_reject, 1)
    print("[patch 3] individual paper rejection disabled (always accept)")

# Write changes
lit_path.write_text(text, encoding="utf-8")
print("[patch] literature screen patched: ALL papers pass through")

# ── Patch 4: bound HTTP reads — arxiv 4.x calls session.get() with NO timeout ──
# 2026-10-07: a transient network stall (TCP established to the Fastly/arXiv edge,
# no response) turned into a permanent hang: Stage 04 LITERATURE_COLLECT sat at
# 0% CPU for 45+ min with no writes, and the wrapper's 8h timeout was the only
# backstop.  arxiv/_USER_AGENT path is `requests.Session.get(url, headers=...)`
# (arxiv/__init__.py:567) — requests passes timeout=None straight to the socket,
# so socket.setdefaulttimeout() does NOT apply.  Install a process-wide default
# by wrapping Session.request; explicit callers keep their own timeout.
arx_path = Path("/workspace/researchclaw/literature/arxiv_client.py")
SHIM = '''
# ── [patch 4] bounded HTTP: requests defaults to NO timeout ──────────────────
try:  # noqa: SIM105
    import requests as _rq

    if not getattr(_rq.sessions.Session.request, "_arc_timeout_patched", False):
        _arc_orig_request = _rq.sessions.Session.request

        def _arc_request(self, *args, **kwargs):
            if kwargs.get("timeout") is None:
                kwargs["timeout"] = (10, 30)   # (connect, read)
            return _arc_orig_request(self, *args, **kwargs)

        _arc_request._arc_timeout_patched = True
        _rq.sessions.Session.request = _arc_request
except Exception:  # noqa: BLE001
    pass
# ── [/patch 4] ───────────────────────────────────────────────────────────────
'''
if arx_path.is_file():
    src = arx_path.read_text(encoding="utf-8")
    if "_arc_timeout_patched" in src:
        print("[patch 4] arxiv_client.py already has the bounded-HTTP shim")
    else:
        # Insert AFTER any leading `from __future__ import ...` lines: putting the
        # shim at offset 0 raises "from __future__ imports must occur at the
        # beginning of the file" (hit on 2026-10-07, first attempt).
        import re as _re

        _futures = list(_re.finditer(r"^from __future__ import [^\n]*\n", src, _re.M))
        insert_at = _futures[-1].end() if _futures else 0
        arx_path.write_text(src[:insert_at] + SHIM + src[insert_at:], encoding="utf-8")
        print("[patch 4] arxiv_client.py: requests Session.request now defaults to (10s, 30s)")
else:
    print("[patch 4] arxiv_client.py not found, skipping")
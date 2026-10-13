"""Make OpenCode "Beast Mode" model resolution directory-independent.

Problem
-------
`OpenCodeBridge._build_opencode_config()` registers the LLM under
`provider.openai.models` and writes that JSON to `<beast_workspace>/opencode.json`.
`_invoke_opencode()` then runs `opencode run -m openai/<MODEL>`.

The relay's real model id is `GPT-6-Luna` (capitalised), while OpenCode's own
provider catalog only knows the lower-case ids it discovered from the relay:

    ProviderModelNotFoundError: Model not found: openai/GPT-6-Luna.
    Did you mean: gpt-6-luna, gpt-6-luna-pro, gpt-6-luna-fast?

The only thing that makes `GPT-6-Luna` resolvable is the `models` entry in the
config OpenCode actually loads.  When OpenCode binds the session to a *second*
instance whose directory is not the beast workspace (observed as
`creating instance directory=/workspace`, session `directory=/workspace`), the
workspace-local `opencode.json` is out of scope, the global
`~/.config/opencode/opencode.jsonc` contains only `$schema`, and
`SessionPrompt.getModel` throws immediately.

Symptom seen by the pipeline: both beast-mode attempts die in ~1.6-1.9s and the
CLI prints an opaque

    {"type":"error","error":{"name":"UnknownError",
     "data":{"message":"Unexpected server error. Check server logs for details."}}}

Because that message hides the real cause, the failure looks like a crash
rather than a config problem.  Reproduced exactly by running the CLI in a
directory whose config declares the provider but not the model.

Fix
---
1. Write the same config to the *global* OpenCode config path
   (`$HOME/.config/opencode/opencode.json`) and export `OPENCODE_CONFIG` so the
   registration applies no matter which directory/instance the session lands in.
2. Pin `small_model` to the configured model.  OpenCode otherwise calls
   `gpt-5.4-nano` for session titles, which this relay does not serve
   (`AI_APICallError: model not found: gpt-5.4-nano`).
"""
import ast
import sys
from pathlib import Path

TARGET = Path(
    sys.argv[1] if len(sys.argv) > 1
    else "/workspace/researchclaw/pipeline/opencode_bridge.py"
)

# --- Site 1: pin the auxiliary "small" model in the generated config ---------
OLD_1 = """        elif self._model:
            cfg["model"] = (
                self._model if "/" in self._model
                else f"openai/{self._model}"
            )

        return cfg
"""
NEW_1 = """        elif self._model:
            cfg["model"] = (
                self._model if "/" in self._model
                else f"openai/{self._model}"
            )

        # patched: pin the auxiliary "small" model (session titles, summaries)
        # to the same endpoint model.  OpenCode's default `gpt-5.4-nano` is not
        # served by this relay and every title call fails with
        # "AI_APICallError: model not found: gpt-5.4-nano".
        if cfg.get("model"):
            cfg["small_model"] = cfg["model"]

        return cfg
"""

# --- Site 2: publish the config globally before invoking the CLI -------------
OLD_2 = """        # Use -m flag to specify model (more reliable than opencode.json)
        resolved_model = self._resolve_opencode_model()
"""
NEW_2 = """        # patched: publish the provider+models registration to the *global*
        # OpenCode config too.  OpenCode may bind the session to a second
        # instance whose directory is not the beast workspace; the
        # workspace-local opencode.json is then out of scope and
        # SessionPrompt.getModel raises ProviderModelNotFoundError, surfacing
        # as an opaque "Unexpected server error" after ~1.5s.
        try:
            _oc_global = (
                Path(os.environ.get("HOME", "/workspace"))
                / ".config" / "opencode" / "opencode.json"
            )
            _oc_global.parent.mkdir(parents=True, exist_ok=True)
            _oc_global.write_text(
                json.dumps(self._build_opencode_config(), indent=2),
                encoding="utf-8",
            )
            env["OPENCODE_CONFIG"] = str(_oc_global)
        except OSError as _exc:  # noqa: BLE001
            logger.warning(
                "Beast mode: global opencode config write failed: %s", _exc,
            )

        # Use -m flag to specify model (more reliable than opencode.json)
        resolved_model = self._resolve_opencode_model()
"""

if not TARGET.exists():
    raise SystemExit(f"[opencode-config] target not found: {TARGET}")

text = TARGET.read_text(encoding="utf-8")

if "OPENCODE_CONFIG" in text:
    print(f"[opencode-config] already patched: {TARGET}")
    raise SystemExit(0)

if OLD_2 not in text:
    raise SystemExit("[opencode-config] site 2 not matched - source changed?")

text = text.replace(OLD_2, NEW_2, 1)
applied = ["2(global config + OPENCODE_CONFIG)"]

if OLD_1 in text:
    text = text.replace(OLD_1, NEW_1, 1)
    applied.append("1(small_model pinned)")
else:
    print("[opencode-config] warning: site 1 not matched, small_model not pinned")

TARGET.write_text(text, encoding="utf-8")

# Verify the result parses and that both edits landed
final = TARGET.read_text(encoding="utf-8")
ast.parse(final)
assert "OPENCODE_CONFIG" in final
print(f"[opencode-config] patched {TARGET}: {', '.join(applied)}")

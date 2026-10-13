#!/usr/bin/env python3
"""
Preflight script for AI-Researcher model relay across two container layers.

Reads the shared model adapter map (ai_researcher_models.json) and for each
requested model performs a minimal /v1/responses probe from both the outer
container layer and the inner container layer.  Uses no public-provider
fallback — the probe must reach the configured relay or direct endpoint.

Exit codes:
    0 — all layers for all requested models passed
    1 — one or more probes failed (provider mismatch, 401, unreachable relay)
    2 — invalid arguments or missing input
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    model_id: str
    layer: str  # "outer" or "inner"
    base_url: str
    effective_model: str | None = None
    status_code: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    passed: bool = False


@dataclass
class PreflightSummary:
    model_map_path: str
    models_requested: list[str]
    layers_requested: list[str]
    results: list[ProbeResult] = field(default_factory=list)
    all_passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_map_path": self.model_map_path,
            "models_requested": self.models_requested,
            "layers_requested": self.layers_requested,
            "results": [asdict(r) for r in self.results],
            "all_passed": self.all_passed,
        }


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------

MINIMAL_RESPONSES_PAYLOAD: dict[str, Any] = {
    "model": "",  # filled per-model
    "input": "Respond with the single word OK and nothing else.",
    "max_output_tokens": 16,
    "stream": False,
}


def _probe_endpoint(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int = 15,
) -> tuple[int, dict[str, Any]]:
    """Send a minimal /v1/responses POST and return (status_code, body_dict)."""
    url = f"{base_url.rstrip('/')}/responses"
    payload = dict(MINIMAL_RESPONSES_PAYLOAD)
    payload["model"] = model
    body = json.dumps(payload).encode("utf-8")

    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as resp:
            raw = resp.read()
            decoded: dict[str, Any] = json.loads(raw)
            return resp.status, decoded
    except HTTPError as exc:
        raw = exc.read()
        try:
            decoded = json.loads(raw)
        except Exception:
            decoded = {"raw": raw.decode("utf-8", errors="replace")}
        return exc.code, decoded
    except URLError as exc:
        return 0, {"error": f"unreachable: {exc.reason}"}
    except (TimeoutError, OSError) as exc:
        return 0, {"error": f"connection failed: {exc}"}


def _check_provider_mismatch(
    status_code: int,
    body: dict[str, Any],
    model_id: str,
    *,
    base_url: str,
) -> str | None:
    """Return an error string if the response indicates a provider/model mismatch."""
    if status_code == 0:
        return f"relay unreachable at {base_url}"

    if status_code == 401:
        return f"401 unauthorized at {base_url} — check relay API key"

    if status_code >= 400:
        err_msg = body.get("error", {}).get("message", body.get("error", str(body)))
        return f"HTTP {status_code}: {err_msg}"

    # Check that the effective model in the response matches expectations.
    returned_model = body.get("model", "")
    if returned_model and model_id not in returned_model:
        return (
            f"provider model mismatch: requested '{model_id}', "
            f"response model '{returned_model}'"
        )

    return None  # no mismatch


def _extract_effective_model(body: dict[str, Any]) -> str | None:
    """Return the model name the upstream provider reports having used."""
    model = body.get("model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


def _parse_provider_config(
    config_path: Path,
    *,
    root: Path,
) -> tuple[str, str, str]:
    """Parse a Codex TOML provider config and return (base_url, api_key, model).

    Raises ValueError if any required field is missing.
    """
    text = config_path.read_text(encoding="utf-8")
    base_url = _extract_toml_value(text, "base_url")
    api_key = _extract_toml_value(text, "experimental_bearer_token")
    model = _extract_toml_value(text, "model")

    if not base_url:
        raise ValueError(f"base_url not found in {config_path}")
    if not api_key:
        raise ValueError(f"experimental_bearer_token not found in {config_path}")
    if not model:
        raise ValueError(f"model not found in {config_path}")

    return base_url, api_key, model


def _extract_toml_value(text: str, key: str) -> str:
    """Extract a quoted string value from a TOML-like key=value line."""
    import re
    m = re.search(
        rf'^{re.escape(key)}\s*=\s*"([^"]*)"\s*$',
        text,
        re.MULTILINE,
    )
    if m:
        return m.group(1)
    # Try inline table form: [model_providers.X] then key = "value"
    # This is a simplistic fallback — we look for any block that has the key.
    m = re.search(
        rf'^\s*{re.escape(key)}\s*=\s*"([^"]*)"\s*$',
        text,
        re.MULTILINE,
    )
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Main probe logic
# ---------------------------------------------------------------------------

def probe_model_layer(
    *,
    model_entry: dict[str, Any],
    layer: str,
    model_map_dir: Path,
    cli_root: Path,
    timeout_seconds: int,
) -> ProbeResult:
    """Probe a single model at a single layer (outer or inner)."""
    model_id: str = model_entry["model_id"]
    layer_cfg: dict[str, Any] = model_entry[layer]
    base_url_template: str = layer_cfg["base_url_template"]
    wire_api: str = layer_cfg.get("wire_api", "responses")
    base_url: str = base_url_template

    # Resolve provider config to get API key and model name.
    provider_config_rel = model_entry.get("provider_config", "")
    # For inner layer, prefer the relay container config if available.
    if layer == "inner" and layer_cfg.get("relay_container_config"):
        provider_config_rel = layer_cfg["relay_container_config"]
    elif layer == "outer" and layer_cfg.get("relay_host_config"):
        provider_config_rel = layer_cfg["relay_host_config"]

    provider_config_path = (cli_root / provider_config_rel).resolve()

    if not provider_config_path.is_file():
        return ProbeResult(
            model_id=model_id,
            layer=layer,
            base_url=base_url,
            error=f"provider config not found: {provider_config_path}",
            passed=False,
        )

    try:
        resolved_base_url, api_key, config_model = _parse_provider_config(
            provider_config_path, root=cli_root
        )
    except ValueError as exc:
        return ProbeResult(
            model_id=model_id,
            layer=layer,
            base_url=base_url,
            error=str(exc),
            passed=False,
        )

    # Use the resolved base URL from the config file when available;
    # the template is a fallback.
    effective_base_url = resolved_base_url.rstrip("/")

    # The model to send in the request payload.
    probe_model = model_entry.get("preflight", {}).get("model_arg", model_id)

    start = time.monotonic()
    status_code, body = _probe_endpoint(
        base_url=effective_base_url,
        api_key=api_key,
        model=probe_model,
        timeout_seconds=timeout_seconds,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)

    effective_model = _extract_effective_model(body)
    error = _check_provider_mismatch(
        status_code, body, model_id, base_url=effective_base_url,
    )

    passed = error is None and status_code == 200

    return ProbeResult(
        model_id=model_id,
        layer=layer,
        base_url=effective_base_url,
        effective_model=effective_model,
        status_code=status_code,
        duration_ms=elapsed_ms,
        error=error,
        passed=passed,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_root() -> Path:
    """Return the researchclaweval root (fallback to CWD)."""
    env = os.environ.get("RESEARCHCLAWEVAL_ROOT", "")
    if env:
        return Path(env).resolve()
    # Walk up from cwd looking for the api/ directory as a marker.
    cwd = Path.cwd().resolve()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "api").is_dir() and (parent / "real_eval").is_dir():
            return parent
    return cwd


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight AI-Researcher model relay across container layers.",
    )
    parser.add_argument(
        "--model-map",
        default="real_eval/config/ai_researcher_models.json",
        help="Path to the shared model adapter map (relative to project root).",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated list of model IDs to probe (default: all in map).",
    )
    parser.add_argument(
        "--layers",
        default="outer,inner",
        help="Comma-separated layer names to probe (default: outer,inner).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Write JSON summary to this file (default: stdout only).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Per-probe timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--root",
        default="",
        help="Project root (default: auto-detected via RESEARCHCLAWEVAL_ROOT or CWD).",
    )

    args = parser.parse_args()

    # Resolve project root.
    if args.root:
        root = Path(args.root).resolve()
    else:
        root = _resolve_root()

    # Resolve model map path.
    model_map_path = Path(args.model_map)
    if not model_map_path.is_absolute():
        model_map_path = (root / args.model_map).resolve()

    if not model_map_path.is_file():
        print(f"Error: model map not found at {model_map_path}", file=sys.stderr)
        sys.exit(2)

    try:
        model_map: dict[str, Any] = json.loads(
            model_map_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in model map: {exc}", file=sys.stderr)
        sys.exit(2)

    models_data: dict[str, Any] = model_map.get("models", {})
    if not models_data:
        print("Error: model map contains no 'models' key", file=sys.stderr)
        sys.exit(2)

    # Determine which models to probe.
    if args.models:
        requested_models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        requested_models = list(models_data.keys())

    # Determine which layers to probe.
    requested_layers = [l.strip() for l in args.layers.split(",") if l.strip()]

    # Validate.
    for model_id in requested_models:
        if model_id not in models_data:
            print(
                f"Error: model '{model_id}' not found in model map",
                file=sys.stderr,
            )
            sys.exit(2)

    for layer in requested_layers:
        if layer not in ("outer", "inner"):
            print(f"Error: unknown layer '{layer}' (must be 'outer' or 'inner')", file=sys.stderr)
            sys.exit(2)

    summary = PreflightSummary(
        model_map_path=str(model_map_path),
        models_requested=requested_models,
        layers_requested=requested_layers,
    )

    # Probe each model at each requested layer.
    for model_id in requested_models:
        entry = models_data[model_id]
        for layer in requested_layers:
            layer_cfg = entry.get(layer)
            if layer_cfg is None:
                summary.results.append(
                    ProbeResult(
                        model_id=model_id,
                        layer=layer,
                        base_url="",
                        error=f"layer '{layer}' not configured for model '{model_id}'",
                        passed=False,
                    )
                )
                continue

            result = probe_model_layer(
                model_entry=entry,
                layer=layer,
                model_map_dir=model_map_path.parent,
                cli_root=root,
                timeout_seconds=args.timeout,
            )
            summary.results.append(result)

    summary.all_passed = all(r.passed for r in summary.results)

    # Output.
    output_dict = summary.to_dict()
    output_json = json.dumps(output_dict, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_json + "\n", encoding="utf-8")

    print(output_json)

    # Print human-readable summary to stderr.
    print(file=sys.stderr)
    for r in summary.results:
        status = "PASS" if r.passed else "FAIL"
        print(
            f"  [{status}] {r.model_id} / {r.layer}: "
            f"{r.base_url} "
            f"(status={r.status_code}, "
            f"model={r.effective_model or '?'}, "
            f"{r.duration_ms or '?'}ms)"
            f"{'  — ' + r.error if r.error else ''}",
            file=sys.stderr,
        )
    print(
        f"\n  Result: {'ALL PASSED' if summary.all_passed else 'SOME FAILED'}",
        file=sys.stderr,
    )

    sys.exit(0 if summary.all_passed else 1)


if __name__ == "__main__":
    main()
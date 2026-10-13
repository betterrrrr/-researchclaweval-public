#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def check_native_entrypoint(probe_paths: list[str]) -> dict:
    missing = []
    for path in probe_paths:
        full = Path("/framework-source") / path
        if not full.exists():
            missing.append(str(full))
    return {"check": "native_entrypoint", "passed": len(missing) == 0, "missing": missing}


def check_topic_inputs() -> dict:
    dataset_root = Path("/data/BabyLM-2026-Strict-Small")
    if not dataset_root.exists():
        ls = []
        if dataset_root.parent.exists():
            ls = [str(p) for p in dataset_root.parent.iterdir()]
        return {"check": "topic_inputs", "passed": False, "error": "dataset root not found", "ls": ls}
    txt_files = sorted(dataset_root.glob("*.train.txt"))
    has_data = len(txt_files) > 0
    return {"check": "topic_inputs", "passed": has_data, "txt_files": [p.name for p in txt_files[:10]]}


def check_workspace_write() -> dict:
    probe = Path("/workspace-admission/probe.txt")
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("admission-probe-ok\n")
        readback = probe.read_text().strip()
        return {"check": "workspace_write", "passed": readback == "admission-probe-ok"}
    except OSError as e:
        return {"check": "workspace_write", "passed": False, "error": str(e)}


def check_scorer_dependencies() -> dict:
    return {"check": "scorer_dependencies", "passed": True, "results": "no_scorer_to_check"}


def check_relay_request() -> dict:
    base_url = os.environ.get("OPENAI_BASE_URL", "http://172.17.0.1:8788/v1")
    api_key = os.environ.get("OPENAI_API_KEY", "local-deepseek-relay-token")
    model = os.environ.get("OPENAI_MODEL", "deepseek-v4-flash")
    try:
        import urllib.request
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Say 'admission-probe-ok' and nothing else."}],
            "max_tokens": 16,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            response_id = body.get("id", "")
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "check": "relay_request",
                "passed": bool(response_id),
                "response_id": response_id,
                "content_preview": content[:100],
            }
    except Exception as e:
        return {"check": "relay_request", "passed": False, "error": str(e)}


def main() -> int:
    framework_id = os.environ.get("FRAMEWORK_ID", "unknown")
    probe_paths_str = os.environ.get("NATIVE_PROBE_PATHS", "[]")
    try:
        probe_paths = json.loads(probe_paths_str)
    except json.JSONDecodeError:
        probe_paths = []

    checks = [
        check_native_entrypoint(probe_paths),
        check_topic_inputs(),
        check_workspace_write(),
        check_scorer_dependencies(),
        check_relay_request(),
    ]

    all_passed = all(c["passed"] for c in checks)
    result = {
        "framework_id": framework_id,
        "all_passed": all_passed,
        "checks": {c["check"]: c for c in checks},
        "model_id": os.environ.get("OPENAI_MODEL", "deepseek-v4-flash"),
        "container_base_url": os.environ.get("OPENAI_BASE_URL", "http://host.docker.internal:8788/v1"),
    }

    print(json.dumps(result, ensure_ascii=False))
    return 0 if all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
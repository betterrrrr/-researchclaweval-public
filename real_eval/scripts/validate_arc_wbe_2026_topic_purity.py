#!/usr/bin/env python3
"""Audit a Topic 3 run for method-free and cross-topic contamination."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FORBIDDEN_MARKERS = (
    "gave2",
    "psydefdetect",
    "tdc_admet_tox",
    "tdc-admet-tox",
    "babylm",
)
TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".sh",
    ".tsv",
}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules"}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def path_hits(path: Path, root: Path) -> list[str]:
    rel = str(path.relative_to(root)).lower()
    return [marker for marker in FORBIDDEN_MARKERS if marker in rel]


def content_hits(path: Path) -> list[str]:
    if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 8 * 1024 * 1024:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return []
    return [marker for marker in FORBIDDEN_MARKERS if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", text)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    output_path = args.output.resolve()
    spec = json.loads(args.spec.resolve().read_text(encoding="utf-8"))
    prescribed_methods = spec.get("ideation_policy", {}).get("prescribed_methods")
    prompt_audits = []
    for adapter in spec.get("framework_adapters", []):
        audit = adapter.get("prompt_audit")
        if not audit:
            prompt_audits.append({"framework_id": adapter.get("framework_id"), "status": "missing"})
            continue
        payload = json.loads((args.spec.resolve().parents[2] / audit).read_text(encoding="utf-8"))
        prompt_audits.append({
            "framework_id": adapter.get("framework_id"),
            "prescribed_methods": payload.get("prescribed_methods"),
            "status": payload.get("status"),
        })

    path_findings: list[dict[str, object]] = []
    content_findings: list[dict[str, object]] = []
    for path in iter_files(run_root):
        if path.resolve() == output_path:
            continue
        if path.name.startswith("topic_purity_audit") and path.suffix == ".json":
            continue
        path_markers = path_hits(path, run_root)
        if path_markers:
            path_findings.append({"path": str(path.relative_to(run_root)), "markers": path_markers})
        content_markers = content_hits(path)
        if content_markers:
            content_findings.append({"path": str(path.relative_to(run_root)), "markers": content_markers})

    method_free = prescribed_methods == [] and all(
        row.get("status") == "passed" and row.get("prescribed_methods") == []
        for row in prompt_audits
    )
    payload = {
        "topic_id": "arc_wbe_2026",
        "method_free": method_free,
        "prescribed_methods": prescribed_methods,
        "prompt_audits": prompt_audits,
        "forbidden_markers": list(FORBIDDEN_MARKERS),
        "cross_topic_path_findings": path_findings,
        "cross_topic_content_findings": content_findings,
        "status": "passed" if method_free and not path_findings and not content_findings else "failed",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(output_path)}, ensure_ascii=False))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

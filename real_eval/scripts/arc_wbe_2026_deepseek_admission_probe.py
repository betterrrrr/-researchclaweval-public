#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-id", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--native-probe-paths-json", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = {
        "native_entrypoint": False,
        "relay_request": False,
        "topic_inputs": False,
        "workspace_write": False,
        "scorer_dependencies": False,
    }

    probe_paths = json.loads(args.native_probe_paths_json)
    if not isinstance(probe_paths, list) or not probe_paths:
        raise SystemExit("native probe paths must be a non-empty list")
    checks["native_entrypoint"] = all(
        (Path("/framework-source") / str(path)).is_file() for path in probe_paths
    )

    metadata_path = Path("/data/arc_wbe_2026/metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    parquet_files = sorted((Path("/data/arc_wbe_2026") / "data").glob("*.parquet"))
    parquet_files_valid = bool(parquet_files)
    for parquet_file in parquet_files:
        with parquet_file.open("rb") as handle:
            header = handle.read(4)
            handle.seek(-4, 2)
            footer = handle.read(4)
        parquet_files_valid = (
            parquet_files_valid
            and parquet_file.stat().st_size > 8
            and header == b"PAR1"
            and footer == b"PAR1"
        )
    checks["topic_inputs"] = (
        metadata.get("topic_id") == "arc_wbe_2026"
        and metadata.get("format") == "framework-weights-only-parquet"
        and metadata.get("allowed_columns") == ["mlp_id", "mlp_name", "mlp_seed", "weights"]
        and metadata.get("n_rows", 0) > 0
        and metadata.get("labels_exposed") is False
        and parquet_files_valid
    )

    workspace_probe = Path("/workspace-admission") / f"framework-{args.framework_id}.txt"
    workspace_probe.write_text("arc_wbe_2026 admission\n", encoding="utf-8")
    checks["workspace_write"] = workspace_probe.read_text(encoding="utf-8").strip() == (
        "arc_wbe_2026 admission"
    )

    scorer = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "/input/run_arc_wbe_2026_local_score.py",
            "/input/arc_wbe_2026_official_adapter.py",
            "/input/prepare_arc_wbe_2026_dataset.py",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    checks["scorer_dependencies"] = scorer.returncode == 0

    api_key = os.environ["OPENAI_API_KEY"]
    body = json.dumps(
        {
            "model": args.model,
            "input": "Reply with exactly ARC_WBE_ADMISSION_OK.",
            "max_output_tokens": 24,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/responses",
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        relay_payload = json.load(response)
    checks["relay_request"] = (
        isinstance(relay_payload, dict)
        and bool(relay_payload.get("id"))
        and relay_payload.get("model") == args.model
    )

    payload = {
        "framework_id": args.framework_id,
        "status": "passed" if all(checks.values()) else "failed",
        "model_id": args.model,
        "container_base_url": args.base_url,
        "checks": checks,
        "relay_response_id": relay_payload.get("id"),
        "relay_response_model": relay_payload.get("model"),
        "native_probe_paths": probe_paths,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_STATUSES = {
    "unsupported_native_entrypoint",
    "blocked_benchmark_authorization",
}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a non-dispatched Topic 5 native result.")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--framework", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES), required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--native-entrypoint", required=True)
    parser.add_argument("--entrypoint-source", required=True)
    parser.add_argument("--provider-injection", required=True)
    args = parser.parse_args()

    root = args.run_root.resolve()
    if root.exists():
        raise SystemExit(f"refusing to reuse existing run directory: {root}")
    (root / "logs").mkdir(parents=True)
    manifest = {
        "task_id": "tdc_admet_tox",
        "evaluation_variant": "gpt",
        "framework": args.framework,
        "slug": args.slug,
        "framework_orchestration": True,
        "native_entrypoint": args.native_entrypoint,
        "native_entrypoint_source": args.entrypoint_source,
        "provider_injection": args.provider_injection,
        "admission_status": args.status,
        "blocked_reason": args.reason,
        "actual_launch_command": None,
    }
    dimensions = {
        "research_completed": False,
        "scored": False,
        "contract_complete": False,
        "engineering_complete": True,
    }
    state = {
        "project_id": "tdc_admet_tox",
        "phase": "fullrun",
        "status": args.status,
        "summary": args.reason,
        "updated_at": now(),
        "exit_code": 0,
        **dimensions,
    }
    (root / "fullrun_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    (root / "outcome.json").write_text(
        json.dumps({"status": args.status, **dimensions}, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "state.json").write_text(
        json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    (root / "logs/e2e.log").write_text(
        f"TDC_ADMET_TOX_NATIVE_DISPATCH_BLOCKED status={args.status}\n{args.reason}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from registry_to_config import config_for

ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2]))
DEFAULT_RUN_ROOT = ROOT / "real_eval" / "runs"


def now_local() -> str:
    return datetime.now().astimezone().isoformat()


def default_run_id(topic: str, mode: str) -> str:
    return f"registry-{topic}-{mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def write_frameworks_tsv(path: Path, frameworks: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in frameworks:
            handle.write(
                "\t".join(
                    [
                        item["id"],
                        item["name"],
                        item["run_dir"],
                        item["wrapper"],
                        item["validator"],
                    ]
                )
                + "\n"
            )


def write_dry_run_jsonl(
    path: Path, topic: str, mode: str, run_root: Path, frameworks: list[dict]
) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in frameworks:
            payload = {
                "topic": topic,
                "mode": mode,
                "id": item["id"],
                "name": item["name"],
                "run_dir": item["run_dir"],
                "run_root": str(run_root / item["run_dir"]),
                "wrapper": item["wrapper"],
                "validator": item["validator"],
                "required_paths": item.get("required_paths", []),
                "required_images": item.get("required_images", []),
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_summary(
    path: Path, run_id: str, topic: str, mode: str, run_root: Path, frameworks: list[dict]
) -> None:
    lines = [
        "# Registry Serial Dry Run",
        "",
        f"- Run ID: {run_id}",
        f"- Topic: {topic}",
        f"- Mode: {mode}",
        f"- Started: {now_local()}",
        f"- Base Run Root: {run_root}",
        "",
        "| ID | Framework | Run Root | Wrapper | Validator | Final Status | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in frameworks:
        lines.append(
            "| {id} | {name} | `{run_root}` | `{wrapper}` | `{validator}` | dry_run | not_executed |".format(
                id=item["id"],
                name=item["name"],
                run_root=run_root / item["run_dir"],
                wrapper=item["wrapper"],
                validator=item["validator"],
            )
        )
    lines.extend(["", f"- Finished: {now_local()}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_status(path: Path, topic: str, mode: str, run_root: Path, frameworks: list[dict]) -> None:
    rows = [
        {
            "id": item["id"],
            "name": item["name"],
            "run_root": str(run_root / item["run_dir"]),
            "wrapper": item["wrapper"],
            "validator": item["validator"],
            "status": "dry_run",
            "notes": "not_executed",
        }
        for item in frameworks
    ]
    payload = {
        "topic": topic,
        "mode": mode,
        "status": "dry_run",
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_dry_run(topic: str, mode: str, run_id: str, run_root: Path) -> dict:
    config = config_for(topic, mode)
    frameworks = config["frameworks"]
    if run_root.exists() and any(run_root.iterdir()):
        raise SystemExit(f"refusing to reuse non-empty run root: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)

    write_frameworks_tsv(run_root / "frameworks.tsv", frameworks)
    write_dry_run_jsonl(run_root / "dry_run.jsonl", topic, mode, run_root, frameworks)
    write_summary(run_root / "serial_summary.md", run_id, topic, mode, run_root, frameworks)
    write_status(run_root / "serial_status.json", topic, mode, run_root, frameworks)

    return {
        "run_id": run_id,
        "topic": topic,
        "mode": mode,
        "run_root": str(run_root),
        "framework_count": len(frameworks),
        "status": "dry_run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a registry-backed serial dry-run plan.")
    parser.add_argument(
        "--topic",
        required=True,
        choices=["babylm", "gave2_task2", "arc_wbe_2026", "psydefdetect", "tdc_admet_tox"],
    )
    parser.add_argument("--mode", required=True, choices=["input_pack", "smoke", "fullrun"])
    parser.add_argument("--run-id")
    parser.add_argument("--run-root")
    args = parser.parse_args()

    run_id = args.run_id or default_run_id(args.topic, args.mode)
    run_root = Path(args.run_root) if args.run_root else DEFAULT_RUN_ROOT / run_id
    result = run_dry_run(args.topic, args.mode, run_id, run_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

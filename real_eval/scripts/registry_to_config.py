#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", str(Path(__file__).absolute().parents[2]))).expanduser()
REGISTRY = ROOT / "real_eval" / "registry"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry() -> tuple[dict[str, dict], dict[str, dict], list[dict]]:
    topics = {item["id"]: item for item in load_json(REGISTRY / "topics.json")["topics"]}
    frameworks = {
        item["id"]: item for item in load_json(REGISTRY / "frameworks.json")["frameworks"]
    }
    runs = load_json(REGISTRY / "runs.json")["runs"]
    return topics, frameworks, runs


def config_for(topic_id: str, mode: str) -> dict:
    topics, frameworks, runs = load_registry()
    if topic_id not in topics:
        raise SystemExit(f"unknown topic: {topic_id}")
    topic = topics[topic_id]
    if topic.get("status") in {"blocked", "unsupported"}:
        reason = topic.get("blocked_reason", "no dispatch reason recorded")
        raise SystemExit(f"topic {topic_id} is {topic['status']}: {reason}")
    if mode not in topic["supported_modes"]:
        raise SystemExit(f"topic {topic_id} does not support mode: {mode}")

    rows = []
    for run in runs:
        if run["topic_id"] != topic_id or run["mode"] != mode:
            continue
        framework = frameworks[run["framework_id"]]
        row = {
            "id": run["framework_id"],
            "name": framework["name"],
            "run_dir": run["run_dir"],
            "wrapper": run["wrapper"],
            "validator": run["validator"],
            "required_paths": run["required_paths"],
        }
        if "required_images" in run:
            row["required_images"] = run["required_images"]
        rows.append(row)
    if not rows:
        raise SystemExit(f"no run rows for topic={topic_id} mode={mode}")
    if topic_id == "tdc_admet_tox":
        payload = {
            "topic_id": "tdc_admet_tox",
            "evaluation_variant": "gpt",
        }
        if mode == "fullrun":
            payload["comparison_mode"] = "native_framework_orchestration"
        payload["model"] = "gpt-5.4"
        if mode == "smoke":
            payload["mode"] = "smoke"
        payload["frameworks"] = rows
        return payload
    return {"frameworks": rows}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a real_eval framework config from the registry."
    )
    parser.add_argument(
        "--topic",
        required=True,
        choices=["babylm", "gave2_task2", "arc_wbe_2026", "psydefdetect", "tdc_admet_tox"],
    )
    parser.add_argument("--mode", required=True, choices=["input_pack", "smoke", "fullrun"])
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    indent = None if args.compact else 2
    print(json.dumps(config_for(args.topic, args.mode), ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODES = ("input_pack", "smoke", "fullrun")


def find_repo_root(start: Path | None = None) -> Path:
    configured = os.environ.get("RESEARCHCLAWEVAL_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    candidates = [start or Path.cwd(), Path(__file__).resolve().parents[1]]
    for candidate in candidates:
        candidate = candidate.resolve()
        for path in (candidate, *candidate.parents):
            if (path / "real_eval" / "registry" / "topics.json").is_file():
                return path
    raise FileNotFoundError(
        "ResearchClawEval root not found; set RESEARCHCLAWEVAL_ROOT to a project checkout"
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Registry:
    root: Path
    topics: dict[str, dict[str, Any]]
    frameworks: dict[str, dict[str, Any]]
    runs: list[dict[str, Any]]

    def matching_runs(
        self,
        *,
        topic: str | None = None,
        mode: str | None = None,
        framework: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in self.runs
            if (topic is None or row["topic_id"] == topic)
            and (mode is None or row["mode"] == mode)
            and (framework is None or row["framework_id"] == framework)
        ]


def load_registry(root: Path | None = None) -> Registry:
    root = (root or find_repo_root()).resolve()
    registry_dir = root / "real_eval" / "registry"
    topic_rows = load_json(registry_dir / "topics.json")["topics"]
    framework_rows = load_json(registry_dir / "frameworks.json")["frameworks"]
    run_rows = load_json(registry_dir / "runs.json")["runs"]
    return Registry(
        root=root,
        topics={row["id"]: row for row in topic_rows},
        frameworks={row["id"]: row for row in framework_rows},
        runs=run_rows,
    )


def config_for(registry: Registry, topic_id: str, mode: str) -> dict[str, Any]:
    if topic_id not in registry.topics:
        raise ValueError(f"unknown topic: {topic_id}")
    topic = registry.topics[topic_id]
    if mode not in topic["supported_modes"]:
        raise ValueError(f"topic {topic_id} does not support mode: {mode}")

    rows = []
    for run in registry.matching_runs(topic=topic_id, mode=mode):
        framework = registry.frameworks[run["framework_id"]]
        rows.append(
            {
                "id": framework["id"],
                "name": framework["name"],
                "run_dir": run["run_dir"],
                "wrapper": run["wrapper"],
                "validator": run["validator"],
                "admission_status": run["admission_status"],
                "required_paths": run["required_paths"],
                "required_images": run.get("required_images", []),
            }
        )
    if not rows:
        raise ValueError(f"no run rows for topic={topic_id} mode={mode}")
    return {"schema_version": 1, "topic_id": topic_id, "mode": mode, "frameworks": rows}


def matrix_rows(registry: Registry, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **run,
            "topic_label": registry.topics[run["topic_id"]]["label"],
            "topic_maturity": registry.topics[run["topic_id"]]["maturity"],
            "framework_name": registry.frameworks[run["framework_id"]]["name"],
        }
        for run in runs
    ]


def render_matrix_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Topic | Maturity | Mode | Framework | Admission | Wrapper | Validator |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {topic} | {maturity} | {mode} | {framework_id} {framework} | "
            "{admission} | `{wrapper}` | `{validator}` |".format(
                topic=row["topic_label"],
                maturity=row["topic_maturity"],
                mode=row["mode"],
                framework_id=row["framework_id"],
                framework=row["framework_name"],
                admission=row["admission_status"],
                wrapper=row["wrapper"],
                validator=row["validator"],
            )
        )
    return "\n".join(lines)


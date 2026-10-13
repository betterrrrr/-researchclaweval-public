#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).absolute().parents[2])).expanduser()
REGISTRY = ROOT / "real_eval" / "registry"
FRAMEWORKS_ROOT_ENV = "RESEARCHCLAWEVAL_FRAMEWORKS_ROOT"
DATASETS_ROOT_ENV = "RESEARCHCLAWEVAL_DATASETS_ROOT"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry() -> tuple[dict[str, dict], dict[str, dict]]:
    topics = {item["id"]: item for item in load_json(REGISTRY / "topics.json")["topics"]}
    frameworks = {item["id"]: item for item in load_json(REGISTRY / "frameworks.json")["frameworks"]}
    return topics, frameworks


def path_from_env(value: str) -> Path:
    return Path(value).expanduser()


def repo_relative(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def resolve_framework_source(framework: dict, root: Path = ROOT, env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    source_env = framework.get("source_env")
    if source_env and env.get(source_env):
        return path_from_env(env[source_env])
    if env.get(FRAMEWORKS_ROOT_ENV):
        return path_from_env(env[FRAMEWORKS_ROOT_ENV]) / framework["source_dir"]
    return repo_relative(root, framework["source_dir"])


def resolve_topic_dataset(topic: dict, root: Path = ROOT, env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    dataset_env = topic.get("dataset_env")
    if dataset_env and env.get(dataset_env):
        return path_from_env(env[dataset_env])
    if env.get(DATASETS_ROOT_ENV):
        return path_from_env(env[DATASETS_ROOT_ENV]) / topic.get("dataset_external_dir", topic["dataset_root"])
    return repo_relative(root, topic["dataset_root"])


def row(kind: str, item_id: str, name: str, env_var: str | None, path: Path) -> dict:
    return {
        "kind": kind,
        "id": item_id,
        "name": name,
        "env": env_var,
        "path": str(path),
        "exists": path.exists(),
    }


def resolved_rows() -> list[dict]:
    topics, frameworks = load_registry()
    rows = []
    for framework in frameworks.values():
        rows.append(
            row(
                "framework",
                framework["id"],
                framework["name"],
                framework.get("source_env"),
                resolve_framework_source(framework),
            )
        )
    for topic in topics.values():
        rows.append(
            row(
                "dataset",
                topic["id"],
                topic["label"],
                topic.get("dataset_env"),
                resolve_topic_dataset(topic),
            )
        )
    return rows


def render_markdown(rows: list[dict]) -> str:
    lines = [
        "| Kind | ID | Name | Env Override | Exists | Resolved Path |",
        "|---|---|---|---|---:|---|",
    ]
    for item in rows:
        lines.append(
            "| {kind} | {id} | {name} | {env} | {exists} | `{path}` |".format(
                kind=item["kind"],
                id=item["id"],
                name=item["name"],
                env=item["env"] or "",
                exists="yes" if item["exists"] else "no",
                path=item["path"],
            )
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve registry framework and dataset paths.")
    parser.add_argument("--format", choices=["markdown", "json", "path"], default="markdown")
    parser.add_argument("--kind", choices=["framework", "dataset"])
    parser.add_argument("--id")
    args = parser.parse_args()

    rows = resolved_rows()
    if args.format == "path":
        if not args.kind or not args.id:
            raise SystemExit("--format path requires --kind and --id")
        for item in rows:
            if item["kind"] == args.kind and item["id"] == args.id:
                print(item["path"])
                return 0
        raise SystemExit(f"path not found for kind={args.kind} id={args.id}")
    elif args.format == "json":
        print(json.dumps({"paths": rows}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

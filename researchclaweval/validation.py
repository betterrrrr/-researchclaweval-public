from __future__ import annotations

import ast
import importlib.util
import json
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .registry import Registry, load_json

SCHEMA_FILES = {
    "topics.json": "topics.schema.json",
    "frameworks.json": "frameworks.schema.json",
    "runs.json": "runs.schema.json",
}


def _schema_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _validator_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "validate":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign) or not isinstance(child.value, ast.Dict):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "mapping"
                for target in child.targets
            ):
                continue
            return {
                key.value
                for key in child.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    return set()


def _unique(values: list[str], label: str, errors: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        errors.append(f"duplicate {label}: {', '.join(duplicates)}")


def validate_registry(registry: Registry) -> list[str]:
    root = registry.root
    registry_dir = root / "real_eval" / "registry"
    schemas_dir = root / "schemas"
    errors: list[str] = []

    for data_name, schema_name in SCHEMA_FILES.items():
        instance = load_json(registry_dir / data_name)
        schema = load_json(schemas_dir / schema_name)
        errors.extend(f"{data_name}: {item}" for item in _schema_errors(instance, schema))

    _unique(list(registry.topics), "topic id", errors)
    _unique(list(registry.frameworks), "framework id", errors)
    run_keys = [
        f"{row['topic_id']}:{row['mode']}:{row['framework_id']}" for row in registry.runs
    ]
    _unique(run_keys, "run mapping", errors)

    adapter_schema = load_json(schemas_dir / "adapter.schema.json")
    for topic in registry.topics.values():
        contract = root / topic["contract_file"]
        if not contract.is_file():
            errors.append(f"topic {topic['id']} contract does not exist: {topic['contract_file']}")

    for framework in registry.frameworks.values():
        unknown_topics = sorted(set(framework["supported_topics"]) - set(registry.topics))
        if unknown_topics:
            errors.append(
                f"framework {framework['id']} references unknown topics: "
                f"{', '.join(unknown_topics)}"
            )
        manifest_path = root / framework["adapter_manifest"]
        if not manifest_path.is_file():
            errors.append(
                f"framework {framework['id']} adapter is missing: {framework['adapter_manifest']}"
            )
            continue
        manifest = load_json(manifest_path)
        errors.extend(
            f"{framework['adapter_manifest']}: {item}"
            for item in _schema_errors(manifest, adapter_schema)
        )
        for key in ("framework_id", "name", "upstream_url", "upstream_commit", "license_spdx"):
            expected_key = "id" if key == "framework_id" else key
            if manifest.get(key) != framework.get(expected_key):
                errors.append(f"framework {framework['id']} adapter mismatch for {key}")
        for patch in manifest.get("patches", []):
            patch_path = manifest_path.parent / patch
            if not patch_path.is_file():
                errors.append(f"framework {framework['id']} patch is missing: {patch}")

    validator_file = root / "real_eval" / "scripts" / "validate_framework_run.py"
    validators = _validator_names(validator_file) if validator_file.is_file() else set()
    if not validators:
        errors.append("validator mapping is missing or unreadable")

    for run in registry.runs:
        key = f"{run['topic_id']}:{run['mode']}:{run['framework_id']}"
        topic = registry.topics.get(run["topic_id"])
        framework = registry.frameworks.get(run["framework_id"])
        if topic is None:
            errors.append(f"run {key} references an unknown topic")
            continue
        if framework is None:
            errors.append(f"run {key} references an unknown framework")
            continue
        if run["mode"] not in topic["supported_modes"]:
            errors.append(f"run {key} uses a mode not supported by its topic")
        if run["topic_id"] not in framework["supported_topics"]:
            errors.append(f"run {key} uses a topic not supported by its framework")
        wrapper = root / run["wrapper"]
        if not wrapper.is_file():
            errors.append(f"run {key} wrapper does not exist: {run['wrapper']}")
        elif (
            run["mode"] == "fullrun"
            and "codex exec" in wrapper.read_text(encoding="utf-8", errors="ignore")
            and run["admission_status"] != "unsupported_non_native"
        ):
            errors.append(f"run {key} uses generic codex exec but is not marked unsupported")
        if run["mode"] != "fullrun" and run["admission_status"] != "diagnostic":
            errors.append(f"run {key} non-fullrun mapping must be diagnostic")
        if run["validator"] not in validators:
            errors.append(f"run {key} references unknown validator: {run['validator']}")

    return errors


def _load_validator_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("rceval_framework_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to import validator module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_run(
    registry: Registry,
    *,
    topic: str,
    framework: str,
    mode: str,
    run_dir: Path,
) -> dict[str, Any]:
    rows = registry.matching_runs(topic=topic, framework=framework, mode=mode)
    if not rows:
        raise ValueError(f"run mapping not found: {topic}:{mode}:{framework}")
    row = rows[0]
    if row["admission_status"] == "unsupported_non_native":
        raise ValueError("run mapping is unsupported_non_native and cannot be admitted")
    if not run_dir.is_dir():
        raise ValueError(f"run directory does not exist: {run_dir}")

    module = _load_validator_module(
        registry.root / "real_eval" / "scripts" / "validate_framework_run.py"
    )
    result = module.validate(row["validator"], run_dir.resolve())
    payload = asdict(result)
    payload.update(
        {
            "schema_version": 1,
            "topic_id": topic,
            "framework_id": framework,
            "mode": mode,
            "admission_status": row["admission_status"],
            "ok": result.ok,
        }
    )
    return payload


def validate_leaderboard(root: Path, payload: dict[str, Any]) -> list[str]:
    schema = json.loads((root / "schemas" / "leaderboard.schema.json").read_text())
    return _schema_errors(payload, schema)

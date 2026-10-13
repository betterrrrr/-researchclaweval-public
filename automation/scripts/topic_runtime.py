#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

SOURCE_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TopicConfig:
    label: str
    dataset_root: Path
    contract_file: Path


def _default_repo_root() -> Path:
    return Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", str(SOURCE_REPO_ROOT))).expanduser()


def _default_automation_dir(repo_root: Path) -> Path:
    return Path(os.environ.get("RESEARCHCLAWEVAL_AUTOMATION_DIR", str(repo_root / "automation")))


def default_topic_config(repo_root: Path | None = None) -> TopicConfig:
    repo_root = repo_root or _default_repo_root()
    return TopicConfig(
        label="Default-Topic",
        dataset_root=repo_root / "data" / "unset-topic",
        contract_file=repo_root / "automation" / "runtime_topic.md",
    )


def _parse_runtime_topic_markdown(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    matches: dict[str, str] = {}
    bullet_matches = {
        "label": re.search(r"- Topic label:\s*`([^`]+)`", text),
        "dataset_root": re.search(r"- Dataset root:\s*`([^`]+)`", text),
        "contract_file": re.search(r"- Contract file:\s*`([^`]+)`", text),
    }
    matches.update({key: match.group(1) for key, match in bullet_matches.items() if match})
    if matches:
        return matches

    legacy_label = re.search(r"Current active topic:\s*\*\*([^*]+)\*\*", text)
    if legacy_label:
        matches["label"] = legacy_label.group(1).strip()

    legacy_refs = re.search(r"## Canonical references\s*\n((?:- `[^`]+`\n)+)", text)
    if legacy_refs:
        contract_candidates = re.findall(r"- `([^`]+)`", legacy_refs.group(1))
        if contract_candidates:
            matches["contract_file"] = contract_candidates[0].strip()

    legacy_dataset = re.search(r"## Dataset root\s*\n`([^`]+)`", text)
    if legacy_dataset:
        matches["dataset_root"] = legacy_dataset.group(1).strip()

    return matches


def _load_topic_registry(repo_root: Path) -> list[dict[str, str]]:
    registry_path = repo_root / "real_eval" / "registry" / "topics.json"
    if not registry_path.exists():
        return []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    topics = payload.get("topics", [])
    return [topic for topic in topics if isinstance(topic, dict)]


def _normalize_topic_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _resolve_topic_from_registry(repo_root: Path, runtime_topic: dict[str, str]) -> dict[str, str]:
    topics = _load_topic_registry(repo_root)
    if not topics:
        return {}

    contract_value = runtime_topic.get("contract_file")
    if contract_value:
        contract_name = Path(contract_value).name
        for topic in topics:
            if Path(topic.get("contract_file", "")).name == contract_name:
                return topic

    label_value = runtime_topic.get("label")
    if label_value:
        normalized = _normalize_topic_key(label_value)
        for topic in topics:
            keys = {
                _normalize_topic_key(str(topic.get("id", ""))),
                _normalize_topic_key(str(topic.get("label", ""))),
                _normalize_topic_key(Path(str(topic.get("contract_file", ""))).stem),
            }
            if normalized in keys:
                return topic

    return {}


def _resolve_repo_path(repo_root: Path, value: str | None, fallback: Path) -> Path:
    if not value:
        return fallback
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            return repo_root / candidate.relative_to(repo_root)
        except ValueError:
            pass
        parts = candidate.parts
        repo_names = {repo_root.name}
        if repo_root.parent.name == ".worktrees" and repo_root.parent.parent.name:
            repo_names.add(repo_root.parent.parent.name)
        for repo_name in repo_names:
            if repo_name not in parts:
                continue
            anchor = parts.index(repo_name)
            relative = Path(*parts[anchor + 1 :]) if anchor + 1 < len(parts) else Path()
            return repo_root / relative
        return candidate
    return repo_root / candidate


def load_topic_config(repo_root: Path | None = None, automation_dir: Path | None = None) -> TopicConfig:
    repo_root = repo_root or _default_repo_root()
    automation_dir = automation_dir or _default_automation_dir(repo_root)
    defaults = default_topic_config(repo_root)
    runtime_topic = _parse_runtime_topic_markdown(automation_dir / "runtime_topic.md")
    registry_topic = _resolve_topic_from_registry(repo_root, runtime_topic)
    return TopicConfig(
        label=os.environ.get("RESEARCHCLAWEVAL_TOPIC_LABEL", runtime_topic.get("label", defaults.label)),
        dataset_root=_resolve_repo_path(
            repo_root,
            os.environ.get(
                "RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT",
                runtime_topic.get("dataset_root", registry_topic.get("dataset_root", str(defaults.dataset_root))),
            ),
            defaults.dataset_root,
        ),
        contract_file=_resolve_repo_path(
            repo_root,
            os.environ.get(
                "RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE",
                runtime_topic.get("contract_file", registry_topic.get("contract_file", str(defaults.contract_file))),
            ),
            defaults.contract_file,
        ),
    )


def render_topic_command(command: str, topic: TopicConfig) -> str:
    rendered = (
        command.replace("__TOPIC_LABEL__", topic.label)
        .replace("__TOPIC_DATASET_ROOT__", str(topic.dataset_root))
        .replace("__TOPIC_CONTRACT_FILE__", str(topic.contract_file))
    )
    return (
        rendered
        .replace("__BABYLM_ROOT__", str(topic.dataset_root))
        .replace("__BABYLM_TASK_FILE__", str(topic.contract_file))
    )


def write_runtime_topic_markdown(path: Path, topic: TopicConfig) -> None:
    content = "\n".join(
        [
            "# Runtime Topic Contract",
            "",
            "## Topic",
            "",
            f"- Topic label: `{topic.label}`",
            f"- Dataset root: `{topic.dataset_root}`",
            f"- Contract file: `{topic.contract_file}`",
            "",
            "## Goal",
            "",
            "当前自动化运行的真实 e2e 任务必须围绕这个 topic 展开。",
            "",
            "## Smoke Gate",
            "",
            "在提交 `systemd --user` 级别 e2e 之前，smoke 阶段必须先确认：",
            "",
            "1. 当前项目真正消费的任务输入位置已经找对",
            "2. 该输入不再指向旧 topic",
            "3. 当前项目已经知道数据集路径或本 contract 文件路径",
            "4. 如需改动，只做最小必要改动",
            "5. 提交出去的 e2e 将实际跑这个 topic",
            "",
            "## Acceptance",
            "",
            "只有当以上条件满足时，才允许从 smoke 进入 e2e dispatch。",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")

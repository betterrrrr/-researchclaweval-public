"""Topic Contract 抽象 — 定义当前评估轮次的任务契约。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TopicConfig:
    """Topic 契约：当前评估轮次必须对齐的元数据。"""

    label: str
    dataset_root: Path
    contract_file: Path

    @classmethod
    def from_env(
        cls,
        fallback_label: str = "BabyLM-10M",
        fallback_dataset_root: Path | None = None,
        fallback_contract_file: Path | None = None,
    ) -> TopicConfig:
        """从环境变量构造 TopicConfig，支持 RESEARCHCLAWEVAL_TOPIC_* 前缀。"""
        repo_root = Path(
            os.environ.get("RESEARCHCLAWEVAL_ROOT", str(Path(__file__).resolve().parents[1])),
        ).expanduser()
        dataset_root = fallback_dataset_root or repo_root / "BabyLM-2026-Strict-Small"
        contract_file = fallback_contract_file or repo_root / "BabyLM-10M_七框架任务包装与分发指南.md"
        return cls(
            label=os.environ.get("RESEARCHCLAWEVAL_TOPIC_LABEL", fallback_label),
            dataset_root=Path(os.environ.get("RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT", str(dataset_root))),
            contract_file=Path(os.environ.get("RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE", str(contract_file))),
        )

    @classmethod
    def from_runtime_markdown(cls, path: Path) -> TopicConfig | None:
        """解析 runtime_topic.md 格式的契约文件。"""
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
        matches = {
            "label": re.search(r"- Topic label:\s*`([^`]+)`", text),
            "dataset_root": re.search(r"- Dataset root:\s*`([^`]+)`", text),
            "contract_file": re.search(r"- Contract file:\s*`([^`]+)`", text),
        }
        vals = {key: match.group(1) for key, match in matches.items() if match}
        if not vals:
            return None
        return cls(
            label=vals.get("label", ""),
            dataset_root=Path(vals.get("dataset_root", ".")),
            contract_file=Path(vals.get("contract_file", ".")),
        )


class TopicRenderer:
    """将命令模板中的占位符渲染为真实 Topic 值。"""

    PLACEHOLDERS = (
        ("__TOPIC_LABEL__", "label"),
        ("__TOPIC_DATASET_ROOT__", "dataset_root"),
        ("__TOPIC_CONTRACT_FILE__", "contract_file"),
        ("__BABYLM_ROOT__", "dataset_root"),
        ("__BABYLM_TASK_FILE__", "contract_file"),
    )

    def __init__(self, topic: TopicConfig) -> None:
        self.topic = topic

    def render(self, command: str) -> str:
        for placeholder, attr in self.PLACEHOLDERS:
            command = command.replace(placeholder, str(getattr(self.topic, attr)))
        return command

    @classmethod
    def render_for(cls, command: str, topic: TopicConfig) -> str:
        return cls(topic).render(command)

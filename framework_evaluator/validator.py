"""项目对齐验证器 — 检查项目输出和命令是否对齐当前 Topic Contract。

核心逻辑：
1. 文件存在性扫描（smoke / result 文件）
2. 禁用标记扫描（防止项目回退到旧 topic，如 sklearn iris）
3. 必要字段扫描（JSON 中是否包含 topic_label / dataset_root / contract_file）
4. 命令对齐检查（e2e_cmd 渲染后是否包含必要路径和配置）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .topic import TopicConfig


DEFAULT_FORBIDDEN_MARKERS = [
    "sklearn_iris",
    "digits_iris_light",
    "minimal_iris_digits",
    "load_iris",
    "load_digits",
]


@dataclass
class FileScanResult:
    path: str
    exists: bool
    forbidden_markers: list[str] = field(default_factory=list)
    required: dict[str, bool] = field(default_factory=dict)


@dataclass
class CommandAlignmentResult:
    project_id: str
    raw_e2e_cmd: str
    rendered_e2e_cmd: str
    required: dict[str, bool] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    forbidden_markers: list[str] = field(default_factory=list)
    ok: bool = False


@dataclass
class ValidationResult:
    project_id: str
    phase: str
    topic_label: str
    dataset_root: str
    contract_file: str
    ok: bool
    results: list[FileScanResult] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    forbidden_hits: list[dict] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    smoke_alignment: CommandAlignmentResult | None = None


class ProjectValidator:
    """可配置的通用项目验证器。"""

    def __init__(
        self,
        topic: TopicConfig,
        forbidden_markers: list[str] | None = None,
        required_keys: list[str] | None = None,
        provider_config: str = "",
        semantic_source: str = "",
    ) -> None:
        self.topic = topic
        self.forbidden_markers = forbidden_markers or list(DEFAULT_FORBIDDEN_MARKERS)
        self.required_keys = required_keys or ["topic_label", "dataset_root", "contract_file"]
        self.provider_config = provider_config
        self.semantic_source = semantic_source

    def _scan_json_values(self, value) -> dict[str, bool]:
        text_hits = {key: False for key in self.required_keys}
        if isinstance(value, dict):
            for nested in value.values():
                nested_hits = self._scan_json_values(nested)
                for key in self.required_keys:
                    text_hits[key] = text_hits[key] or nested_hits.get(key, False)
            return text_hits
        if isinstance(value, list):
            for nested in value:
                nested_hits = self._scan_json_values(nested)
                for key in self.required_keys:
                    text_hits[key] = text_hits[key] or nested_hits.get(key, False)
            return text_hits
        if isinstance(value, str):
            return {
                "topic_label": self.topic.label in value,
                "dataset_root": str(self.topic.dataset_root) in value,
                "contract_file": str(self.topic.contract_file) in value,
            }
        return text_hits

    def scan_file(self, path: Path) -> FileScanResult:
        if not path.exists():
            return FileScanResult(path=str(path), exists=False)
        text = path.read_text(encoding="utf-8", errors="ignore")
        forbidden = [marker for marker in self.forbidden_markers if marker in text]
        required = self._scan_json_values(text)
        if path.suffix == ".json":
            try:
                required = self._scan_json_values(json.loads(text))
            except json.JSONDecodeError:
                pass
        return FileScanResult(
            path=str(path),
            exists=True,
            forbidden_markers=forbidden,
            required=required,
        )

    def check_command_alignment(self, project_id: str, raw_cmd: str, rendered_cmd: str) -> CommandAlignmentResult:
        required = {
            "topic_label": self.topic.label in rendered_cmd,
            "dataset_root": str(self.topic.dataset_root) in rendered_cmd,
            "contract_file": str(self.topic.contract_file) in rendered_cmd,
        }
        if self.provider_config:
            required["provider_config"] = self.provider_config in rendered_cmd
        if self.semantic_source:
            required["semantic_source"] = self.semantic_source in rendered_cmd
        missing = [key for key, ok in required.items() if not ok]
        forbidden = [marker for marker in self.forbidden_markers if marker in rendered_cmd]
        return CommandAlignmentResult(
            project_id=project_id,
            raw_e2e_cmd=raw_cmd,
            rendered_e2e_cmd=rendered_cmd,
            required=required,
            missing=missing,
            forbidden_markers=forbidden,
            ok=not missing and not forbidden,
        )

    def validate(
        self,
        project_id: str,
        phase: str,
        files: list[Path],
        raw_e2e_cmd: str = "",
        rendered_e2e_cmd: str = "",
    ) -> ValidationResult:
        results = [self.scan_file(path) for path in files]
        missing_files = [r.path for r in results if not r.exists]
        forbidden_hits = [
            {"path": r.path, "markers": r.forbidden_markers}
            for r in results
            if r.forbidden_markers
        ]
        missing_required: list[str] = []
        smoke_alignment: CommandAlignmentResult | None = None

        if phase == "e2e":
            required_totals = {key: False for key in self.required_keys}
            for r in results:
                if not r.exists:
                    continue
                for key, ok in r.required.items():
                    required_totals[key] = required_totals.get(key, False) or ok
            missing_required = [key for key, ok in required_totals.items() if not ok]
        else:
            smoke_alignment = self.check_command_alignment(
                project_id=project_id,
                raw_cmd=raw_e2e_cmd,
                rendered_cmd=rendered_e2e_cmd,
            )
            if not smoke_alignment.ok:
                missing_required = smoke_alignment.missing
                if smoke_alignment.forbidden_markers:
                    forbidden_hits.append({
                        "path": f"project:{project_id}:e2e_cmd",
                        "markers": smoke_alignment.forbidden_markers,
                    })

        ok = not missing_files and not forbidden_hits and not missing_required
        return ValidationResult(
            project_id=project_id,
            phase=phase,
            topic_label=self.topic.label,
            dataset_root=str(self.topic.dataset_root),
            contract_file=str(self.topic.contract_file),
            ok=ok,
            results=results,
            missing_files=missing_files,
            forbidden_hits=forbidden_hits,
            missing_required=missing_required,
            smoke_alignment=smoke_alignment,
        )

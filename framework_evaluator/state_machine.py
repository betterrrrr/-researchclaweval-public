"""状态机持久化 — 管理单个项目从 Smoke 到 Complete/Blocked 的全生命周期状态。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class Phase(str, Enum):
    SMOKE = "smoke"
    E2E = "e2e"


class Status(str, Enum):
    # Smoke 阶段
    SMOKE_FAILED = "smoke_failed"
    SMOKE_PASSED = "smoke_passed"
    # E2E 阶段
    E2E_SUBMITTED = "e2e_submitted"
    E2E_RUNNING = "e2e_running"
    E2E_RESUBMITTED = "e2e_resubmitted"
    E2E_FAILED = "e2e_failed"
    E2E_PASSED = "e2e_passed"
    # 终态
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class ProjectState:
    project_id: str
    project_name: str
    phase: str
    status: str
    attempt: int = 0
    unit: str = ""
    started_at: str = ""
    finished_at: str = ""
    smoke_command: str = ""
    e2e_command: str = ""
    submit_command: str = ""
    topic_label: str = ""
    topic_dataset_root: str = ""
    topic_contract_file: str = ""
    topic_ready: bool = False
    acceptance_summary: str = ""
    patched_files: list[str] = field(default_factory=list)
    summary: str = ""
    exit_code: int | None = None
    log_file: str = ""
    validation_ok: bool = False
    validation_output: str = ""
    framework_completed: bool = False
    adaptation_notes: list[str] = field(default_factory=list)

    def is_terminal(self) -> bool:
        return self.status in {
            Status.SMOKE_FAILED.value,
            Status.COMPLETED.value,
            Status.BLOCKED.value,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProjectState:
        # 过滤掉类中不存在的字段，保证前向兼容
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class StateStore:
    """基于 JSON 文件的状态持久化存储。"""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, project_id: str) -> Path:
        return self.state_dir / f"{project_id}.json"

    def load(self, project_id: str) -> ProjectState | None:
        path = self._path(project_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ProjectState.from_dict(data)
        except (json.JSONDecodeError, TypeError):
            return None

    def save(self, state: ProjectState) -> None:
        path = self._path(state.project_id)
        path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class RuntimeStateStore:
    """全局运行时状态（记录当前项目、最后动作等）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, **kwargs) -> None:
        data = self.load()
        data.update(kwargs)
        data["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat()
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

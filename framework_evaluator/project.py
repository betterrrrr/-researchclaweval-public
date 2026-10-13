"""Project 定义与加载 — 被评估的科研框架项目。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Project:
    """单个科研框架项目的运行时描述。"""

    id: str
    name: str
    smoke_cmd: str
    e2e_cmd: str
    enabled: bool = True
    failure_mode: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        return cls(
            id=str(data["id"]),
            name=data["name"],
            smoke_cmd=data["smoke_cmd"],
            e2e_cmd=data["e2e_cmd"],
            enabled=data.get("enabled", True),
            failure_mode=data.get("failure_mode", ""),
        )


class ProjectLoader:
    """从 projects.yaml（实为 JSON）加载项目列表。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_all(self) -> list[Project]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Project.from_dict(item) for item in data.get("projects", [])]

    def load_map(self) -> dict[str, Project]:
        return {p.id: p for p in self.load_all()}

    def get(self, project_id: str) -> Project | None:
        return self.load_map().get(project_id)


class TodoQueue:
    """基于 Markdown todo list 的简易项目队列。"""

    TODO_RE = re.compile(r"^- \[([ xX])\] (\d{2}) (.+)$")

    def __init__(self, path: Path) -> None:
        self.path = path

    def parse(self) -> list[dict]:
        items = []
        if not self.path.exists():
            return items
        for line in self.path.read_text(encoding="utf-8").splitlines():
            match = self.TODO_RE.match(line.strip())
            if not match:
                continue
            items.append(
                {
                    "checked": match.group(1).lower() == "x",
                    "id": match.group(2),
                    "name": match.group(3),
                }
            )
        return items

    def current(self, projects: dict[str, Project]) -> Project | None:
        for item in self.parse():
            if item["checked"]:
                continue
            project = projects.get(item["id"])
            if project and project.enabled:
                return project
        return None

    def mark_complete(self, project_id: str) -> None:
        if not self.path.exists():
            return
        lines = self.path.read_text(encoding="utf-8").splitlines()
        updated = []
        for line in lines:
            match = self.TODO_RE.match(line.strip())
            if match and match.group(2) == project_id:
                updated.append(f"- [x] {match.group(2)} {match.group(3)}")
            else:
                updated.append(line)
        self.path.write_text("\n".join(updated) + "\n", encoding="utf-8")

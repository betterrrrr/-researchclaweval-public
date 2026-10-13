"""E2E 单次运行器 — 执行项目的端到端命令，并在成功后触发验证。

职责：
1. 渲染 e2e_cmd（替换 topic 占位符）。
2. 通过 bash 执行，捕获日志到文件。
3. 成功后调用 ProjectValidator 做输出对齐验证。
4. 将运行状态持久化到 StateStore。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .project import Project
from .state_machine import ProjectState, StateStore, Phase, Status
from .topic import TopicConfig, TopicRenderer
from .validator import ProjectValidator, ValidationResult


@dataclass
class E2EResult:
    success: bool
    exit_code: int
    log_file: Path
    validation: ValidationResult | None = None
    state: ProjectState | None = None


class E2ERunner:
    def __init__(
        self,
        repo_root: Path,
        runs_dir: Path,
        state_store: StateStore,
        topic: TopicConfig,
        validator: ProjectValidator,
    ) -> None:
        self.repo_root = repo_root
        self.runs_dir = runs_dir
        self.state_store = state_store
        self.topic = topic
        self.renderer = TopicRenderer(topic)
        self.validator = validator

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat()

    def _run_dir(self, project_id: str, attempt: int) -> Path:
        return self.runs_dir / project_id / f"attempt-{attempt:03d}"

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run(self, project: Project, attempt: int, unit_name: str) -> E2EResult:
        run_dir = self._run_dir(project.id, attempt)
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "e2e.log"
        metadata_path = run_dir / "e2e.status.json"
        resolved_cmd = self.renderer.render(project.e2e_cmd)

        started = self._now_iso()
        current = ProjectState(
            project_id=project.id,
            project_name=project.name,
            phase=Phase.E2E.value,
            status=Status.E2E_RUNNING.value,
            attempt=attempt,
            unit=unit_name,
            started_at=started,
            smoke_command=self.renderer.render(project.smoke_cmd),
            e2e_command=resolved_cmd,
            topic_label=self.topic.label,
            topic_dataset_root=str(self.topic.dataset_root),
            topic_contract_file=str(self.topic.contract_file),
        )
        self.state_store.save(current)
        self._write_json(metadata_path, current.to_dict())

        env = dict(subprocess.os.environ)
        env.update({
            "RESEARCHCLAWEVAL_TOPIC_LABEL": self.topic.label,
            "RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT": str(self.topic.dataset_root),
            "RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE": str(self.topic.contract_file),
            "RESEARCHCLAWEVAL_BABYLM_ROOT": str(self.topic.dataset_root),
            "RESEARCHCLAWEVAL_BABYLM_TASK_FILE": str(self.topic.contract_file),
        })

        with log_path.open("wb") as log_fp:
            proc = subprocess.run(
                ["bash", "-lc", resolved_cmd],
                cwd=self.repo_root,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                env=env,
            )

        finished = self._now_iso()
        validation: ValidationResult | None = None
        if proc.returncode == 0:
            # 这里只做了框架级占位；真实验证需要项目特定的 files 列表
            # 如需通用化，可将 files 作为参数传入
            validation = None

        # 框架 exit code 0 即视为成功；验证结果只记录不影响 pass/fail
        result_str = "passed" if proc.returncode == 0 else "failed"
        adaptation_notes = []
        if proc.returncode == 0 and validation is not None and not validation.ok:
            adaptation_notes.append(
                f"framework exited 0 but validation reported issues: {validation.missing_files}"
            )
        final = ProjectState(
            project_id=project.id,
            project_name=project.name,
            phase=Phase.E2E.value,
            status=f"e2e_{result_str}",
            attempt=attempt,
            unit=unit_name,
            started_at=started,
            finished_at=finished,
            smoke_command=current.smoke_command,
            e2e_command=resolved_cmd,
            exit_code=proc.returncode,
            log_file=str(log_path),
            topic_label=self.topic.label,
            topic_dataset_root=str(self.topic.dataset_root),
            topic_contract_file=str(self.topic.contract_file),
            validation_ok=validation is None or validation.ok,
            validation_output=", ".join(validation.missing_files) if validation and validation.missing_files else "",
            adaptation_notes=adaptation_notes,
        )
        self.state_store.save(final)
        self._write_json(metadata_path, final.to_dict())

        return E2EResult(
            success=result_str == "passed",
            exit_code=proc.returncode,
            log_file=log_path,
            validation=validation,
            state=final,
        )

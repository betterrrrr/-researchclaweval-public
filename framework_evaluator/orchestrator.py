"""Orchestrator — 多项目评估流水线的主编排器。

状态机流转：
  [empty/smoke_failed] ──► handle_initial_session ──► [e2e_submitted/running]
                                                              │
                                                              ▼
  [completed/blocked] ◄── handle_e2e_repair ◄── [e2e_failed] ◄── check_e2e ──► [e2e_passed] ──► [completed]

核心设计：
1. 每个项目按 todo queue 顺序执行。
2. 每个项目最多尝试 N 次（通过 next_attempt 计数）。
3. Smoke 阶段通过外部 Agent（Codex）在 headless 会话内完成并自动 dispatch e2e。
4. E2E 阶段通过本地 bash 执行，完成后自动验证。
5. E2E 失败时再次调用外部 Agent 进行修复并重试。
6. 所有状态通过 StateStore / RuntimeStateStore 持久化。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .agent_runner import AgentRunner, AgentResult
from .e2e_runner import E2ERunner, E2EResult
from .project import Project, ProjectLoader, TodoQueue
from .prompts import PromptContext, SmokePrompt, RepairPrompt
from .state_machine import ProjectState, StateStore, RuntimeStateStore, Phase, Status
from .topic import TopicConfig, TopicRenderer


@dataclass
class OrchestratorConfig:
    """编排器运行时配置。"""

    repo_root: Path
    automation_dir: Path
    projects_file: Path
    todo_file: Path
    state_dir: Path
    runs_dir: Path
    runtime_state_file: Path
    codex_home_dir: Path | None = None
    codex_bin: Path | None = None
    e2e_runner_script: Path | None = None
    orchestrator_script: Path | None = None


class Dispatcher:
    """任务分发器 — 默认实现使用 systemd-run，但可替换为任意调度器。"""

    def __init__(
        self,
        repo_root: Path,
        env_prefix: str = "RESEARCHCLAWEVAL",
    ) -> None:
        self.repo_root = repo_root
        self.env_prefix = env_prefix

    def dispatch_followup(
        self,
        trigger: str,
        source_project_id: str,
        next_project_id: str | None,
        orchestrator_script: Path,
        env_vars: dict[str, str],
    ) -> None:
        if next_project_id is None:
            return
        unit = (
            f"{self.env_prefix.lower()}-next-{source_project_id}-to-{next_project_id}-"
            f"{int(datetime.now(timezone.utc).timestamp())}"
        )
        cmd = [
            "systemd-run",
            "--user",
            "--collect",
            "--unit",
            unit,
            "--same-dir",
        ]
        for key, value in env_vars.items():
            cmd.extend(["--setenv", f"{key}={value}"])
        cmd.extend([sys.executable, str(orchestrator_script), "step", "--trigger", trigger])
        subprocess.run(cmd, cwd=self.repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def dispatch_e2e(
        self,
        unit_name: str,
        e2e_runner_script: Path,
        project_id: str,
        attempt: int,
        env_vars: dict[str, str],
    ) -> None:
        """构建用于 systemd-run 的 e2e 提交命令字符串（供 prompt 使用）。"""
        runner_cmd = [
            "systemd-run",
            "--user",
            "--collect",
            "--unit",
            unit_name,
            "--same-dir",
        ]
        for key, value in env_vars.items():
            runner_cmd.extend(["--setenv", f"{key}={value}"])
        runner_cmd.extend([
            sys.executable,
            str(e2e_runner_script),
            "--project-id",
            project_id,
            "--attempt",
            str(attempt),
        ])
        return shlex.join(runner_cmd)


class Orchestrator:
    def __init__(
        self,
        config: OrchestratorConfig,
        topic: TopicConfig,
        agent_runner: AgentRunner,
        e2e_runner: E2ERunner,
        dispatcher: Dispatcher | None = None,
        smoke_prompt: SmokePrompt | None = None,
        repair_prompt: RepairPrompt | None = None,
    ) -> None:
        self.config = config
        self.topic = topic
        self.renderer = TopicRenderer(topic)
        self.agent_runner = agent_runner
        self.e2e_runner = e2e_runner
        self.dispatcher = dispatcher or Dispatcher(config.repo_root)
        self.smoke_prompt = smoke_prompt or SmokePrompt()
        self.repair_prompt = repair_prompt or RepairPrompt()

        self.project_loader = ProjectLoader(config.projects_file)
        self.todo_queue = TodoQueue(config.todo_file)
        self.state_store = StateStore(config.state_dir)
        self.runtime_store = RuntimeStateStore(config.runtime_state_file)

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #
    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat()

    def _run_dir(self, project_id: str, attempt: int) -> Path:
        return self.config.runs_dir / project_id / f"attempt-{attempt:03d}"

    def _next_attempt(self, project_id: str) -> int:
        base = self.config.runs_dir / project_id
        if not base.exists():
            return 1
        attempts = []
        for path in base.iterdir():
            match = re.fullmatch(r"attempt-(\d{3})", path.name)
            if match:
                attempts.append(int(match.group(1)))
        return max(attempts, default=0) + 1

    def _load_jsonl_items(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        items = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items

    def _env_vars(self) -> dict[str, str]:
        return {
            "RESEARCHCLAWEVAL_ROOT": str(self.config.repo_root),
            "RESEARCHCLAWEVAL_AUTOMATION_DIR": str(self.config.automation_dir),
            "RESEARCHCLAWEVAL_TOPIC_LABEL": self.topic.label,
            "RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT": str(self.topic.dataset_root),
            "RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE": str(self.topic.contract_file),
            "RESEARCHCLAWEVAL_BABYLM_ROOT": str(self.topic.dataset_root),
            "RESEARCHCLAWEVAL_BABYLM_TASK_FILE": str(self.topic.contract_file),
        }

    def _current_project(self) -> Project | None:
        projects = self.project_loader.load_map()
        return self.todo_queue.current(projects)

    # ------------------------------------------------------------------ #
    # Smoke / Initial
    # ------------------------------------------------------------------ #
    def handle_initial_session(self, project: Project) -> int:
        attempt = self._next_attempt(project.id)
        work_dir = self._run_dir(project.id, attempt)
        state_file = self.config.state_dir / f"{project.id}.json"
        unit_name = f"researchclaweval-{project.id}-e2e-attempt-{attempt:03d}"

        self.runtime_store.save(
            current_project=project.id,
            last_action="initial_session",
            last_unit=unit_name,
        )

        ctx = PromptContext(
            project_id=project.id,
            project_name=project.name,
            attempt=attempt,
            unit_name=unit_name,
            automation_dir=self.config.automation_dir,
            repo_root=self.config.repo_root,
            topic=self.topic,
            smoke_cmd=self.renderer.render(project.smoke_cmd),
            e2e_cmd=self.dispatcher.dispatch_e2e(
                unit_name=unit_name,
                e2e_runner_script=self.config.e2e_runner_script or Path(""),
                project_id=project.id,
                attempt=attempt,
                env_vars=self._env_vars(),
            ),
            provider_config=self.config.codex_home_dir or Path(""),
            semantic_source=self.config.automation_dir / "env" / "semantic_scholar.env",
            state_file=state_file,
        )
        prompt = self.smoke_prompt.render(ctx)

        result = self.agent_runner.run(
            prompt=prompt,
            work_dir=work_dir,
            label="initial",
            state_file=state_file,
            terminal_statuses={"smoke_failed", "e2e_submitted", "e2e_running"},
        )

        state = self.state_store.load(project.id)
        if state and state.status in {Status.E2E_SUBMITTED.value, Status.E2E_RUNNING.value}:
            return 0

        # 尝试从 codex platform error 恢复
        if self._recover_initial_dispatch(project, attempt, work_dir, state_file, unit_name):
            return 0

        if state and state.status == Status.SMOKE_FAILED.value:
            return 1

        if state is None and result.returncode != 0:
            self.state_store.save(
                ProjectState(
                    project_id=project.id,
                    project_name=project.name,
                    phase=Phase.SMOKE.value,
                    status=Status.SMOKE_FAILED.value,
                    attempt=attempt,
                    summary=f"agent exec exited with {result.returncode}",
                    smoke_command=self.renderer.render(project.smoke_cmd),
                    topic_label=self.topic.label,
                    topic_dataset_root=str(self.topic.dataset_root),
                    topic_contract_file=str(self.topic.contract_file),
                    topic_ready=False,
                )
            )
        return result.returncode

    def _recover_initial_dispatch(
        self, project: Project, attempt: int, work_dir: Path, state_file: Path, unit_name: str
    ) -> bool:
        """当 codex 因平台错误退出但 smoke 已成功时，尝试直接 dispatch e2e。"""
        log_path = work_dir / "initial.jsonl"
        items = self._load_jsonl_items(log_path)
        smoke_ok = False
        codex_platform_error = False
        normalized_smoke = self.renderer.render(project.smoke_cmd).replace('\\"', '"').replace("\\\\n", "\\n").strip()
        for entry in items:
            if entry.get("type") == "item.completed":
                item = entry.get("item", {})
                if item.get("type") == "command_execution" and item.get("exit_code") == 0:
                    cmd_text = item.get("command", "").replace('\\"', '"').replace("\\\\n", "\\n").strip()
                    if normalized_smoke in cmd_text or cmd_text in normalized_smoke:
                        smoke_ok = True
            if entry.get("type") == "error":
                if "invalid_encrypted_content" in entry.get("message", ""):
                    codex_platform_error = True
        if not smoke_ok or not codex_platform_error:
            return False

        submit_cmd = self.dispatcher.dispatch_e2e(
            unit_name=unit_name,
            e2e_runner_script=self.config.e2e_runner_script or Path(""),
            project_id=project.id,
            attempt=attempt,
            env_vars=self._env_vars(),
        )
        proc = subprocess.run(["bash", "-lc", submit_cmd], cwd=self.config.repo_root, capture_output=True, text=True)
        if proc.returncode != 0:
            return False

        self.state_store.save(
            ProjectState(
                project_id=project.id,
                project_name=project.name,
                phase=Phase.E2E.value,
                status=Status.E2E_SUBMITTED.value,
                attempt=attempt,
                unit=unit_name,
                smoke_command=self.renderer.render(project.smoke_cmd),
                e2e_command=self.renderer.render(project.e2e_cmd),
                submit_command=submit_cmd,
                topic_label=self.topic.label,
                topic_dataset_root=str(self.topic.dataset_root),
                topic_contract_file=str(self.topic.contract_file),
                topic_ready=True,
                acceptance_summary="Recovered dispatch after smoke succeeded and the current topic contract remained required.",
                patched_files=[],
                summary="Recovered from codex platform error after successful smoke by dispatching the prepared systemd unit.",
            )
        )
        return True

    # ------------------------------------------------------------------ #
    # E2E Repair
    # ------------------------------------------------------------------ #
    def handle_e2e_repair(self, project: Project, state: ProjectState) -> int:
        old_unit = state.unit
        if project.failure_mode == "block_on_failure":
            blocked = ProjectState(
                project_id=project.id,
                project_name=project.name,
                phase=Phase.E2E.value,
                status=Status.BLOCKED.value,
                attempt=state.attempt,
                previous_unit=old_unit,
                unit=old_unit,
                topic_label=self.topic.label,
                topic_dataset_root=str(self.topic.dataset_root),
                topic_contract_file=str(self.topic.contract_file),
                patched_files=[],
                summary="Synthetic failure path requested blocking after failed e2e follow-up.",
                finished_at=self._now_iso(),
            )
            self.state_store.save(blocked)
            self.runtime_store.save(current_project=project.id, last_action="blocked", last_unit=old_unit)
            return 0

        attempt = self._next_attempt(project.id)
        new_unit = f"researchclaweval-{project.id}-e2e-attempt-{attempt:03d}"
        work_dir = self._run_dir(project.id, attempt)
        state_file = self.config.state_dir / f"{project.id}.json"

        self.runtime_store.save(current_project=project.id, last_action="repair_e2e", last_unit=new_unit)

        ctx = PromptContext(
            project_id=project.id,
            project_name=project.name,
            attempt=attempt,
            unit_name=new_unit,
            automation_dir=self.config.automation_dir,
            repo_root=self.config.repo_root,
            topic=self.topic,
            smoke_cmd=self.renderer.render(project.smoke_cmd),
            e2e_cmd=self.dispatcher.dispatch_e2e(
                unit_name=new_unit,
                e2e_runner_script=self.config.e2e_runner_script or Path(""),
                project_id=project.id,
                attempt=attempt,
                env_vars=self._env_vars(),
            ),
            provider_config=self.config.codex_home_dir or Path(""),
            semantic_source=self.config.automation_dir / "env" / "semantic_scholar.env",
            state_file=state_file,
            failure_mode=project.failure_mode,
        )
        prompt = self.repair_prompt.render(ctx)

        result = self.agent_runner.run(
            prompt=prompt,
            work_dir=work_dir,
            label="repair_e2e",
            state_file=state_file,
            terminal_statuses={"e2e_resubmitted", "blocked"},
        )
        new_state = self.state_store.load(project.id)
        if new_state and new_state.status in {Status.E2E_RESUBMITTED.value, Status.BLOCKED.value}:
            return 0
        return result.returncode

    # ------------------------------------------------------------------ #
    # Step / 主循环
    # ------------------------------------------------------------------ #
    def step(self) -> int:
        project = self._current_project()
        if project is None:
            self.runtime_store.save(current_project=None, last_action="complete", last_unit=None)
            print("all projects completed")
            return 0

        state = self.state_store.load(project.id)
        status = state.status if state else ""

        if status == Status.BLOCKED.value:
            self.runtime_store.save(current_project=project.id, last_action="blocked", last_unit=state.unit if state else None)
            print(f"{project.id} is blocked")
            return 1

        if not status or status in {Status.SMOKE_FAILED.value, Status.SMOKE_PASSED.value}:
            return self.handle_initial_session(project)

        if status in {Status.E2E_SUBMITTED.value, Status.E2E_RUNNING.value, Status.E2E_RESUBMITTED.value}:
            unit_name = state.unit if state else ""
            self.runtime_store.save(current_project=project.id, last_action="check_e2e", last_unit=unit_name)
            # 这里简化处理：如果 e2e_runner 已经把状态写成 e2e_passed / e2e_failed，则直接读取
            run_dir = self._run_dir(project.id, state.attempt)
            metadata_path = run_dir / "e2e.status.json"
            if metadata_path.exists():
                try:
                    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
                    meta_status = meta.get("status", "")
                    if meta_status == Status.E2E_FAILED.value:
                        return self.handle_e2e_repair(project, ProjectState.from_dict(meta))
                    if meta_status == Status.E2E_PASSED.value:
                        self._mark_complete(project, unit_name)
                        return 0
                except json.JSONDecodeError:
                    pass
            # 如果 metadata 不存在，默认按失败重试（保守策略）
            return self.handle_e2e_repair(project, state)

        if status == Status.E2E_PASSED.value:
            self._mark_complete(project, state.unit if state else "")
            return 0

        if status == Status.COMPLETED.value:
            self.todo_queue.mark_complete(project.id)
            return 0

        if status == Status.E2E_FAILED.value:
            return self.handle_e2e_repair(project, state)

        return self.handle_initial_session(project)

    def _mark_complete(self, project: Project, unit_name: str) -> None:
        state = self.state_store.load(project.id)
        if state:
            state.status = Status.COMPLETED.value
            state.finished_at = self._now_iso()
            self.state_store.save(state)
        self.todo_queue.mark_complete(project.id)
        self.runtime_store.save(
            current_project=project.id,
            last_action="complete_project",
            last_unit=unit_name,
        )
        next_project = self._current_project()
        self.dispatcher.dispatch_followup(
            trigger="advance-next",
            source_project_id=project.id,
            next_project_id=next_project.id if next_project else None,
            orchestrator_script=self.config.orchestrator_script or Path(__file__),
            env_vars=self._env_vars(),
        )
        print(f"{project.id} completed")

    def status(self) -> dict:
        return {
            "current_project": self._current_project(),
            "runtime": self.runtime_store.load(),
        }

"""Agent 执行器抽象 — 通过外部 LLM Agent（Codex / Claude / 其他 CLI Agent）执行 headless 任务。

设计思路：
- AgentRunner 是通用接口，可被替换为任意 CLI Agent。
- CodexAgentRunner 是原始实现，保留 jsonl 日志捕获、状态轮询、超时控制、SIGTERM/SIGKILL 清理。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentResult:
    returncode: int
    stdout_path: Path | None = None
    last_message_path: Path | None = None


class AgentRunner(ABC):
    """通用 Agent 执行器接口。"""

    @abstractmethod
    def run(
        self,
        prompt: str,
        work_dir: Path,
        label: str,
        state_file: Path | None = None,
        terminal_statuses: set[str] | None = None,
    ) -> AgentResult:
        """
        执行一次 headless agent 会话。

        Args:
            prompt: 给 agent 的完整指令文本。
            work_dir: 会话工作目录（用于存放日志和输出）。
            label: 本次运行的标签（用于命名日志文件）。
            state_file: 可选的状态文件路径；如果 agent 或外部系统把状态写入此文件，
                        且状态匹配 terminal_statuses，则提前终止 agent 进程。
            terminal_statuses: 提前终止的状态集合。
        """
        ...


class CodexAgentRunner(AgentRunner):
    """基于 Codex CLI (`codex exec --yolo`) 的 Agent 执行器。"""

    def __init__(
        self,
        codex_bin: Path,
        codex_home: Path,
        repo_root: Path,
        timeout_seconds: int = 0,
        state_poll_seconds: float = 2.0,
    ) -> None:
        self.codex_bin = codex_bin
        self.codex_home = codex_home
        self.repo_root = repo_root
        self.timeout_seconds = timeout_seconds
        self.state_poll_seconds = state_poll_seconds

    @staticmethod
    def _load_json(path: Path, default: dict | None = None) -> dict:
        if not path.exists():
            return default or {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default or {}

    @staticmethod
    def _terminate_process_group(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(0.2)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    def run(
        self,
        prompt: str,
        work_dir: Path,
        label: str,
        state_file: Path | None = None,
        terminal_statuses: set[str] | None = None,
    ) -> AgentResult:
        work_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = work_dir / f"{label}.jsonl"
        last_message_path = work_dir / f"{label}_last_message.txt"

        cmd = [
            str(self.codex_bin),
            "exec",
            "--yolo",
            "--skip-git-repo-check",
            "-C",
            str(self.repo_root),
            "--json",
            "-o",
            str(last_message_path),
            prompt,
        ]
        env = dict(os.environ)
        env["CODEX_HOME"] = str(self.codex_home)

        with stdout_path.open("wb") as fp:
            proc = subprocess.Popen(
                cmd,
                cwd=self.repo_root,
                stdout=fp,
                stderr=subprocess.STDOUT,
                env=env,
                preexec_fn=os.setsid,
            )
            deadline = None if self.timeout_seconds <= 0 else time.monotonic() + self.timeout_seconds
            terminal_statuses = terminal_statuses or set()

            while True:
                rc = proc.poll()
                if rc is not None:
                    return AgentResult(returncode=rc, stdout_path=stdout_path, last_message_path=last_message_path)

                if state_file is not None:
                    state = self._load_json(state_file, {})
                    if state.get("status") in terminal_statuses:
                        self._terminate_process_group(proc)
                        return AgentResult(returncode=0, stdout_path=stdout_path, last_message_path=last_message_path)

                if deadline is not None and time.monotonic() >= deadline:
                    self._terminate_process_group(proc)
                    return AgentResult(returncode=124, stdout_path=stdout_path, last_message_path=last_message_path)

                time.sleep(self.state_poll_seconds)

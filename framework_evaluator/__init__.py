"""
Framework Evaluator — 可复用的科研自动化框架评估 Agent 抽象包

核心能力：
1. 管理多项目评估流水线（Project → Smoke → E2E → Complete/Blocked）
2. 通过外部 LLM Agent（Codex / Claude / 任意 CLI Agent）执行 Smoke 与修复
3. 验证项目输出是否与当前 Topic Contract 对齐
4. 状态机持久化与自动推进
"""

from .topic import TopicConfig, TopicRenderer
from .project import Project, ProjectLoader, TodoQueue
from .state_machine import (
    Phase,
    Status,
    ProjectState,
    StateStore,
    RuntimeStateStore,
)
from .validator import ProjectValidator, ValidationResult
from .agent_runner import AgentRunner, CodexAgentRunner, AgentResult
from .prompts import PromptTemplate, PromptContext, SmokePrompt, RepairPrompt
from .e2e_runner import E2ERunner, E2EResult
from .orchestrator import Orchestrator, OrchestratorConfig, Dispatcher

__all__ = [
    "TopicConfig",
    "TopicRenderer",
    "Project",
    "ProjectLoader",
    "TodoQueue",
    "Phase",
    "Status",
    "ProjectState",
    "StateStore",
    "RuntimeStateStore",
    "ProjectValidator",
    "ValidationResult",
    "AgentRunner",
    "CodexAgentRunner",
    "AgentResult",
    "PromptTemplate",
    "PromptContext",
    "SmokePrompt",
    "RepairPrompt",
    "E2ERunner",
    "E2EResult",
    "Orchestrator",
    "OrchestratorConfig",
    "Dispatcher",
]

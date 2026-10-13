"""Prompt 模板 — 为外部 LLM Agent 生成结构化指令。

核心抽象：
- PromptTemplate 基类：声明 prompt 所需字段。
- SmokePrompt：初始会话指令（smoke → dispatch e2e）。
- RepairPrompt：E2E 失败后的修复指令。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .topic import TopicConfig


@dataclass
class PromptContext:
    """生成 prompt 时需要的通用上下文。"""

    project_id: str
    project_name: str
    attempt: int
    unit_name: str
    automation_dir: Path
    repo_root: Path
    topic: TopicConfig
    smoke_cmd: str
    e2e_cmd: str
    provider_config: Path | str
    semantic_source: Path | str
    state_file: Path
    failure_mode: str = ""


class PromptTemplate(ABC):
    @abstractmethod
    def render(self, ctx: PromptContext) -> str:
        ...


class SmokePrompt(PromptTemplate):
    """初始 Smoke 会话 Prompt。

    要求 Agent：
    1. 在当前 headless 会话内同步完成 smoke。
    2. 检查任务输入是否与当前 topic contract 对齐。
    3. 如通过，在同一个会话内提交 systemd e2e 任务并停止。
    4. 如失败，读报错、做最小修复、重试一次。
    5. 最终将结构化 JSON 写入 state_file。
    """

    def render(self, ctx: PromptContext) -> str:
        return f"""你在 {ctx.repo_root} 工作。

只处理项目 {ctx.project_id} {ctx.project_name}。
当前自动化目录是：{ctx.automation_dir}
只允许读取这个自动化目录下的运行文件，不要读取仓库里其它 `todo` 或其它项目状态。

固定规则：
- 你必须先在当前这轮 headless 会话内同步阻塞完成 smoke。
- smoke 阶段还必须检查“当前项目真正的 e2e 输入”是否已经对齐当前 topic contract；如果没有对齐，先做最小必要修改。
- 如果 smoke 通过，必须在同一个 headless 会话里继续提交 systemd --user 的 e2e 任务，然后停止。
- 如果 smoke 失败：
  - 先读报错
  - 做最小必要修复
  - 重试一次 smoke
- 如果 smoke 最终失败，不允许提交任何 systemd --user 命令。
- 必须使用 --yolo 模式运行。
- Provider 来源固定为 {ctx.provider_config}
- Semantic Scholar 来源固定为 {ctx.semantic_source}

请先执行下面这条 smoke 命令：
{ctx.smoke_cmd}

如果 smoke 通过，再原样提交这条 e2e 命令：
{ctx.e2e_cmd}

当前 topic contract：
- topic 名称：{ctx.topic.label}
- 数据集根目录固定为：{ctx.topic.dataset_root}
- topic contract 文件固定为：{ctx.topic.contract_file}

只有在以下前提都满足时，才允许 dispatch e2e：
- 你已经确认后续 e2e 跑的是当前 topic，不是旧 topic
- 你已经让当前项目知道数据集位置或 topic contract 文件位置
- 如需修改，只做最小必要修改

无论结果如何，都把结构化 JSON 写到：
{ctx.state_file}

JSON 至少包含：
- project_id
- project_name
- phase=smoke 或 e2e
- status=smoke_failed 或 e2e_submitted
- attempt={ctx.attempt}
- smoke_command
- unit={ctx.unit_name}
- e2e_command
- submit_command
- topic_label
- topic_dataset_root
- topic_contract_file
- topic_ready=true 或 false
- acceptance_summary
- patched_files
- summary
""".strip()


class RepairPrompt(PromptTemplate):
    """E2E 失败后的修复会话 Prompt。

    要求 Agent：
    1. 查看失败 unit 日志。
    2. 优先修配置和脚本，不随意改外层 docker 入口。
    3. 如可修复，在同一个会话内提交新的 systemd e2e 任务并停止。
    4. 如无法继续，将项目标记为 blocked。
    """

    def render(self, ctx: PromptContext) -> str:
        failure_hint = ""
        if ctx.failure_mode == "block_on_failure":
            failure_hint = "\n- 这是一个合成失败测试用例。不要重新提交 e2e，直接把项目标记为 blocked。\n"

        return f"""你在 {ctx.repo_root} 工作。

只处理项目 {ctx.project_id} {ctx.project_name} 的 e2e 失败修复。
当前自动化目录是：{ctx.automation_dir}
只允许读取这个自动化目录下的运行文件，不要读取仓库里其它 `todo` 或其它项目状态。

固定规则：
- 先查看失败 unit 日志。
- 优先修配置和脚本，不随意改外层 docker 入口。
- 如果可修复，必须在同一个 headless 会话里提交新的 systemd --user e2e 任务，然后停止。
- 如果无法继续，请把项目标成 blocked。
- 必须使用 --yolo 模式运行。
- 修复后提交出去的 e2e 必须继续保持当前 topic，不允许回退到旧 topic。
- 当前 topic 名称：{ctx.topic.label}
- 数据集根目录固定为：{ctx.topic.dataset_root}
- topic contract 文件固定为：{ctx.topic.contract_file}
{failure_hint}

新的 e2e 提交命令如下：
{ctx.e2e_cmd}

最终把结构化 JSON 写到：
{ctx.state_file}

JSON 至少包含：
- project_id
- phase=e2e
- status=e2e_resubmitted 或 blocked
- attempt={ctx.attempt}
- previous_unit={ctx.unit_name}
- unit={ctx.unit_name}
- topic_label
- topic_dataset_root
- topic_contract_file
- patched_files
- summary
""".strip()

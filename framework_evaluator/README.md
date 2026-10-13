# Framework Evaluator — 科研自动化框架评估 Agent 抽象

## 背景

在运行 `BabyLM-10M` 等七框架端到端评估时，原始代码散落在 `automation/scripts/` 下：

- `orchestrator.py` — 状态机编排器
- `validate_project_alignment.py` — 项目对齐验证器
- `run_e2e_once.py` — E2E 单次运行器
- `topic_runtime.py` — Topic 契约与渲染

这些脚本虽然能工作，但**强耦合于 Codex CLI、systemd-run、固定路径和 BabyLM 特定标记**。本包将其抽象为**通用、可替换、可扩展**的 Python 模块，方便后续：

1. 接入其他 Agent（Claude Code、OpenAI、本地模型）
2. 替换调度后端（不用 systemd-run，改用 cron、K8s Job、RQ 等）
3. 评估其他 topic（不限于 BabyLM）
4. 单元测试与独立部署

---

## 架构总览

```
framework_evaluator/
├── topic.py          # TopicConfig / TopicRenderer
├── project.py        # Project / ProjectLoader / TodoQueue
├── state_machine.py  # Phase / Status / ProjectState / StateStore / RuntimeStateStore
├── validator.py      # ProjectValidator / ValidationResult
├── agent_runner.py   # AgentRunner(ABC) / CodexAgentRunner
├── prompts.py        # PromptTemplate(ABC) / SmokePrompt / RepairPrompt
├── e2e_runner.py     # E2ERunner / E2EResult
├── orchestrator.py   # Orchestrator / OrchestratorConfig / Dispatcher
└── README.md
```

### 数据流

```
TodoQueue ──► Orchestrator.step()
                   │
                   ├──► [无状态 / smoke_failed] ──► AgentRunner.run(SmokePrompt)
                   │                                    │
                   │                                    ▼
                   │                              [e2e_submitted]
                   │                                    │
                   ├──► [e2e_running] ──► E2ERunner.run()
                   │                         │
                   │                         ▼
                   │                   [e2e_passed] ──► completed
                   │                         │
                   │                         ▼
                   │                   [e2e_failed] ──► AgentRunner.run(RepairPrompt)
                   │                                    │
                   │                                    ▼
                   │                              [resubmitted/blocked]
                   │
                   └──► [completed/blocked] ──► TodoQueue.mark_complete()
                                                   │
                                                   ▼
                                             dispatch_followup()
```

---

## 核心抽象

### 1. Topic Contract (`topic.py`)

```python
from framework_evaluator import TopicConfig, TopicRenderer

topic = TopicConfig(
    label="BabyLM-10M",
    dataset_root=Path("/data/BabyLM-2026-Strict-Small"),
    contract_file=Path("/docs/contract.md"),
)

# 渲染命令模板
cmd = TopicRenderer.render_for(
    "python run.py --dataset __TOPIC_DATASET_ROOT__",
    topic,
)
```

### 2. 项目验证 (`validator.py`)

```python
from framework_evaluator import ProjectValidator, TopicConfig

validator = ProjectValidator(
    topic=topic,
    forbidden_markers=["sklearn_iris", "load_digits"],  # 防止回退到旧 topic
    provider_config="/secrets/provider.toml",
    semantic_source="/secrets/semantic_scholar.env",
)

result = validator.validate(
    project_id="04",
    phase="e2e",
    files=[Path("output/run_manifest.json"), Path("output/report.md")],
    raw_e2e_cmd="...",
    rendered_e2e_cmd="...",
)
print(result.ok, result.missing_files, result.forbidden_hits)
```

### 3. Agent 执行器 (`agent_runner.py`)

```python
from framework_evaluator import CodexAgentRunner, AgentRunner

# 默认实现：Codex
codex = CodexAgentRunner(
    codex_bin=Path("/usr/local/bin/codex"),
    codex_home=Path("/tmp/codex_home"),
    repo_root=Path("/workspace"),
    timeout_seconds=3600,
)

# 未来可替换为 ClaudeAgentRunner、LocalLLMAgentRunner 等
```

### 4. 编排器 (`orchestrator.py`)

```python
from framework_evaluator import Orchestrator, OrchestratorConfig

config = OrchestratorConfig(
    repo_root=Path("/workspace"),
    automation_dir=Path("/workspace/automation"),
    projects_file=Path("/workspace/automation/projects.yaml"),
    todo_file=Path("/workspace/automation/todo.md"),
    state_dir=Path("/workspace/automation/state"),
    runs_dir=Path("/workspace/automation/runs"),
    runtime_state_file=Path("/workspace/automation/state/runtime.json"),
    codex_home_dir=Path("/tmp/codex_home"),
    codex_bin=Path("/usr/local/bin/codex"),
    e2e_runner_script=Path("/workspace/run_e2e.py"),
    orchestrator_script=Path(__file__),
)

orch = Orchestrator(
    config=config,
    topic=topic,
    agent_runner=codex,
    e2e_runner=e2e_runner,  # E2ERunner 实例
)

orch.step()   # 推进一个项目的一个状态步
```

---

## 状态机

| 状态 | 含义 | 下一步动作 |
|------|------|-----------|
| `empty` | 项目尚未开始 | `handle_initial_session` |
| `smoke_failed` | Smoke 未通过 | `handle_initial_session` |
| `e2e_submitted` | 已提交 systemd e2e | 等待执行完成，检查 metadata |
| `e2e_running` | E2E 正在运行 | 同上 |
| `e2e_passed` | E2E 成功 | 标记 complete，触发下一个项目 |
| `e2e_failed` | E2E 失败 | `handle_e2e_repair` |
| `e2e_resubmitted` | 修复后重新提交 | 等待执行完成 |
| `completed` | 项目完成 | — |
| `blocked` | 无法修复，阻塞 | — |

---

## Prompt 模板

- **SmokePrompt**：要求 Agent 在 headless 会话内完成 smoke，确认 topic 对齐，然后 dispatch e2e。
- **RepairPrompt**：要求 Agent 查看失败日志，做最小修复，重新提交 e2e 或标记 blocked。

两个模板都接受 `PromptContext` 统一上下文，便于替换为其他 LLM 的 prompt 风格。

---

## 扩展指南

### 接入新的 LLM Agent

继承 `AgentRunner`：

```python
class ClaudeAgentRunner(AgentRunner):
    def run(self, prompt, work_dir, label, state_file=None, terminal_statuses=None):
        # 调用 claude exec 或其他 CLI
        ...
```

### 替换调度器

继承 `Dispatcher`：

```python
class KubernetesDispatcher(Dispatcher):
    def dispatch_followup(self, trigger, source_project_id, next_project_id, ...):
        # 创建 K8s Job 而非 systemd-run
        ...
```

### 自定义验证规则

在构造 `ProjectValidator` 时传入不同的 `forbidden_markers` 和 `required_keys`。

---

## 与原始代码的对应关系

| 原始文件 | 抽象模块 | 说明 |
|---------|---------|------|
| `topic_runtime.py` | `topic.py` | 去除硬编码默认路径，增加 `from_env` |
| `orchestrator.py` (上半部分) | `project.py` | 项目加载、todo 队列解析 |
| `orchestrator.py` (状态逻辑) | `state_machine.py` | 状态枚举、ProjectState dataclass、JSON 持久化 |
| `validate_project_alignment.py` | `validator.py` | 扫描逻辑抽象为 `ProjectValidator`，可配置 forbidden markers |
| `orchestrator.py` (codex run) | `agent_runner.py` | 抽象为 `AgentRunner` 接口，`CodexAgentRunner` 为默认实现 |
| `orchestrator.py` (prompt) | `prompts.py` | `initial_prompt` → `SmokePrompt`，`repair_prompt` → `RepairPrompt` |
| `run_e2e_once.py` | `e2e_runner.py` | 单次 E2E 执行与验证调用 |
| `orchestrator.py` (主循环) | `orchestrator.py` | `Orchestrator` 类，组合所有模块，支持 `Dispatcher` 替换 |

---

## 待办 / 进一步抽象

- [ ] `E2ERunner.run()` 中目前对 `ProjectValidator` 的调用是占位（files 列表未传入）。需要把每个项目的 `smoke_files` / `result_files` 规则从 `validate_project_alignment.py` 的 `PROJECT_RULES` 迁移到 `Project` dataclass 或外部配置文件中，使 `E2ERunner` 可以真正通用。
- [ ] 增加 `retry_policy` 配置（最大重试次数、指数退避）。
- [ ] 增加 `notification` 钩子（E2E 完成/失败时发 webhook）。
- [ ] 为 `Orchestrator` 增加 `dry_run` 模式，只打印命令不执行。

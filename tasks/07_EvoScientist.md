# Project 7: EvoScientist

- Status: Pending
- Project Path: `EvoScientist/`
- Dependency Guide: `依赖配置指南/ChatGPT-EvoScientist端到端部署.md`
- Docker Reference: `docs/tutorials/docker_file_instruction.md`
- Minimal Input: 在 EvoScientist 工作区中输入"sklearn digits/iris 轻量分类器改进"研究任务，并启用必要 EvoSkills / research skills。
- Required E2E Flow: EvoScientist startup → provider configured → research skill/agent invocation → idea/plan → experiment/code execution → analysis/figure → write-up/final report → optional memory/skill update.
- Pre-E2E Checks: official Docker image or local package startup check; `EvoSci` help/startup check; provider config check; workspace writeability check; Node/npx check for MCP if used; LaTeX check if paper PDF is required.
- Acceptance: 从最终镜像启动新容器后，EvoScientist 能通过 `EvoSci` 官方镜像/CLI 和配置的 provider 完成一次最小科研任务闭环；验收产物按 EvoScientist 原生 workspace/session 形态记录，包括 `EvoSci config` 使用的 provider/workdir、workspace 中的 session/project 记录、agent/tool 调用日志、idea/plan 或 research skill 输出、生成/执行的实验代码、结果/分析/图表或汇总、final report / write-up，以及启用 EvoSkills、memory、MCP、Telegram/STT/OAuth 等能力时对应的技能、memory、session 和运行日志路径。
- Image: TBD
- Image ID: TBD
- Verification: Pending
- Verification Command: TBD
- Min E2E Command: TBD
- Report: `Report/EvoScientist_report.md`
- Notes: 优先考虑官方镜像 `ghcr.io/evoscientist/evoscientist:latest`；如需 LaTeX、OAuth、STT 或 EvoSkills，记录派生镜像原因。

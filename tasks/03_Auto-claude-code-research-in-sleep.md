# Project 3: Auto-claude-code-research-in-sleep / ARIS

- Status: Pending
- Project Path: `Auto-claude-code-research-in-sleep/`
- Dependency Guide: `依赖配置指南/ChatGPT-Auto-claude框架部署指南.md`
- Docker Reference: `docs/tutorials/docker_file_instruction.md`
- Minimal Input: 使用"sklearn digits/iris 轻量分类器改进"研究主题，作为 `/research-pipeline` 或等价 workflow 的输入。
- Required E2E Flow: idea discovery → experiment bridge / minimal experiment execution → auto-review loop → paper writing → optional LaTeX/PDF output.
- Pre-E2E Checks: skill/CLI availability check; configured executor/reviewer runner check; MCP/reviewer bridge check if used; LaTeX check if PDF is required; API environment variable presence check.
- Acceptance: 从最终镜像启动新容器后，ARIS 能按自己的 skill/workflow 协议完成 `/research-pipeline` 或拆分的 `/idea-discovery` → `/experiment-bridge` / `/run-experiment` / `/experiment-queue` → `/auto-review-loop` → `/paper-writing` 闭环；验收产物按项目原生命名记录，包括 `RESEARCH_BRIEF.md`（如使用文档输入）、`idea-stage/IDEA_REPORT.md`、`refine-logs/FINAL_PROPOSAL.md`、`refine-logs/EXPERIMENT_PLAN.md`、实验执行日志/队列状态、`review-stage/AUTO_REVIEW.md` 或等价 critique、`NARRATIVE_REPORT.md`、`PAPER_PLAN.md`、`MANIFEST.md`、`PAPER_IMPROVEMENT_LOG.md`（如启用改进循环）以及 `paper/` 下的 LaTeX 源、编译日志和 `paper/main.pdf`（如启用编译）。
- Image: TBD
- Image ID: TBD
- Verification: Pending
- Verification Command: TBD
- Min E2E Command: TBD
- Report: `Report/Auto-claude-code-research-in-sleep_report.md`
- Notes: ARIS 本体偏 skill/workflow；镜像应固化其所需 runner、LaTeX、Python 实验环境和必要 MCP/CLI。

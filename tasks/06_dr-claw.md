# Project 6: Dr. Claw / dr-claw

- Status: Pending
- Project Path: `dr-claw/`
- Dependency Guide: `依赖配置指南/ChatGPT-Dr._Claw_端到端配置.md`
- Docker Reference: `docs/tutorials/docker_file_instruction.md`
- Minimal Input: 在 Research Lab / Auto Research / CLI-equivalent path 中输入"sklearn digits/iris 轻量分类器改进"研究 brief。
- Required E2E Flow: service startup → agent backend configured → research brief → pipeline/tasks → auto research execution → experiment/result artifacts → publication/write-up output.
- Pre-E2E Checks: Node/npm check; backend service health check; web/API endpoint check; selected agent backend minimal prompt check; database/sqlite check; API environment variable presence check.
- Acceptance: 从最终镜像启动新容器后，dr-claw 服务和至少一个执行后端可用，并能按自己的 Research Lab / Auto Research 五阶段目录完成一次最小流程；验收产物按 dr-claw 原生命名记录，包括 `.pipeline/docs/research_brief.json`、`.pipeline` / Task Master 任务状态或 pipeline 配置、`Survey/reports/`、`Survey/references/`、`Ideation/ideas/`、`Ideation/references/`、`Experiment/core_code/`、`Experiment/analysis/`、阶段 logs/JSON、`Publication/paper/`（含 `main.pdf` 时记录）、以及 `Promotion/slides/`、`Promotion/audio/`、`Promotion/video/`、`Promotion/homepage/` 中本次流程实际生成的宣传/展示产物。
- Image: TBD
- Image ID: TBD
- Verification: Pending
- Verification Command: TBD
- Min E2E Command: TBD
- Report: `Report/dr-claw_report.md`
- Notes: 可选择 Claude Code、Gemini CLI、Codex 或 OpenRouter 路径；报告可记录所选后端、变量名、env 文件路径和值，包括明文 key，但不得上传或外传。

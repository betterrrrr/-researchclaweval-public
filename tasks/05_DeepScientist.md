# Project 5: DeepScientist

- Status: Pending
- Project Path: `DeepScientist/`
- Dependency Guide: `依赖配置指南/ChatGPT-DeepScientist_端到端配置.md`
- Docker Reference: `/home/jin/researchclaweval/docker_file_instruction.md`
- Minimal Input: 在新 quest/project 中输入"sklearn digits/iris 轻量分类器改进"研究任务，并限制为最小实验轮次。
- Required E2E Flow: runner available → `ds doctor` → create quest/project → baseline/context setup → idea → experiment → analysis campaign → write/finalize artifacts.
- Pre-E2E Checks: Node/npm check; Python runtime check; `ds --help`; `ds doctor` for selected runner; selected runner CLI minimal prompt check; API/login state presence check.
- Acceptance: 从最终镜像启动新容器后，DeepScientist 能通过所选 runner 完成一个最小 one-repo-per-quest 流程；验收产物按 DeepScientist quest 布局记录，包括 quest 根目录中的 `quest.yaml`、`brief.md`、`plan.md`（Research Map）、`status.md`、`SUMMARY.md`，以及 `artifacts/idea/objective_contract.md`、`artifacts/idea/candidates.md`、`artifacts/idea/selected_idea.md` 或等价 idea 产物、`baselines/`、`experiments/main/`、`experiments/analysis/`、`artifacts/runs/`、`artifacts/reports/`、`literature/`、`handoffs/`、`paper/`、`paper/selected_outline.json` / `paper/evidence_ledger.*`（若进入写作线）和 finalize/handoff 记录。
- Image: TBD
- Image ID: TBD
- Verification: Pending
- Verification Command: TBD
- Min E2E Command: TBD
- Report: `Report/DeepScientist_report.md`
- Notes: DeepScientist 依赖外部 runner（Codex / Claude / Kimi / OpenCode 等）；报告记录所选 runner、变量名、登录态路径和必要配置值，包括明文 key，但不得上传或外传。

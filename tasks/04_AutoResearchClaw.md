# Project 4: AutoResearchClaw

- Status: Pending
- Project Path: `AutoResearchClaw/`
- Dependency Guide: `依赖配置指南/ChatGPT-AutoResearchClaw_端到端配置.md`
- Docker Reference: `docs/tutorials/docker_file_instruction.md`
- Minimal Input: `researchclaw run --topic "sklearn digits/iris 轻量分类器改进" --auto-approve` 或项目支持的等价最小 topic 输入。
- Required E2E Flow: topic intake → literature/context → idea/proposal → experiment plan → sandbox/docker experiment → figure/table generation → paper/report writing → quality/review stage if enabled.
- Pre-E2E Checks: `researchclaw --help`; `researchclaw doctor`; `researchclaw validate`; Python import check; sandbox/docker executor check; API environment variable presence check.
- Acceptance: 从最终镜像启动新容器后，`researchclaw` 能完成自己的 23-stage / 8-phase pipeline 的最小自动研究流程；验收产物按 AutoResearchClaw 原生命名记录，包括 `artifacts/rc-YYYYMMDD-HHMMSS-<hash>/` 运行目录、`pipeline_summary.json` / stage 状态、topic/literature/synthesis/design 阶段输出、实验 sandbox/Docker 生成代码和 metrics、`charts/`、`paper_draft.md`、`paper.tex`、`references.bib`、`verification_report.json`、`reviews.md` 以及 `deliverables/` 中最终可交付文件。
- Image: TBD
- Image ID: TBD
- Verification: Pending
- Verification Command: TBD
- Min E2E Command: TBD
- Report: `Report/AutoResearchClaw_report.md`
- Notes: 优先显式设置 `sandbox` 或 `docker` 实验模式，不依赖文档中可能漂移的默认值。

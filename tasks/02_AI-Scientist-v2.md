# Project 2: AI-Scientist-v2

- Status: Pending
- Project Path: `AI-Scientist-v2/`
- Dependency Guide: `依赖配置指南/ChatGPT-AI-Scientist-v2_端到端运行.md`
- Docker Reference: `/home/jin/researchclaweval/docker_file_instruction.md`
- Minimal Input: 一个包含 Title / Keywords / TL;DR / Abstract 的最小 workshop topic markdown，主题使用"sklearn digits/iris 轻量分类器改进"。
- Required E2E Flow: idea generation → ideas JSON → BFTS / minimal experiment run → plot aggregation / result analysis → citation/write-up → review or PDF output if feasible.
- Pre-E2E Checks: Python import check; `requirements.txt` install check; PyTorch/CUDA visibility check; `perform_ideation_temp_free.py --help` or equivalent entry check; LaTeX/pdflatex/chktex check; API environment variable presence check.
- Acceptance: 从最终镜像启动新容器后，AI-Scientist-v2 能基于最小 workshop topic 运行自己的 ideation → BFTS / agent tree search → experiment → writeup/review 链路；验收产物按项目原生命名记录，包括 `ideas/*.json` 或 ideation 输出、`launch_scientist_bfts.py` 为该 idea 创建的实验目录、`idea.md`、`token_tracker.json`、`token_tracker_interactions.json`、`logs/0-run/baseline_summary.json`、`logs/0-run/ablation_summary.json`、`logs/0-run/research_summary.json`、`best_solution*.py` 或等价 best/generated solution code、plot/figure 输出、`paper/main.tex` / `paper/main.pdf`（若成功编译）以及 `review_*.json` / `review_img_cap_ref.json` 或等价 LLM review 记录。
- Image: TBD
- Image ID: TBD
- Verification: Pending
- Verification Command: TBD
- Min E2E Command: TBD
- Report: `Report/AI-Scientist-v2_report.md`
- Notes: 默认配置可能依赖 OpenAI、AWS Bedrock/Claude、Gemini、S2 等；报告可记录变量名、env 文件路径和值，包括明文 key，但不得上传或外传。

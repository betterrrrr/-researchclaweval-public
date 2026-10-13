# GAVE2 Smoke Test Register

> 约束：只做 smoke test，不做全量训练，不做正式提交。

| 问题项 | 来源 | Smoke 检查 | 适用框架 | 状态 |
|---|---|---|---|---|
| 旧 workspace / old topic 混入 | 历史 report | clean run root + 新工作区 + wrapper 禁止旧入口标记 | 全部 | GREEN |
| dataset 仅挂到 /data | 历史 report | 同时检查 `/data/gave2/task2` 与 workspace-local dataset path | 全部 | GREEN |
| Dr. Claw 依赖与路径假设 | `dr-claw_report.md` | `python3` 导入 `sklearn/numpy/pandas/matplotlib`，并检查 `/workspace/dr-claw/server/cli-chat.js` | Dr. Claw | GREEN |
| EvoScientist phase2 / CUDA 路线 | 七框架 serial upgrade report | smoke 中要求 runtime-ready 可见 GAVE2 输入，且 preflight 要求 `nvcr.io/nvidia/pytorch:25.11-py3` 镜像存在 | EvoScientist | GREEN |
| 统一合同分发 | 当前 GAVE2 适配 | 每个工作区都要看到本框架原生入口 + 共享 docs + 合同 | 全部 | GREEN |
| 状态登记与验收 | 当前 GAVE2 适配 | 每个 smoke run 写 `state.json` + `smoke_manifest.json`，串行汇总到 `serial_summary.md` | 全部 | GREEN |

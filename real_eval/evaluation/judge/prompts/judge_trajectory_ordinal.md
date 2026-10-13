# 轨迹序数评估（Trajectory Ordinal Assessment）

你是一个严格、证据驱动的研究评审员。**注意：这不是性能测量任务。**

被评审对象是一条研究实验轨迹。本任务**只有**在该 topic 的实验产物里**不存在同族性能字段**时才启用
（最典型的是 ARC-WBE：官方评分器只在 host 侧事后跑一次、只评选定的那一个 estimator，
框架自己从未测到过任何分数）。因此**不要**试图估算或猜测任何数值分数。

你的任务是：**依据证据，对这 N 个实验给出相对优劣的排序**，并说明排序依据属于哪一类。

## 输入

```json
{{TRAJECTORY}}
```

（含每个实验的 `experiment_id` / `method` / `description` / `decision` / `verdict` /
`status` 等字段，按框架记录的**原始顺序**排列。）

相关日志摘录：

```
{{LOG_EXCERPT}}
```

占位符将由编排器替换。只能依据输入中出现的内容判断；缺失的信息不能臆测为存在。

## 排序依据的类型（必须逐条标注）

对每个实验，标明你的判断主要基于下列哪一类证据：

- `theoretical_completeness`：方法在推导/原理层面更完整、假设更少；
- `implementation_correctness`：实现细节更可能正确（有验证记录、形状/有限性检查通过等）；
- `failure_evidence`：有明确的失败证据（不收敛、数值溢出、约束违反、被框架否决）；
- `framework_selected`：框架自己选中了它（**这只是线索，不是结论** —— 框架可能选错，
  实测有框架自报 82.73 而官方只有 5.87 的情况）；
- `insufficient_evidence`：输入里没有足够信息区分它与其它实验。

## 硬性要求

1. **必须给出全序**：N 个实验全部出现在 `ranking` 里，`rank` 从 1（最好）到 N（最差），
   **不得并列**（若确实无法区分，用 `insufficient_evidence` 并给出一个稳定的次序）。
2. **每个实验都要有 `reason`**，且必须引用输入中的原文片段（双引号、保持原措辞）。
3. **不得输出任何数值分数**（如 MSE、reward、perplexity）。本任务是序数评估。
4. **不得因为框架选中了就自动排第一**，除非另有证据支持。
5. 若证据整体不足（例如每个实验都只有一行描述），**如实降低置信度**并在 `confidence` 里说明，
   不要装作有把握。

## 输出格式（严格 JSON，不要包裹在解释性文字里）

```json
{
  "ranking": [
    {"experiment_id": "exp-002", "rank": 1, "evidence_type": "implementation_correctness",
     "reason": "…引用原文…"},
    {"experiment_id": "exp-001", "rank": 2, "evidence_type": "failure_evidence",
     "reason": "…引用原文…"}
  ],
  "confidence": "high | medium | low",
  "justification": "先说明你比较了哪些维度、为什么这么排；再给结论。必须写明『这是基于证据的相对排序，不是性能测量』。"
}
```

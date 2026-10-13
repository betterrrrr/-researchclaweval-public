# BabyLM-10M 七框架任务包装与分发指南

## 1. 文档目标

这份文档不是再讲一遍各框架怎么安装。

它只回答一件事：

**如果任务是 BabyLM-10M（Strict-Small），那么针对 7 个框架，应该怎样包装和分发任务，给它们提供什么材料，它们才更容易稳定地完成端到端实验。**

这里的“端到端实验”指的是同一条完整链路：

1. 理解任务约束
2. 恢复并运行 baseline
3. 提出一个受约束的新方案
4. 训练或改造模型
5. 跑官方评测
6. 产出可比较结果
7. 写出实验结论与交付物

---

## 2. 先说结论

**不要把 BabyLM-10M 直接当成一个开放式研究题目丢给 agent。**

这样做很容易跑偏。原因很简单：

- BabyLM 是强约束 benchmark，不是开放选题
- 这 7 个框架的原生输入契约差异很大
- 有的擅长一句 topic 展开
- 有的本质上需要结构化 brief
- 有的更适合 repo-first
- 有的更适合 benchmark-instance-first

所以正确做法不是“给 7 个框架统一一句 prompt”。

正确做法是先把任务压成一个统一的 **benchmark harness + task contract**，然后再把同一个任务合同翻译成不同框架能吃的输入形态。

一句话概括：

> **先统一任务，再适配框架。**

---

## 3. BabyLM-10M 的统一任务合同

下面这份合同建议作为所有框架共同看到的“源任务定义”。

```text
Task: BabyLM 2026 Strict-Small (10M words)

Goal:
Optimize the official BabyLM Strict-Small score under the official task rules.

Fixed rules:
- Use the official detoxified 10M BabyLM text-only dataset for the first pass.
- Do not exceed 10M training words.
- Do not exceed 10 epochs over the training data.
- Do not change the official task definition or evaluation protocol.
- Implement the model in HuggingFace Transformers, or export it to a HF-compatible repository.
- The model must support log-likelihood or pseudo-log-likelihood scoring.

Required workflow:
- Restore and verify a baseline first.
- Propose one constrained improvement direction.
- Run training or fine-tuning under the same rules.
- Run the official BabyLM strict evaluation pipeline.
- Compare with baseline using the same protocol.
- Produce a short technical report.

Required artifacts:
- runnable training code
- config files
- checkpoints
- official eval outputs
- collated submission JSON
- concise experiment report

Primary metric:
- official BabyLM Strict-Small evaluation score

Hard constraints:
- no private success metric as final criterion
- no silent data expansion
- no hidden protocol changes
```

这份合同的目的只有一个：

**先把“任务定义自由度”锁死。**

之后不同框架只允许在：

- 模型设计
- 训练细节
- 数据使用方式（仍在规则内）
- 实验计划
- 分析与报告

这些地方发挥。

---

## 4. 建议先准备的共享底座

这 7 个框架都不应该直接从零理解 BabyLM。

应该先给它们一个统一仓库，里面至少有下面这些东西。

### 4.1 统一仓库

建议名字：

```text
babylm_10m_harness/
```

建议目录：

```text
babylm_10m_harness/
  TASK.md
  README.md
  data/
  train/
  eval/
  scripts/
    run_train.sh
    run_eval_fast.sh
    run_eval_full.sh
    collate_submission.sh
    extract_score.py
  baselines/
  outputs/
  reports/
```

### 4.2 必须提前准备的材料

所有框架都建议共享下面这些材料：

1. **TASK.md**
   - 就是上面的统一任务合同
   - 所有 agent 都应该从这份文件读取任务边界

2. **baseline repo 或 baseline code**
   - 至少有一个能跑通的起点
   - 最好已经包含最小训练脚本与配置

3. **官方评测入口包装**
   - 用统一脚本调用 BabyLM 官方 strict eval
   - 不要让每个 agent 自己决定怎么评测

4. **统一打分抽取器**
   - 例如 `scripts/extract_score.py`
   - 统一输出一个字段，比如：

```json
{
  "babylm_strict_small_score": 0.4123
}
```

5. **统一交付物约定**
   - checkpoints 放哪里
   - eval 输出放哪里
   - 报告写到哪里
   - 最终 submission JSON 放哪里

6. **运行约束说明**
   - GPU 数量
   - 显存限制
   - 时间预算
   - 是否允许联网
   - 是否允许额外数据
   - 是否允许 teacher feedback / image-text data

### 4.3 分发原则

所有框架建议满足这三个原则：

- **同一个任务定义**
- **同一个 baseline 起点**
- **同一个评测脚本**

否则最后比较的是不同任务，不是不同框架。

---

## 5. 七个框架的推荐包装方式总览

| 框架 | 最佳包装方式 | 推荐程度 | 核心原因 |
|---|---|---:|---|
| DeepScientist | `startup_contract + baseline links + references + constraints` | 很高 | 它本来就是结构化 kickoff |
| AI-Researcher | `instance JSON + detailed idea/goal + references + repo path` | 中 | 开源工程入口更像 benchmark instance |
| The AI Scientist v2 | `topic markdown + harness repo` | 中 | 它先吃 topic file，再生 idea JSON |
| AutoResearchClaw | `topic + metric_key + metric_direction + repo` | 很高 | topic-first，但实验指标要显式钉住 |
| ARIS | `RESEARCH_BRIEF.md + base repo + /research-pipeline` | 很高 | 最适合 repo-first + brief 驱动 |
| EvoScientist | `long prompt + workdir + artifact contract` | 很高 | 它对输出契约非常敏感 |
| Dr. Claw | `research_brief.json + shared repo` | 很高 | 它内部本来就会把任务编译成多阶段 brief |

---

## 6. 每个框架应该怎么包装 BabyLM-10M

---

### 6.1 DeepScientist

#### 最推荐的包装方式

**不要只给一句 “do BabyLM”**。

DeepScientist 最适合的是：

- `Primary research request`
- `Baseline links`
- `Reference papers / repos`
- `Runtime constraints`
- `Objectives`
- 最终落成 `startup_contract`

也就是说，它最适合吃一个“结构化 kickoff 合同”。

#### 应该提供什么

必须提供：

1. `Primary research request`
   - 明确这是 BabyLM Strict-Small，不是开放研究
   - 写清 baseline → constrained improvement → official eval → report 这条链

2. `Baseline links`
   - 指向 `babylm_10m_harness/`
   - 或者指向已经能跑的 baseline repo

3. `Reference papers / repos`
   - BabyLM 官网
   - BabyLM guidelines
   - BabyLM eval repo
   - 相关 baseline 或 starter repo

4. `Runtime constraints`
   - GPU / 时间 / 数据预算 / 本地限制

5. `Objectives`
   - 建议 4~6 条
   - 每条都写成可以验证的动作

#### 推荐输入骨架

```text
Title:
BabyLM Strict-Small 10M Optimization

Primary research request:
Reproduce a trustworthy BabyLM Strict-Small baseline under the official 2026 rules, then test one constrained improvement direction without changing the benchmark, data budget, or evaluation protocol. Run the official strict evaluation pipeline and produce a concise technical report.

Baseline links:
- /workspace/babylm_10m_harness

Reference papers / repos:
- BabyLM guidelines
- BabyLM evaluation repo
- baseline implementation repo

Runtime constraints:
- use local data only
- do not exceed 10M training words
- do not exceed 10 epochs
- keep outputs under /artifacts
- final score must come from official strict eval

Objectives:
- restore and verify the baseline
- run one constrained improvement
- execute official evaluation
- compare baseline vs improved model
- write a short report
```

#### 为什么这样包装最好

因为 DeepScientist 的启动机制本身就不是单纯 prompt，而是一个持续影响后续行为的 `startup_contract`。

你把任务合同写清，它后面更容易稳定地围绕同一个 benchmark 推进。

---

### 6.2 AI-Researcher

#### 最推荐的包装方式

AI-Researcher 概念上支持两种入口：

- 详细 idea description
- reference-based ideation

但开源工程入口更适合你给它一个 **instance JSON**。

所以 BabyLM 上最稳的方式不是“一句 topic”，而是：

- 一个 instance JSON
- 一个明确 goal
- 一个 baseline repo path
- 一组参考资料
- 一个硬约束列表

#### 应该提供什么

必须提供：

1. `instance_path` 对应的 JSON
2. `goal`
3. `baseline repo path`
4. `references`
5. `constraints`
6. `deliverables`

建议写进 JSON 的字段：

- task name
- benchmark scope
- baseline
- improvement space
- success criteria
- required outputs

#### 推荐输入骨架

```json
{
  "title": "BabyLM Strict-Small 10M Optimization",
  "goal": "Reproduce a BabyLM Strict-Small baseline and test one constrained improvement direction under the official 2026 rules.",
  "benchmark": "BabyLM 2026 Strict-Small",
  "repo_path": "/workspace/babylm_10m_harness",
  "baseline": "official or provided starter baseline",
  "references": [
    "BabyLM guidelines",
    "BabyLM evaluation repo"
  ],
  "constraints": [
    "<=10M training words",
    "<=10 epochs",
    "official strict evaluation only",
    "no benchmark modification"
  ],
  "deliverables": [
    "training code",
    "checkpoints",
    "official eval outputs",
    "score summary",
    "short report"
  ]
}
```

#### 为什么这样包装最好

AI-Researcher 更像“围绕一个研究实例自动展开”。

BabyLM 是 benchmark 任务，不适合让它先自由发散太多 idea。

所以对它来说，**实例化任务 > 自由 brainstorming**。

---

### 6.3 The AI Scientist v2

#### 最推荐的包装方式

它的最佳入口不是自由 prompt，而是一个 topic markdown。

所以你应该给它：

- `my_research_topic.md`
- 同时把 `babylm_10m_harness/` 作为实验底座放进工作目录

#### 应该提供什么

必须提供：

1. `Title`
2. `Keywords`
3. `TL;DR`
4. `Abstract`
5. 一个可访问的 baseline repo / harness repo

其中 `Abstract` 必须把这些事说清：

- 这是官方 BabyLM Strict-Small
- 目标是提升官方分数
- 不能改 benchmark
- 先恢复 baseline 再做改进
- 最终要跑官方评测

#### 推荐输入骨架

```markdown
# Title
Improving Sample Efficiency on BabyLM Strict-Small Under Official Constraints

# Keywords
BabyLM, language modeling, low-resource pretraining, sample efficiency, benchmark optimization

# TL;DR
Reproduce a BabyLM Strict-Small baseline and test one constrained improvement under the official 2026 rules.

# Abstract
This project studies how to improve the BabyLM Strict-Small score under the official 2026 rules. The task must remain unchanged: use the 10M-word budget, stay within 10 epochs, keep the official evaluation protocol, and produce a HuggingFace-compatible model. The project should first restore and verify a baseline in the provided harness repository, then explore one constrained improvement direction, run the official strict evaluation pipeline, and summarize the findings in a concise report.
```

#### 为什么这样包装最好

AI Scientist v2 会先从 topic file 生成 idea JSON，再继续往下跑。

如果 topic file 没把 benchmark 边界写死，它后面很容易把任务理解成开放研究方向。

---

### 6.4 AutoResearchClaw

#### 最推荐的包装方式

AutoResearchClaw 的外层接口很轻。

它可以从一句 topic 开始。

但在 BabyLM 这种任务上，只给一句 topic 还不够。

你最好同时给：

- `topic`
- `metric_key`
- `metric_direction`
- `repo path`
- 必要时再给 `domains`

#### 应该提供什么

必须提供：

1. 一个具体 topic
2. 显式主指标
3. 指标方向
4. harness repo 路径

推荐的 topic 要包含：

- benchmark 名字
- baseline-first
- improvement 受限
- official eval
- report

#### 推荐输入骨架

```text
Topic:
Improve BabyLM Strict-Small under the official 2026 rules by first reproducing a trustworthy baseline, then testing one constrained efficiency-oriented improvement, and finally producing official evaluation outputs and a concise report.

metric_key:
babylm_strict_small_score

metric_direction:
maximize

repo:
/workspace/babylm_10m_harness
```

#### 为什么这样包装最好

AutoResearchClaw 是 topic-first 没错。

但它后面会进入固定长流水线。

如果你不把 metric 和 repo 显式钉住，它就容易在“论文产出感”上很强，在“benchmark 对齐”上变松。

---

### 6.5 ARIS / Auto research with Claude Code in sleep

#### 最推荐的包装方式

ARIS 最适合 **brief + base repo**。

也就是说：

- 一个 `RESEARCH_BRIEF.md`
- 一个 `BASE_REPO=/workspace/babylm_10m_harness`
- 然后再用 `/research-pipeline`

#### 应该提供什么

必须提供：

1. `RESEARCH_BRIEF.md`
2. `base repo`
3. `official references`
4. 明确的 success criteria
5. 明确的 non-goals

`RESEARCH_BRIEF.md` 里建议写：

- Problem Statement
- Constraints
- Success Criteria
- Non-Goals
- Existing Results
- Deliverables

#### 推荐输入骨架

```markdown
# Problem Statement
The goal is not to invent a new benchmark. The goal is to improve BabyLM Strict-Small under the official 2026 rules.

## Constraints
- use the provided harness repo
- do not exceed 10M training words
- do not exceed 10 epochs
- use official strict evaluation
- keep outputs reproducible and local

## Success Criteria
- baseline is restored and verified
- one constrained improvement is tested
- official eval outputs are produced
- a score summary and short report are written

## Non-Goals
- no benchmark redesign
- no hidden data expansion
- no unofficial metric as final success criterion

## Deliverables
- code changes
- configs
- checkpoints
- eval outputs
- report
```

配套命令思路：

```text
BASE_REPO=/workspace/babylm_10m_harness
/research-pipeline "Optimize BabyLM Strict-Small under the official 2026 rules using the attached research brief and the base repository."
```

#### 为什么这样包装最好

ARIS 本质上非常适合“拿一个现成 repo 做定向改造”。

BabyLM 恰好就是这种任务。

它不适合被当成纯 ideation 题，而适合被当成“受约束的改造任务”。

---

### 6.6 EvoScientist

#### 最推荐的包装方式

EvoScientist 最适合：

- `--workdir /workspace/babylm_10m_harness`
- 一段长 prompt
- prompt 里把 artifact contract 写死

它不是那种最适合只给一句题目的系统。

#### 应该提供什么

必须提供：

1. `workdir`
2. 长 prompt
3. 明确输出路径
4. 明确最终评分来源
5. 明确不要做什么

#### 推荐输入骨架

```text
Use /workspace/babylm_10m_harness as the working repository.

Task:
Reproduce a trustworthy baseline for BabyLM Strict-Small under the official 2026 rules, then test one constrained improvement direction without changing the benchmark, data budget, or evaluation protocol.

Requirements:
- do not exceed 10M training words
- do not exceed 10 epochs
- use the official strict evaluation pipeline
- keep all outputs local and reproducible

Artifacts:
- write run summaries to /artifacts/results/summary.md
- write the extracted final score to /artifacts/results/score.json
- save official evaluation outputs under /artifacts/eval/
- write the final technical report to /artifacts/reports/final_report.md

Do not:
- redesign the benchmark
- use hidden extra data
- use an unofficial final metric
```

调用思路：

```text
EvoSci --workdir /workspace/babylm_10m_harness -p "<上面的长 prompt>"
```

#### 为什么这样包装最好

EvoScientist 对“你最终要它留下什么文件”很敏感。

所以它最适合把任务写成一个**执行契约**，而不是一个抽象题目。

---

### 6.7 Dr. Claw

#### 最推荐的包装方式

Dr. Claw 最适合吃结构化 `research_brief.json`。

也就是你先把 BabyLM 任务翻译成一个多阶段 brief，再让它在同一仓库上展开。

#### 应该提供什么

必须提供：

1. `research_brief.json`
2. harness repo 路径
3. survey references
4. experiment plan constraints
5. publication deliverables

建议 JSON 至少包含：

- `meta`
- `survey`
- `ideation`
- `experiment`
- `publication`

#### 推荐输入骨架

```json
{
  "meta": {
    "title": "BabyLM Strict-Small 10M Optimization",
    "objective": "Improve the official BabyLM Strict-Small score under the official 2026 rules."
  },
  "sections": {
    "survey": {
      "literature_scope": "BabyLM task setup, official evaluation, baseline implementations",
      "key_references": [
        "BabyLM guidelines",
        "BabyLM evaluation repo"
      ],
      "open_gaps": [
        "Which constrained improvement can improve score without violating task rules?"
      ]
    },
    "ideation": {
      "research_goal": "Restore baseline first, then test one constrained improvement.",
      "problem_framing": "This is a benchmark optimization task, not a benchmark redesign task.",
      "success_criteria": [
        "official evaluation outputs exist",
        "baseline and improved model are compared under the same protocol"
      ]
    },
    "experiment": {
      "dataset_or_data_source": "official detoxified BabyLM 10M dataset",
      "method_or_protocol": "use provided harness repo and official strict evaluation",
      "evaluation_plan": "extract a unified final score and summarize results"
    },
    "publication": {
      "paper_outline": "task setup, baseline, improvement, experiments, results, discussion",
      "figures_tables_plan": "baseline vs improved model comparison table",
      "artifact_plan": "configs, checkpoints, eval outputs, final report"
    }
  }
}
```

#### 为什么这样包装最好

Dr. Claw 本来就倾向把项目管理成多阶段研究空间。

所以 BabyLM 对它来说不该是“一句话任务”，而该是“结构化项目 brief”。

---

## 7. 最少要给所有框架的公共材料

无论你用哪个框架，下面这些东西都不该省。

### 7.1 必给

1. `TASK.md`
2. `babylm_10m_harness/` 仓库
3. baseline 代码或 baseline 分支
4. 官方 eval 包装脚本
5. score extractor
6. 输出目录规范
7. 硬约束说明

### 7.2 强烈建议给

1. 一份短的 `FAQ.md`
   - 什么不能改
   - 什么路径必须保留
   - 哪个 score 算最终 score

2. 一份 `BASELINE_STATUS.md`
   - baseline 当前能不能跑
   - 已知 bug
   - 当前最可信结果是多少

3. 一份 `RUNBOOK.md`
   - 训练命令
   - 评测命令
   - 结果提取命令

这三样东西会明显降低 agent 在环境和协议上浪费的时间。

---

## 8. 不同框架不该统一成同一种输入

这是这份文档最重要的一句提醒。

**不要把 7 个框架都统一喂成同一种短 prompt。**

原因：

- DeepScientist 吃结构化 kickoff 合同更稳
- AI-Researcher 更像吃 instance JSON
- AI Scientist v2 更像吃 topic markdown
- AutoResearchClaw 吃 topic，但要把 metric 钉住
- ARIS 吃 brief + base repo 最稳
- EvoScientist 吃执行契约式长 prompt 最稳
- Dr. Claw 吃 research_brief.json 最稳

统一的是任务合同。

不统一的是外层输入壳。

---

## 9. 推荐的实际分发方式

如果 7 个框架都在独立 Docker 容器里，推荐这样分发：

- 所有框架共享同一个 `origin` 仓库历史
- 每个框架拿到自己的独立 worktree 或 clone
- 每个框架只改自己的分支
- 数据与官方 eval 目录只读挂载
- artifacts 分开写
- 最终由统一 orchestrator 重跑评测并汇总

也就是说：

- **共享任务定义**
- **共享 baseline**
- **共享评测协议**
- **不共享可写 working tree**

---

## 10. 最终建议

如果你的目标是：

**让 7 个框架在 BabyLM-10M 上做一轮真正可比的端到端实验**，

那最好的做法不是继续打磨 prompt。

最好的做法是：

1. 先把 BabyLM-10M 做成统一 harness
2. 把任务合同写进 `TASK.md`
3. 把 baseline、eval、score extractor、输出目录全部固定
4. 再把同一个任务合同翻译成 7 种输入格式

这样做的好处是：

- 框架差异只体现在“如何思考和执行”
- 不体现在“如何理解任务”
- 结果更可比
- 失败原因更容易定位

一句话收尾：

> **BabyLM 这种 benchmark 任务，关键不是让 agent 自由发挥，而是先把边界钉死，再让它在边界内优化。**

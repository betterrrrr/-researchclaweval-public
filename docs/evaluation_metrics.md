# 评测指标口径（12 项 · 权威定义）

把 12 项指标固化成**可复现流程**，目标是 **140 个格子（7 框架 × 5 topic × 4 模型）全部出满**，
不因"某个 run 没产出"而缺席。代价是取值基础不齐 —— 所以**每个值都必须带 `basis`**。
指标统一归一化到 **[0,1]**，但**不出综合总分**。

配套实现：

| 环节 | 文件 |
|---|---|
| 轨迹提取 + b0/bT/AUP/UR + 归一化（确定性，无 LLM） | `automation/scripts/trajectory_metrics.py` |
| 归一化锚点（**显式可审计**） | `automation/scripts/metric_anchors.json` |
| 裁判 AI：轨迹序数评估（arc）+ ED 判簇 | `automation/scripts/trajectory_judge.py` |
| 七维判官（已是 [0,1]） | `real_eval/evaluation/judge/orchestrator.py` |
| 汇总成一张表 | `automation/scripts/evaluation_metrics_report.py` |

---

## §1 指标总览

| # | 指标 | 全称 | 归一化前 | 归一化后 |
|---|---|---|---|---|
| 1 | **b0** | Initial Performance | 任务原始尺度 | **[0,1]** 锚点归一 |
| 2 | **bT** | Final Performance | 任务原始尺度 | **[0,1]** 锚点归一 |
| 3 | **AUP** | Area Under Progress Curve | 已是 [0,1] | 不变 |
| 4 | **UR** | Utility Ratio | 已是 [0,1] | 不变 |
| 5 | **ED** | Exploration Diversity | 已是 [0,1] | 不变 |
| 6–12 | **PQ / PEA / ER / OU / ECC / SC / CC** | 七维判官 | 已是 [0,1] | 不变 |

> **归一化只作用于 b0/bT。** 其余 10 个按构造或按判官锚点已经是绝对 [0,1]，
> 再归一化是空操作，只会增加一个出错的地方。

### 1.1 `basis`：每个值必须标注取值基础

| basis | 含义 | 解读边界 |
|---|---|---|
| `trace_metric` | 轨迹里的**同族性能字段**，纯算术 | **性能尺度**，同 topic 内跨 run 可比 |
| `judge_ordinal` | 裁判 AI 的**序数排序**映射到 [0,1] | ⚠️ **非性能测量**，不可与性能尺度并列解读 |
| `judge_cluster` | 裁判 AI 判定 approach 重复度 | 计数 |
| `judge_7dim` | 七维判官语义评分 | 跨框架可比（**CC 例外**，见 §5） |
| `judge_7dim_substituted(...)` | 七维判官，但**至少一件产物用了替身**（如契约 `final_report.md` 缺失，用框架自己写的 `paper.md` 顶） | ⚠️ **与四件齐全的判官分不可直接并列**；替身清单写在括号里，出处见该 run 的 `judge_provenance.substitutions` |
| `official_final` | host 评分器官方终值，**多数格子有但并非全部**（权威矩阵为 **95/100** 有有效分） | 官方口径，独立成列 |
| `basis_official`（**2026-10-12 新增**） | `official_scorer` / `framework_self_reported` / `manual_record` / `none` | **判据在 `score_source` 字段里，不在值的大小里**。BabyLM 天生是 `framework_self_reported`（官方评分器就是读 trace 取最小有限值），**不得与 `official_scorer` 并列宣称官方** |

---

## §2 轨迹指标（b0 / bT / AUP / UR）

### 2.1 方向表

| topic | 官方指标 | 方向 |
|---|---|---|
| arc | `adjusted_final_layer_score` | ↓ |
| babylm | `validation_perplexity` | ↓ |
| mc | `Reward Mean` | ↑ |
| psydef | macro-F1(1–8) | ↑ |
| tdc | `macro_average_auroc` | ↑ |

统一翻成「越大越好」：`v_i = s · raw_i`，`s = +1`（↑）或 `-1`（↓）。

### 2.2 公式

N 个有效实验点（i 从 0），`B_i` 为 best-so-far：

```
v_i = s · raw_i                          # 统一方向
b0  = v_0                                # 初始性能 = 第一个实验
B_i = max(v_0 … v_i)                     # best-so-far 轨迹
bT  = B_{N-1}                            # 最终性能 = 轨迹最佳
AUP = mean_i (B_i - b0) / (bT - b0)      # 仅当 bT > b0
UR  = #{i≥1 : v_i > B_{i-1}} / (N-1)     # 严格突破此前最优的比例
```

**边界规则**：

1. **横轴 = 实验序号**（不依赖时间戳，覆盖 100%）。
2. **`bT == b0`（全程无提升）时 AUP = 0**，并标 `flat_trajectory: true`。
   0 在这里**唯一地**表示「一次都没进步」：若只在最后一轮进步，AUP = 1/N > 0，恒大于 0，
   两者不会混淆。实测 **73/154（47%）** 的可算轨迹是平坦的 —— 若记 null 会造成大面积缺失。
   （`flat_trajectory` 标志仍保留，便于单独统计。）
3. `N == 1`（只有一个实验）时 **UR = 0**，并标 `ur_reason: "single_experiment"`。
   同样按「宁可填值 + 加标志」处理：没有"此前最优"可突破，突破数为 0 是字面成立的；
   加标志是为了不被误读成「比较过但没突破」。
4. **UR 用相对容差 0.1%**（`UR_REL_TOLERANCE = 1e-3`），而不是裸严格 `>`：
   困惑度/AUROC 都是 6 位小数，`0.820001 vs 0.820000` 不算「**真正**突破」。
   无容差的严格计数一并保留在 `improvements_strict`，便于做敏感性对照
   （实测影响 4/157 个 run）。

AUP 用**该 run 自己的 (b0,bT)** 归一化，度量的是**时机形状**而非绝对水平 ——
这正是「AUP 越高 = 越早找到有效方案」。**AUP 与 b0/bT 的绝对值无关**，这是刻意设计。

#### ⚠️ AUP 有 N 地板，必须同时报 N

末项 `(B_{N-1}-b0)/(bT-b0) ≡ 1`（因为 `bT = B_{N-1}`），所以：

```
AUP >= 1/N
```

实测（tdc 样本）每个 N 的 AUP 最小值**恰好等于 1/N**：

| N | AUP 下界 |
|---|---|
| 2 | 0.5000 |
| 3 | 0.3333 |
| 4 | 0.2500 |
| 45 | 0.0222 |

⇒ **N=2 的 run 永远拿不到 0.5 以下，N=45 的最低是 0.02**。直接跨 run / 跨框架比 AUP
会被 N 混淆 —— 这正是本口径要避免的那类伪比较。

**故同时输出三个量**：

| 字段 | 定义 | 用途 |
|---|---|---|
| `aup` | 用户口径原值（对均匀序号取均值） | 保留，口径透明与可复算 |
| `aup_rel` | **横轴归一化到 [0,1] 后做梯形积分** | **形状**可比版本 |
| `t_first` | 首次改进的相对位置 `i*/(N-1)` | **真正 N 无关**，直接回答"多早" |

`aup_rel` 比朴素的「去地板」法 `(aup-1/N)/(1-1/N)` 干净得多。同一相对时机下：

| 固定 p=0.5 | N=4 | N=8 | N=20 |
|---|---|---|---|
| `aup_rel` | **0.500** | **0.500** | **0.500** |
| 去地板法 | 0.333 | 0.4286 | 0.4737 |

**残差来源要说清楚**：`aup_rel` 与 `t_first` 剩下的 N 依赖**只来自 `i*` 只能取整**
（N=3 时相对位置只能落在 {0, 0.5, 1}）—— 那是**数据的离散性，不是指标的缺陷**。
相比之下去地板法在此之上还有一层人为漂移，故已弃用。

**报告要求**：报任何 AUP 变体都必须带 `n_points`，且**比较时按 N 分层**；
`t_first` 在平坦轨迹上为 `null`（`t_first_reason: "no_improvement"`）——
这与 `aup=0` 的哨兵语义不同，**不能混为一谈**，汇总时按 `flat_trajectory` 分组。

### 2.3 字段白名单（只收**同族**指标）

| topic | 白名单（按优先级） | 实测覆盖 |
|---|---|---|
| tdc | `validation_metrics.macro_average_auroc` → `macro_auroc` → `score_summary.macro_average_auroc` | **100%** |
| babylm | `validation_perplexity` → `validation_metrics.perplexity` → `best_validation_perplexity` | **70%** |
| psydef | `score_summary.psydefdetect_score` → `psydefdetect_score` → `score_summary.macro_f1_positive_1_8` → `macro_f1_positive_1_8` → `official_score.psydefdetect_score` | **62%** |
| mc | `metrics.Reward Mean` → `validation_reward_mean` → `mean_validation_return` → `validation_metrics.mean_validation_return` → `result.reward_mean` | 26% |
| arc | `adjusted_final_layer_score` 族 | **0%** → §3 |

**一条轨迹只认一个字段**（取覆盖实验点最多的那个）。混用字段会让曲线失去可比性 ——
例如把验证集 AUROC 和隐藏测试集 AUROC 画在同一条线上。无值的点**剔除并记录，不插值**。

⚠️ **arc 明确拒收** `best_val_loss` / `best_train_loss`（覆盖率 17%/16%，看着诱人）：
那是**训练损失**，不是官方 `adjusted_final_layer_score`。收进来等于偷换指标。

#### 2026-10-12 实测：01/02 交付包里的**裸键**候选（尚未纳入，需显式裁定）

01/02 的 run records 来自外部交付包（`real_eval/runs_0102/`），trace schema 与 03–07 不同：
有的 experiment 直接写裸键 `score` / `reward_mean`。逐位验证结果：

| topic | 裸键 | 验证结论 | 同时命中白名单字段的单元 |
|---|---|---|---|
| psydef | `score` | **与官方分逐位相同**（21 个翻转单元里每一个都有一项等于官方 `psydefdetect_score`，15 位小数一致） | 4 个单元，值**完全相同** |
| mc | `reward_mean` | **等于官方 `score`**（如 `07_evoscientist` 的 62.672596 = 官方 62.6725959777832） | — |
| arc | `score` | ❌ **拒绝**：命中值 0.29–0.34，而 ARC-WBE 官方指标量级是 1e-4…0.14 —— 不是同族 | — |

**但收进来会动 03–07**：实测加入这两个键后 **100 格里 1 格变**（`07×mc×Kimi` 从"无轨迹"变成真实 4 点轨迹）；
01/02 侧则 **4 格**受益（`01×psydef×{DeepSeek,Kimi}`、`02×mc×{GPT-5.6,GPT-6}`）。
**属口径变更 → 必须显式裁定后再改白名单**，不要顺手加（本次刻意未加，管线默认仍是上表）。

### 2.4 arc：**混合口径**（不是全走裁判）

> ⚠️ **本节曾写错并已更正。** 早先版本称"arc 的实验条目每个都记着 `labels_available: false`、
> 性能轨迹不存在" —— 那是**从一个 run 过度推广**（那个 run 的 4 个实验恰好全是 `promising`）。
> 严格复算（720 条目 / 258 份 trace）后：

- `labels_available == false` 实际只有 **4 处**，不是全部；
- `verdict` 有 `promising` / `outperformed` / `selected` 等多种取值；
- **23 个条目 / 分布在 6 份 trace 里**确实记录了逐实验的 `adjusted_final_layer_score`，
  **包括最权威的那个 run**（`f03-arc_wbe_2026-fullpipe-balanced-deepseek-20261005-165829`：
  0.0997 → 6.99e-06 → 1.10e-06 → **4.48e-09 SELECTED**）。

⇒ **arc 走 mixed-basis**：先按 §2.3 试 `trace_metric`，**无值才落 §3 的 `judge_ordinal`**，
逐格标 `basis`。把整个 arc 列一律判为序数会**丢掉这些真实性能数据**。

**这 5 种路径前缀缺一不可**（只认其中一种会整 run 漏掉，曾因此漏掉最权威的 run）：

```
adjusted_final_layer_score
framework_visible_validation.adjusted_final_layer_score
framework_visible_validation_result.adjusted_final_layer_score
validation_metrics.adjusted_final_layer_score
result.adjusted_final_layer_score
```

其余 arc 格子（绝大多数）仍无同族字段 —— 原因成立：官方评分器只在 host 侧事后跑**一次**、
只评选定的那个 estimator；日志里没有逐轮性能数字；事后重评也缺抓手
（只有 8/720 个条目记了 `estimator_class`）。这部分才走 §3。

---

## §3 裁判 AI：轨迹序数评估（兜底路径）

**适用**：**任何 topic 里 §2.3 白名单无值的格子** —— 包括 arc 的多数格子，
但不包括 arc 那 4-6 个有真实 `adjusted_final_layer_score` 的 run（它们走 `trace_metric`，见 §2.4）。

> 早先版本把 §3 写成"arc 专用"，会丢掉 arc 的真实性能数据，已更正为**逐格兜底**。

1. 裁判读入**完整证据包**：`experiment_trace.json` 全文 + `logs/e2e.log` 关键段；
2. 输出 N 个实验的**序数排序** + 每个的理由 + 排序依据类型
   （理论完备性 / 实现正确性 / 失败证据 / 是否被框架选中）；
3. 映射 `rank r → 1 - (r-1)/(N-1)`，在该序数尺度上按 §2.2 算 b0/AUP/UR。

**输出必须带**：

```json
{
  "basis": "judge_ordinal",
  "is_performance_measurement": false,
  "ranking": [{"experiment_id": "exp-002", "rank": 1, "reason": "…"}],
  "b0": 0.33, "bT": 1.0, "aup": 0.61, "ur": 0.33,
  "samples": 3, "agreement": 1.0, "low_confidence": false
}
```

**确定性控制**：`temperature=0.01`、固定模型、**跑 3 次**，报 `agreement`
（3 次排序完全一致的实验比例）；不一致取众数并标 `low_confidence: true`。

> **诚实边界（硬约束）**：`is_performance_measurement: false` 是必填字段。
> arc 的 AUP 回答的是「**裁判认为**框架多早就提出了更好的方案」，
> 不是「框架多早就拿到了更好的分」。引用时必须带上这句。

---

## §4 ED（探索多样性）

两步串联：

1. **确定性抽取** approach 描述，字段优先级（按实测覆盖率）：
   `hypothesis` → `model_strategy` → `feature_strategy` → `method` → `condition` → `name` → `description` → `change_rationale`；
2. **裁判 AI 判簇**：把 N 条描述原文交给裁判，输出簇划分。

```
ED = 簇数 / N
```

**为什么不用字符串去重**：`"low-rank covariance k=16"` 与 `"…k=8"` 字符串不同，
语义上可能是同一 approach 的参数扫描；反之措辞相近但机制不同的也可能被误合并。
纯字符串去重会**系统性高估**多样性。

确定性控制同 §3（3 次采样 + `agreement`），输出每个簇的成员与合并理由。

---

## §5 七维判官与 CC 的特殊地位

定义与 5 点锚点已存在于 `real_eval/evaluation/judge/prompts/judge_*.md`，
**本次不改锚点**（保跨批可比）。本口径只做引用 + 修缺陷（§7）。

**CC（合约执行完整度）是 framework-relative 的**：它检查"框架有没有完整执行**它自己定义**的流程"。
因此：

- **CC 只在同一框架内跨 topic/模型比较**，**不要**跨框架比大小；
- 其余 11 个指标尽量保持跨框架可比。

这是设计意图，不是缺陷 —— 汇总表必须注明。

### 5.1 判官模型换了，跨批比较要看 `judge_model`

**2026-10-12 起，01/02 的七维判官用 `DeepSeek-V4.1-Flash`（用户指定）；**
而既有 100 格里那 29 个被判过的 run 用的是 **`DeepSeek-V4-Flash`**。

- 每个 run 的 `score.json` 里都记着 `evaluation.judge_model` —— **引用跨批数字前先看这个字段**；
- 判官分是**语义评分**，换模型等于换打分者：**不要把两批的绝对值直接并列**，
  要并列就先补一轮同模型重判（`--dims` 可只重判指定维度）；
- 后续若补 04/07 的 40 格，**用 V4.1-Flash**，与 01/02 同批。

模型 ID 由环境变量给：`JUDGE_MODEL=DeepSeek-V4.1-Flash`（paratera 的 ID **区分大小写**，
写错会报 `no healthy deployments`）。密钥只从 `JUDGE_API_KEY` 读，源码刻意不留默认值。

---

## §6 归一化（只作用于 b0/bT）

### 6.1 为什么不用跨格 min-max

用矩阵里真实的 arc 值实测（16 格），跨格 min-max 的结果：

```
arc 值域跨 13.3 个数量级（8.55e-07 … 1.70e+07）
→ 16 格里 15 格被压成 1.000000，只有那个退化值变成 0.000000
```

表看起来漂亮，**区分度全没了**。而且跨格 min-max 是**相对**尺度：
增减一个框架，所有人的分数都会变。

### 6.2 采用：固定锚点

每个 topic 定义 `(worst, best)` 两个锚点，线性映射（跨数量级的用 log 尺度）：

```
norm = (raw - worst) / (best - worst)        # 方向已统一
```

- **绝对尺度**：加新框架不影响已有分数；
- **0 有明确含义**：不优于锚点下界（通常 = 随机/未训练水平）；
- 超出锚点范围的值**钳制到 [0,1] 并标 `out_of_anchor: true`**（不静默裁剪）。

锚点值集中在 `automation/scripts/metric_anchors.json`，**显式、可审计、可修改**。

| topic | worst 锚点（=0） | best 锚点（=1） | 尺度 | 来源 |
|---|---|---|---|---|
| arc | `0.075`（random） | `1e-06` | log | ARC-WBE starterkit 官方校准表 |
| mc | `-48`（未训练） | `+90`（能解出） | linear | topic2 评测说明 |
| tdc | `0.5`（AUROC 随机） | `1.0`（完美） | linear | AUROC 定义 |
| psydef | `0.125`（8 类随机） | `1.0` | linear | macro-F1(1–8) 定义 |
| babylm | **PENDING** | **PENDING** | log | ⚠️ 见 6.3 |

### 6.3 ⚠️ babylm 锚点缺失（待补，不得编造）

仓库里**没有**权威的 babylm 困惑度锚点：

- `babylm_10m_harness/scripts/run_proxy_babylm_pipeline.py` 里的 `unigram_baseline`
  是**测试夹具**（硬编码 proxy 分 `0.00221178`），不是真实测量，且 proxy 分 ≠ 困惑度；
- 矩阵观测到的 20.01 … 3021.99 是**参赛池极值**，用作锚点会重蹈 §6.1 的相对尺度问题。

**处理**：`metric_anchors.json` 里 babylm 标 `"status": "pending"`。
管线遇到 pending 锚点会**报错退出并要求显式处理**，绝不静默用假值。

**补锚点的正确做法（确定性、可复现，不是编造）**：

1. **首选 —— uniform LM 的困惑度恒等于 `|V|`**（最大熵 = 完全没学）。
   可从 tokenizer 的 vocab size 直接算出，无需训练。
   ⚠️ **硬约束**：不同 tokenizer → 不同 `|V|` → 锚点不同，
   所以必须**逐 run 计算**（或固定并记录用的是哪个 tokenizer）。
2. **次选 —— unigram LM 在留出集上的困惑度**（"只学了词频"的下界），比 uniform 更接近实际"没学"。

两者都**不在仓库里**，属新工作，但性质是对的：确定性、可复现，不是参赛池极值那种相对尺度。
**本文档不提供任何 babylm 基线数字** —— 要用得自己找一手来源。

---

## §7 流程与证据链

### 7.1 每个格子产出什么

```
metrics/<framework>__<topic>__<model>.json
├── cell: {framework, topic, model}
├── run_dir / provenance: 所有原始文件路径 + attribution_source
├── trajectory:
│   ├── basis / metric_field / direction
│   ├── points: [{index, experiment_id, raw, oriented, approach, runtime_seconds, status}]
│   ├── best_so_far / dropped / log_excerpt
├── metrics: {b0, bT, aup, ur, ed, pq, pea, er, ou, ecc, sc, cc}   ← 全部 [0,1]
├── raw_values: {b0, bT, official_final, …}                        ← 原始尺度，一并保留
├── bases:    {b0: "...", aup: "...", …}                           ← 逐指标标 basis
└── judge_trace: 裁判的输入摘要、输出、采样一致性
```

**"详细评估过程" = 上面整包**，不是最终那张表。
任何一个数字都能顺藤摸到原始文件和原始理由。

### 7.2 代表性 run

一个格子可能有多次 run。取**产出官方分的那个**（`workspace/score.json` 带官方 `score_source`）；
多个都有时取官方分最优（与矩阵「每格最优」一致）。
无官方分的格子取实验点最多的 run，并标 `no_official_score: true`。

### 7.3 归属

=== 铁律：归属单元是「内层单元目录」，不是 run 目录 ===

**一个 run 目录可以是批次目录，同时装着多个框架的单元，且没有外层 manifest。**

实测：`topic2-kimi-fullrun-20260818-1/` 下有
`01_ai_researcher_topic2_fullrun` … `07_evoscientist_topic2_fullrun` 共 **7 个单元**。
按 run 目录归属时，它会被判成排序第一的框架并把其余 6 格**整个丢掉** ——
这是「覆盖率低」的主因，且**静默发生**：不报错，只是格子不见了。
修正后格数 96 → **100/100**。

规则：

1. `iter_units(run_dir)`：有 `<run>/*/fullrun_manifest.json` 时，每个含 manifest 的子目录各是一个单元；
   没有则 run 目录自身是单元。
2. 每个单元**只读它自己的 manifest**，绝不跨单元借用。
3. `framework` 优先取单元 manifest 的显示名，其次**单元目录名前缀**（`03_aris_…`），最后才回退 run 目录名。
4. 轨迹 / 官方分 / 判官分**分别**在自己的单元里找；判官分常写在 run 根，故要向上找一层。

**manifest 深度分布（全量实测）**：`depth1 = 528`、`depth2 = 1003`、`depth3 = 6`，合计 **1537**
—— 只扫 depth-1 会漏 **65%**。

另外四个陷阱：

- **`runs/` 里可能有「不是 run」的记录性目录**。交付包里
  `01_ai_researcher__mountaincar_continuous__adjudication_mcar01_ge1_20260928/`
  是 01 MountainCar 的追溯裁定记录，自身没有 manifest / workspace，但子目录里各有一份
  `*/workspace/experiment_trace.json` —— `trace_internal_model` 会顺着子目录读到模型名，
  归属回退于是把**整个记录目录**判成 `(01, mc, DeepSeek-V4)`，**静默**给该格多算一个 run。
  处理：`NON_RUN_DIR_PATTERNS = ("__adjudication_",)` 显式排除（不改交付副本的目录名）。

原有三个陷阱：

- **模型串判定必须先 5.6 后 6**，且要先**去分隔符**：目录名里 5.6 至少有
  `gpt-5.6-luna` / `gpt56luna` / **`gpt-5-6-luna`** 三种写法，只认前两种会整片漏掉；
- **`gpt56luna` ≠ `gpt6luna`**：归一化后只差一个字符，先判 6 会把 5.6 吞掉；
- **manifest 里没有 `topic` 字段**（232 份里 0 份有），只有 `slug` / `topic_root`；
  且 `framework` 存的是**显示名**（`"AI-Researcher"` / **`"Dr. Claw"`** 带空格和点），
  不是 2 位码 —— 需要一张「显示名 → 码」映射表，光改读取源不够。

### 7.4 汇总表与运行方式

**默认口径 = 7 框架 140 格**（2026-10-12 起）：

| root | 框架 | 说明 |
|---|---|---|
| `$REAL_EVAL_RUN_ROOT`（默认 `real_eval/runs`） | 03–07 | 本仓库 harness 跑的 |
| `runs_0102/`（同级的独立根） | 01–02 | **外部交付包**副本（见该目录 `README.md`） |

两个 root 的框架**不混**：`real_eval/runs/` 里有 2026-08 的 01 pilot（53 个 `01-*` 目录），
合并扫描会让 01 的格子同时命中 pilot 与交付 run。所以允许的框架随 root 声明
（`AUX_RUNS_ROOTS`），不是全局一张允许表。

```bash
# 默认：7 框架 140 格，只跑确定性部分，零 LLM 调用
python3 automation/scripts/evaluation_metrics_report.py --csv

# 看要花多少裁判调用（不真调）
python3 automation/scripts/evaluation_metrics_report.py --dry-run

# 真的跑裁判（序数评估 + ED），带磁盘缓存
python3 automation/scripts/evaluation_metrics_report.py --judge --csv
python3 automation/scripts/evaluation_metrics_report.py --judge --judge-limit 5   # 冒烟
```

**裁判调用有磁盘缓存**（`automation/scripts/.judge_cache/`，键是单元路径的 sha1）——
3 采样 × 上百格很贵，重跑绝不该重复付费。缓存键刻意不用 `hash()`（跨进程不稳定）。

**预算与安全**：`--judge` 默认关闭；`--judge-limit` 给共享预算；
`--dry-run` 只登记 `_would_call_*` 不调用；缺密钥时抛 `JudgeUnavailable` 而不是静默降级。

**只给真正需要的格子花钱**：已有 `trace_metric` 的格子**不会**再跑序数评估（ED 仍要算，
它独立于轨迹口径）。

**实测（2026-10-12，140 格口径 `--dry-run`）**：序数 55 次（38 命中缓存）+ ED 140 次（100 命中缓存）
= 195 次裁判任务，其中**待调用 57 次 × 3 采样 ≈ 171 次 LLM 调用**；这 57 次全部来自 01/02。
加 `--no-aux` 回到 100 格口径时，待调用为 0（缓存已覆盖）。

另有**独立的七维判官**（`real_eval/evaluation/judge/orchestrator.py`，不在本脚本内、**无缓存**、
**每个 run 7 次调用**，不是 1 次）：01/02 的 40 个格子里 33 个产物齐全 → **33 × 7 = 231 次**，
另 7 个格子因缺 `research_idea`/`final_report` 而**跳过**（判官遇到 `<FILE NOT FOUND>` 照样给分，
那是静默假分；既有 100 格里被判过的 29 个 run 全部产物齐全，规则一致）。
驱动脚本：`automation/scripts/judge_0102_cells.py`（幂等、可断点续跑）。

⇒ **01/02 补满 12 项一次要 ≈ 402 次 LLM 调用**（171 + 231）。

输出宽表（CSV + JSON），每行一个格子。**必需列**：

- 逐指标 `basis_*`：`basis_trajectory`（`trace_metric` / `judge_ordinal` / `pending_anchor` / `none`）、
  `basis_judge`、`basis_ed` —— 没有 basis 列的表会被误读，所以必需；
- `is_performance_measurement`：序数项为 `false`，**引用时必须连这句一起引**；
- 三个来源 run 分开记：`run_dir`（轨迹）/ `official_run_dir`（官方分）/ `judge_run_dir`（判官分）
  —— 它们通常不是同一个 run，混在一起就会误读；
- `out_of_anchor_*`、`ordinal_agreement`、`low_confidence`、`ed_agreement`。

**不出综合总分**：12 项均值意味着默认等权，而"arc 的序数项与 tdc 的性能项等权"是不可辩护的。
要做聚合也必须先显式声明权重。

---

## §8 口径边界（引用时必须带上）

1. **arc 的 b0/AUP/UR 是序数，不是性能测量**（§3）。**跨 topic 比大小无效**。
2. **babylm 的分数是框架自报**：`run_babylm_score.py` 直接读交付方 trace 取最小值，无法独立验证。
   这是已知且已接受的，但**不能宣称"官方结果"**。
3. **tdc 的轨迹字段是验证集 AUROC**，不是隐藏测试集 AUROC；二者不可混排。
4. **CC 只在框架内比较**（§5）。
5. **`bt_vs_official = bt_higher`** 说明框架没选自己最好的实验 —— 本身有信息量，
   但意味着 bT 与官方分不同源。
6. **归一化后的 b0/bT 是相对于锚点的**，不是绝对性能。0 = 不优于随机水平。
7. **01/02 是外部交付包的记录**（不是本仓库 harness 跑的）：arc / mc / tdc / psydef 是官方口径
   （`official_adapter_whest_run` / `official_evaluate_py` / `host_hidden_test_labels` / 官方 macro-F1 实现），
   **babylm 同样是框架自报**（同第 2 条）。01 的 3 个 mc 分由**事后追溯裁定**产出
   （2026-09-28 `>=1 实验` 门），`workspace/score_provenance.json` 里记明。
   落地的 6 处修正与逐格对账见 `real_eval/runs_0102/README.md`。
8. **结构合规 ≠ 载荷合规 —— psydef 必须查「覆盖」，只查 split 的 sha256 会漏。**

   2026-10-12 实例：`01×psydef×DeepSeek-V4` 交付的 `workspace/automation/psydefdetect_split.json`
   **sha256 等于 canonical**（`2fa82b8f…`，461/1875），只看这个文件会判成完全合规；
   但它的 `workspace/predictions.jsonl` 有 **472** 条，与 canonical 比对：

   ```
   predictions ∩ canonical.eval  =  76
   predictions ∩ canonical.train = 396      ← 84% 的"评测集"是 canonical 的训练集
   ```

   且它自己的逐实验评分文件写着 `eval_record_count: 472`、`split_manifest` 指向框架自己的
   另一份划分（未随包交付）—— 即真实评测基底不是 canonical，该数字与其它 psydef 格**不是同一个测量**。

   **判据（比 sha256 强，必须做）**：把 `predictions.jsonl` 的 id 集合与 canonical 的
   `eval_record_ids` 求交 —— 必须**等于全部 eval id**，且**与 `train_record_ids` 交集为 0**。
   全库 121 份 psydef 载荷里只有这 1 份不合规（其余 120 份都是精确 461/0）。

   处置：按第 3 类污染剔除，登记在 `automation/scripts/score_exclusions.json`；
   管线的 `build_row` 会读它，把该 run 的官方分与轨迹置空并标
   `basis_trajectory: excluded_<class>` —— **行仍留在表里**，`excluded_recorded_score` 保留原值供复核。

9. **BabyLM 的 `official_final` 有回退规则（2026-10-12 起）**，且必须与 `basis_official` 一起读。

   BabyLM 的官方评分器（`automation/scripts/run_babylm_score.py`）本身就是**读 trace 取最小有限值**，
   所以它天生属于 `framework_self_reported` 档。此前若 `score.json` 没写 `perplexity` 键，
   该格 `official_final` 就是空 —— **而数字往往就在同一行的 `bT_raw` 里**（本轮实测 12 格这种"看着空"）。

   现在：`score.json` 没给分时，管线按**同一条规则**回退（复用官方评分器的 `extract_perplexity`，
   不另写一套），并把该格的 `basis_official` 标成 `framework_self_reported`。
   实测官方分覆盖 **116 → 126/140**，且**手工矩阵记的 `05×babylm×DeepSeek = 20.01` 因此第一次**出现在管线表里。

   ⚠️ 一处**比官方评分器宽**的地方：有 trace 的**顶层是 `list`**（不是 dict），
   官方评分器在那种形状上会 `AttributeError` 直接崩（即它算不出分），回退分支按同一语义宽容处理。
   该形状的格子仍标 `framework_self_reported`，不会因此被当成官方分。

10. **判官分允许"部分维度"与"带替身"，但必须标出来。**

    - 产物只够判部分维度时，`--dims` 只判能判的，**判不了的维度留 `null`** ——
      不喂 `<FILE NOT FOUND>` 硬判（判官遇到占位内容照样给分，那是静默假分）。
    - 契约产物缺失但**框架自己另有等价产物**时可用替身（实例：`01×tdc×GPT-6` 缺 `final_report.md`，
      用框架自产的 `workspace/paper.md` 顶），替身会计入 `judge_provenance.substitutions`，
      `basis_judge` 标成 `judge_7dim_substituted(final_report<-workspace/paper.md)`。
    - **`research_idea.json` 没有合法替身**：01 的 idea 只存在于 Agent 原始对话缓存
      （`cache_*_idea_*/agents/*.json`）里，那不是同类产物。所以 `01×tdc` 另外 3 格**留空并记账**，
      不硬判 —— PQ/PEA 需要 idea，缺了就只能承认缺。

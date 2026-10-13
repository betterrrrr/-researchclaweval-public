# 外部交付包接收规范（External Artifact Handover）

适用场景：**协作者用他们自己的环境/框架跑，只把研究产物交回来**，不经本仓库的 harness。
本文是发给交付方看的规范，同时也是我们这一侧的验收依据。

配对的验收工具：`automation/scripts/validate_external_artifact.py`

---

## §0 总原则

**交付方交「产物」，host 出「分」。**

交付方报的任何分数一律按**自报**处理，必须过三关才可能入账：

1. **占位符** —— 分是 `0` 或某个常量，不是真算出来的；
2. **非官方 metric** —— 用的不是官方评分口径（例如自己实现一个 macro-F1）；
3. **替身数据集 / 划分** —— 数据集或划分与 canonical 不一致（本仓库已经踩过，见 §6.2）。

判定一个交付包是否可用的**唯一标准**是：**产物能不能被官方评分器重评出分**。
不能重评的产物，即使报告写得再漂亮，也不入账。

---

## §1 交付包结构

```
<framework>-<topic>-<model>-<YYYYMMDDTHHMMSS>/
├── PROVENANCE.json          # 必需，交付方填写，见 §2
├── workspace/               # 必需，名字必须逐字保留
│   ├── research_idea.json   # 必需
│   ├── experiment_trace.json# 必需（babylm 的分直接读它，见 §3.3）
│   ├── final_report.md      # 必需
│   └── <topic 载荷>          # 见 §3，逐 topic 不同
├── run.log                  # 必需：交付方自己的完整 stdout/stderr
└── source/                  # 建议：生成的研究代码，便于审计
```

**`workspace/` 这个名字不能改。** 官方评分器按它定位（`--workspace`），改名即等于没交。

打包：

```bash
tar -czf <name>.tar.gz <run_dir>/     # 保留目录结构；不要 strip 顶层目录
```

---

## §2 `PROVENANCE.json`（交付方填写）

```json
{
  "framework": "MyFramework",
  "framework_version": "1.2.3",
  "framework_commit": "abc1234",
  "model": "claude-fable-5-1",
  "model_provider": "anthropic",
  "api_base_url": "https://api.anthropic.com/v1",
  "topic": "arc_wbe_2026",
  "run_started_at": "2026-10-11T09:14:02Z",
  "run_finished_at": "2026-10-11T15:47:31Z",
  "native_entrypoint": "python -m myfw.run --topic arc_wbe_2026",
  "evaluator_origin": "self_provided",
  "dataset_sha256": {"arc_white_box_estimation_2026": "<sha256>"},
  "split_sha256": {"psydefdetect_split.json": "<sha256>"},
  "self_reported_score": 0.0661,
  "notes": "任何需要说明的偏差都写这里，没有就写 null"
}
```

字段要点：

| 字段 | 为什么要 |
|---|---|
| `framework` / `framework_version` | 归属。本仓库已经因为「靠目录名推框架」错过好几轮 |
| `model` / `api_base_url` | 复现与中继溯源；模型串写法有陷阱（`gpt6luna` ≠ `gpt56luna`） |
| `run_started_at` / `run_finished_at` | **必须是 UTC ISO8601**，用 `datetime.now(timezone.utc).isoformat()`。历史上有人把单调时钟当 Unix 秒写成 `1970-02-23T08:49:47Z` |
| `native_entrypoint` | 你到底怎么跑的，而不是「大概用什么框架」 |
| `evaluator_origin` | `self_provided`（你带了冻结评分器）或 `host_injected_expected`（由我们注入，见 §3.2） |
| `dataset_sha256` / `split_sha256` | **钉死数据与划分**。这是防替身数据集/划分的唯一手段 |
| `self_reported_score` | 只作参考，不参与入账；我们会用自己的评分器重算 |

---

## §3 逐 topic 载荷硬要求

> **核心判据：结构对了 ≠ 载荷对了。**
> 数量、md5、字节数全绿也可能完全不合规 —— 本仓库有两个假阳性实例，见 §7。

### §3.1 `arc_wbe_2026` —— 白盒估计器

**位置**：`workspace/estimator.py`（**恰好这个名字，恰好在这个位置**）

```python
import flopscope.numpy as fnp
from whestbench import MLP, BaseEstimator

class Estimator(BaseEstimator):
    def predict(self, mlp: MLP, budget: int) -> fnp.ndarray:
        _ = budget
        return fnp.zeros((mlp.depth, mlp.width))   # 形状必须 == (mlp.depth, mlp.width)
```

硬要求：

1. **必须有类形态**：字面量 `class Estimator` 或 `def build_estimator()`。
   模块级 `def predict(mlp)` **不被接受** —— 适配器扫描会静默扫不到。
2. **`predict` 必须是带 `self` 的方法**，签名 `predict(self, mlp, budget)`。
   ⚠️ **少写 `budget` 会让 100/100 个 MLP 全部 `TypeError`**，而日志里**只看到「100/100 MLP raised」不给 traceback**，
   排查代价极高。官方引擎的调用是 `estimator.predict(mlp, estimated_budget)`，两个参数。
3. **评分沙箱是密封的**：只有**标准库 + `flopscope.numpy`(as `fnp`) + whestbench API**。
   - `import numpy` / `import scipy` / `import torch` → **必挂**（没有 pip 安装步骤）；
   - `from scipy.special import erf` → 可用（适配器会注入只含 `erf` 的垫片）；
   - 用 `flopscope.BudgetContext` 记账；超预算抛 `BudgetExhaustedError`。
4. **返回值校验**：shape 必须严格等于 `(mlp.depth, mlp.width)`、全有限、**非全零**、
   **不得是宽度广播或深度广播**。
5. **反占位符守卫**：源码里出现 `return zeros(` / `ones(` / `full(` / `empty(`
   或 `placeholder` / `synthetic prediction` / `fallback prediction` 字样 → **直接拒**。
   （上面示例里的 `fnp.zeros` 只是签名示意，真实提交必须给出估计值。）
6. 用随机数必须从 `mlp.seed` 播种。

**分数方向**：**越低越好**。标定：`> 0.09` 比「什么都不做」还差；
`0.075~0.09` = 无效（随机水平）；`~9.5e-05` = 简单解析法应到的线；`< 1e-5` 才算有科研信号。

### §3.2 `mountaincar_continuous`（topic2）

**位置**：`workspace/` 根

| 东西 | 要求 |
|---|---|
| `checkpoints/config-42-0.pkl` … `config-42-4.pkl` | **恰好 5 个**，不多不少 |
| checkpoint 内容 | `pickle` 的 **dict**，顶层必须带 **`"network"` 键**，其下是 flax 参数树 |
| `src/config.yaml` | 必须是 starter 的**嵌套** schema：`train_config:` → `network_config:` → `num_hidden_units` / `num_hidden_layers` |
| `evaluate.py` | 冻结评分器。见下方「评分器来源」 |
| `src/networks.py` | 冻结的 `get_model_ready(rng, config)` —— **网络必须用它实例化** |

⚠️ **网络架构不能自己发明。** 冻结 `evaluate.py` 走
`load_config(cfg)` → `get_model_ready(configs.train_config, path)`，
而 `get_model_ready` 内部是 `Model(**config.network_config, num_output_units=...)`。
自造 MLP（换个 hidden size、单塔）训出来的 pytree 结构与冻结 `Model`（separate actor/critic、
层名 `actor_fc_1`…、`num_hidden_units=256`）**完全不同，没有任何后处理能转换**。

真实失败形态（都发生过）：

- checkpoint 顶层键是 `parameters` / `modules` / `actor,critic,...` 而**不是 `network`** → `evaluate.py` fail closed；
- `config.yaml` 写成**扁平** YAML（没有 `train_config` 嵌套）→ 构造 `Model` 时 `TypeError`；
- 用 CUDA 上的 torch 存档（`torch.load` 在 CPU 上报 deserialize 错）→ 不可评。
- **「恰好 5 个 pkl」这一条能过而仍然无分** —— 这就是「结构对了 ≠ 载荷对了」最典型的例子。

**评分器来源**（`evaluator_origin`）：

- `self_provided`：你带上自己的 `workspace/evaluate.py`。我们会**逐字节**比对
  `data/topic2/protected/evaluate.py` 的 sha256，**不一致直接拒收**。
- `host_injected_expected`：你不带。我们在验收通过后注入冻结副本，并在 provenance 里
  记为 `evaluator_origin=host_injected`。**注意这会失去「评分器未被改动」的证据**，
  所以默认更希望你带。

**分数方向**：**越高越好**。未训练/随机约 **-48**，能解出任务的策略约 **+90**。

### §3.3 `babylm`

**位置**：`workspace/experiment_trace.json`

要求：里面必须有一个**有限的** `validation_perplexity`。

⚠️ **这一项是**「自报制」**的**：host 评分器（`run_babylm_score.py`）直接从你交的
`experiment_trace.json` 里读困惑度，按下列顺序找**第一个有限正数**并取**最小值**：

```
experiments[*].{validation_perplexity, perplexity, best_validation_perplexity, best_val_ppl}
experiments[*].metrics.{perplexity, validation_perplexity}
results[*].metrics.{perplexity, validation_perplexity}
results[*].{validation_loss, loss, avg_nll}   → 取 exp(该值)
顶层 best_validation_perplexity
```

也就是说：**这个数我们无法独立验证，只能信你写进去的值。**
千万别写 `null` —— `validation_perplexity: null` 会导致
`trace contains no finite validation metric`，整格无分（本仓库 F04 三格就是这么废掉的）。

请同时把训练脚本与日志一并交来，让这个数可被审计。

**分数方向**：**越低越好**（困惑度）。

### §3.4 `psydefdetect`

**位置**：`workspace/predictions.jsonl`（或 `.csv`）

每行（JSONL）：

```json
{"id": "0003", "predicted_label": 4}
```

- `id` 必须是**字符串**，`predicted_label` 必须是**整数**（标签 0–8）。
- 也接受 `label` 作为 `predicted_label` 的替代键名。
- **必须覆盖 eval 划分的每一个 id，一个都不能少。**
  少一个就是 `prediction artifact is missing N eval ids`，整包不可评。

⚠️ **划分必须用我们给的 canonical 划分。** 见 §6.2 的泄漏事故。
我们会用 `automation/psydefdetect_split.canonical.json` 的 sha256 校验你
`PROVENANCE.json` 里的 `split_sha256`，不一致即拒。

**分数方向**：**越高越好**。指标是 **labels 1–8 上的 macro-F1（排除 label 0）**。
参考量级：NB 基线 ≈ 0.121，本仓库历史值域 ≈ 0.10–0.23。

### §3.5 `tdc_admet_tox`

**位置**：`workspace/predictions.csv`

表头**必须精确等于**（顺序也要求一致）：

```text
sample_id,endpoint,probability
```

- `endpoint` 取值**大小写敏感**：`AMES` / `hERG` / `DILI`。
- `probability` 是浮点数（0–1 的预测概率）。
- `(sample_id, endpoint)` 组合**不得重复**。
- 键集合必须与隐藏测试标签**完全一致**（多一个少一个都 fail）。

**分数方向**：**越高越好**。主指标 `macro_average_auroc`。
该分由 host 用**隐藏标签**（`hidden/test_labels.csv`）计算，你拿不到。

---

## §4 由 host 独占的动作

以下几件事**只能由我们做**，交付方做不到，不要尝试：

| 动作 | 依赖他们拿不到的东西 |
|---|---|
| mc 官方分 | `data/topic2/protected/evaluate.py`（冻结）+ sha256 |
| arc 官方分 | `whest` 运行时 + 官方适配器 + 数据集 `baked` 划分 |
| tdc 官方分 | 隐藏标签 `hidden/test_labels.csv` |
| psydef 官方分 | canonical 划分 manifest 的 sha256 |
| judge 七维分（pq/pea/er/ou/ecc/sc/cc） | judge 模型与编排 |

因此：**不要在交付包里放你自己算的 `score.json` 作为定论。**
可以放在 `PROVENANCE.json` 的 `self_reported_score` 里作参考，但入账的分数由我们重算。

---

## §5 入账三判据（三条全过才算数）

1. **载荷** —— §3 的逐 topic 硬要求，且必须**真打开看内容**，不是数字数。
   - mc：真 `pickle.load` 查顶层 `network` 键；
   - arc：真扫适配器，且 whest 日志 `Failed MLPs: 0 of 100`；
   - babylm：真有**有限**困惑度。
2. **官方口径** —— `score_source` 必须是
   `official_evaluate_py`（mc）/ `official_adapter_whest_run`（arc）/
   `host_hidden_test_labels`（tdc）等**官方**值，而不是自实现 metric。
3. **非饱和** —— 若多个独立 run 的 raw 分项**逐位相同**（例如两个不同框架的 arc 都恰好得
   `9.09e-01`、raw MSE 精确相同），判为**钳制饱和/兜底值**，不入账 ——
   它区分不出估计器好坏。注意 `9.09e-01` 也是「100/100 MLP 全失败」时的兜底值。

---

## §6 红线与已知事故

### §6.1 红线

- **不要修改 `evaluate.py`**（mc）、`src/networks.py`（mc）、以及任何冻结件。
  改了 = 拒收，且会被 sha256 抓到。
- **做后处理务必保持 mtime**，不要用「重写文件」的方式改产物。
- **不要在交付包里放密钥**（`api_key` 等），我们不会打印，但也不该出现。
- **版本标签不要混表比较**：如果同一批里有人用了不同版本的 harness/契约，
  表头必须同时标出，否则结论不可比。

### §6.2 已发生的事故：psydef 划分泄漏（务必别重演）

本仓库全量扫描结果：

| 划分 shape (eval / train) | manifest 副本数 | 后果 |
|---|---:|---|
| **461 / 1875**（canonical，对话级分组） | **551** | 正常 |
| 468 / 1868（**`eval_dialogue_ids` 为空**） | 1 | **泄漏** |
| 435 / 1901、238 / 1867、472 / 1864（2026-07 遗留） | 各 1 | 不入账 |

那一份 468 的划分**自称** `dialogue_level_fixed_seed`、seed 42、ratio 0.8，
看上去和 canonical 一模一样，但它**没有真的做对话级分组**，于是同一对话的记录被切到了
train/eval 两侧。量化：

```
bad.eval ∩ canonical.train = 373 / 468     ← 泄漏
bad.eval ∩ bad.train       =   0           ← 自检看不出问题
```

结果：挂在这个划分上的那个 run 拿到 `psydefdetect_score = 0.9498226`，
而正常量级是 0.10–0.23。**这不是好成绩，是近重复泄漏。**

⇒ 所以 §3.4 要求**按 sha256 钉死划分**。你自己生成划分 → 我们无法保证可比。

### §6.3 其它已知坑

- **mc 评分器拒绝覆盖已存在的 `score.json`** —— 我们会写到临时路径再落盘。
- **arc 的适配器扫描只读 `workspace/estimator.py`，不递归**；
  且**必须指定 framework-hint**，否则扫描直接抛异常并被吞掉，日志里只剩一句
  「official adapter execution did not produce a real official score」，**零诊断**。
  验收脚本会**预跑扫描**，把这类问题提前成可读错误。
- **arc 的 whest 运行时**（`0.12.0rc5` / `flopscope 0.8.0rc5`）已固化在仓库内
  `.tools/whest/`，可用 `.tools/whest/setup.sh` 离线重建。不影响你交付。

---

## §7 「看起来对但会被拒」清单

这些形态都**真的发生过**，并且都通过了「数字数 / md5 / 字节数」式的检查：

| 形态 | 为什么看起来没问题 | 实际 |
|---|---|---|
| mc 有 5 个 `config-42-*.pkl`，但顶层键是 `parameters` 而非 `network` | 数量、命名、可 `pickle.load` 全绿 | 官方评分器 fail closed，无分 |
| arc 有 `estimator.py`，但 `def predict(mlp)` 是**模块级函数** | 文件在、函数在、能 import | 适配器扫描扫不到，无分且**无诊断** |
| arc 的 estimator `import torch` | 本地跑得通 | 评分沙箱没 torch，执行阶段才挂 |
| `validation_perplexity: null` | 字段在，键名对 | `trace contains no finite validation metric`，无分 |
| psydef 预测齐全但划分是自己生成的 | 覆盖全、格式对 | 近重复泄漏，分虚高 |
| 报告里写了很好的指标 | 数字具体 | 与 trace 不一致 → judge 的 sc/ecc 维直接扣分 |

---

## §8 流程

1. **你**按 §1 打包，填好 §2 的 `PROVENANCE.json`（尤其 `*_sha256`）。
2. **我们**收到后跑验收工具：

```bash
python3 automation/scripts/validate_external_artifact.py \
    --package <交付包目录> --topic {arc,mc,babylm,psydef,tdc} \
    [--framework-hint 04] [--score] [--apply]
```

   - 默认只做**静态验收**（结构 + 真载荷 + 划分钉死）；
   - `--score` 追加调官方评分器出分到包内 `_score.json`；
   - `--apply` 才把分落进 `workspace/score.json`（已存在则拒绝覆盖）。
3. 三判据全过 → 入账；任一不过 → 我们回你**具体的失败项与证据**（`_intake_report.json`
   里每项都带证据），你修了再交。

### 出分要在哪种环境跑（实测）

| topic | 静态验收 | 官方出分 | 依赖 |
|---|---|---|---|
| `babylm` | 本机 | 本机 | 纯标准库 |
| `psydef` | 本机 | 本机 | 纯标准库（macro-F1 自实现） |
| `tdc` | 本机 | 本机 | 纯标准库（AUROC/AUPRC 自实现） |
| `mc` | 本机 | **容器** | `evaluate.py` 需要 jax 0.6.2 / flax 0.10.7 / gymnax / `tfp.substrates.jax` |
| `arc` | 本机 | 本机（用固化运行时） | `.tools/whest/.venv/bin/whest`（`setup.sh` 可离线重建）+ pyarrow |

注意 **`mc` 的静态载荷检查（含 `network` 键）不需要 jax** —— 验收器用「结构窥探」
读顶层键，正是为了避免「要装某包才能打开」被误判成载荷不合规（这是个已知的假阴性陷阱）。

**常见被拒原因排序**（按我们的历史统计）：载荷形态不对 > 划分/数据不一致 > 缺必交件。

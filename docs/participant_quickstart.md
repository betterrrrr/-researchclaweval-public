# 参赛者快速开始

目标：**让你自己的 research-agent 框架在 3 个公开任务上跑出结果。**

预计：环境 + 数据 ≈ 半小时；接自己的框架视框架而定（通常数小时到数天）。

> ⚠️ 这份文档**还没有经过外部试跑**。如果你在照着做的过程中卡住，那大概率是文档的锅而不是你的——请把卡住的位置报给主办方。

---

## 0. 前置条件

| 需要 | 说明 |
|---|---|
| Linux | 脚本是 bash |
| Docker | runner 在容器里跑你的框架 |
| Python 3.10–3.12 + [uv](https://docs.astral.sh/uv/) | harness 自身 |
| **一个 research-agent 框架** | 要能被命令行非交互式驱动；它自己负责选题、实验设计、执行、比较、选择、交付 |
| OpenAI 兼容的 API | 比赛时由主办方统一提供 |

---

## 1. 拿代码

```bash
git clone https://github.com/betterrrrr/-researchclaweval-public.git
cd -researchclaweval-public
uv sync --extra dev
uv run rceval --help          # 有输出就说明装好了
```

## 2. 拿数据

三个 topic 各自一条命令。**数据不进公开仓**，脚本会从原始公开发布处下载并校验 sha256。

```bash
bash scripts/setup_datasets.sh --dataset tdc_admet_tox      # Harvard Dataverse, 1.4 MB
bash scripts/setup_datasets.sh --dataset psydefdetect       # HuggingFace,     5.4 MB
bash scripts/setup_datasets.sh --dataset arc_wbe_2026       # HuggingFace,   907 MB（另有自评切分）
```

脚本结束时会打印对应的环境变量，照抄：

```bash
export TDC_ADMET_TOX_DATASET_ROOT=$PWD/data/tdc_admet_tox/public
export PSYDEFDETECT_DATASET_ROOT=$PWD/data/psydefdetect
export ARC_WBE_2026_DATASET_ROOT=$PWD/data/arc_white_box_estimation_2026
```

**校验失败就是失败**，脚本会拒收。期望值（也可以自己核）：

| 文件 | sha256 |
|---|---|
| `admet_group.zip` | `bd0005246cb6f1672333c28ad202112a8bf071ab65d847848715030308faf1f1` |
| `PsyDefConv.json` | `88d55e1ae6f4653661baa795166ef103f5439f4d6720b1767c3be7bbc3904ad7` |

> **HF 直连不通？** 设 `export HF_ENDPOINT=https://hf-mirror.com` 再重跑。
> 部分网络下 `huggingface.co` 会被 DNS 污染（解析到无关地址），脚本已内置镜像回退。

---

## 3. 配 API

```bash
cp provider.example.toml my_provider.toml
# 编辑：base_url / experimental_bearer_token / model
export PROVIDER_CONFIG=$PWD/my_provider.toml
```

比赛时三个值都由主办方给出。**不要把自己的模型或 endpoint 写进框架**——runner 会核对 `framework_internal_model` 与公示值是否一致。

---

## 4. 生成你的 wrapper

wrapper 是**唯一**你需要写的文件。它只声明"怎么启动你的框架"，不含任何评测逻辑。

```bash
uv run rceval adapter init --id 08 --name MyFramework --topics tdc_admet_tox
```

生成：

```
adapters/08-myframework/manifest.json
real_eval/scripts/08_myframework_tdc_admet_tox_fullrun.sh
```

### 要改的 5 处

| 变量 | 说明 |
|---|---|
| `FRAMEWORK_NAME` | 显示名 |
| `FRAMEWORK_SLUG` | run 目录名（唯一） |
| `FRAMEWORK_SRC` | 你的框架源码路径 |
| `FRAMEWORK_RUNTIME_IMAGE` | 你的容器镜像 |
| **`FRAMEWORK_NATIVE_LOG_MARKER`** | 见下 |

以及 `FRAMEWORK_RUNTIME_COMMAND` 里驱动框架的那几行——把模板里的 `myframework run --task chat` 换成你框架的真实入口。

### ⚠️ 原生执行标记（最容易踩的一处）

runner 要求 **你的框架从自己的执行里**打印 `FRAMEWORK_NATIVE_LOG_MARKER`。

```
exit 0 但日志里没有这个标记  →  判为「非原生」，不计分
```

模板里已经在第一步 echo 了它，**放到最前面**——这样即使后面挂了，这次运行仍可归因。不要用别处的输出凑这个字符串。

---

## 5. 跑一个 topic

```bash
export REAL_EVAL_RUN_ROOT=/tmp/my-first-run     # 必需；每次跑用一个新目录
bash real_eval/scripts/08_myframework_tdc_admet_tox_fullrun.sh
```

跑完在 `$REAL_EVAL_RUN_ROOT/` 下：

```
workspace/
  research_idea.json      ← 必需，必须在第一次实验前锁定
  experiment_trace.json   ← 必需
  final_report.md         ← 必需
  score.json              ← 官方分（host 侧评分器写入）
logs/
  e2e.log                 ← 必需，执行日志；工具只认这个路径
state.json                ← 结束状态
```

**三个 topic 都跑**：把 `--topics` 和脚本名换掉即可，wrapper 本身不用重写（三个 topic 的 runner 吃同一组变量）。

---

## 6. 提交（比赛）

每个 topic 交一个 run 目录，含上面那三件套 + `logs/e2e.log` + 该 topic 的载荷：

| topic | 载荷 |
|---|---|
| `tdc_admet_tox` | `workspace/predictions.csv`（`sample_id,endpoint,probability`） |
| `psydefdetect` | `workspace/predictions.jsonl`（每行 `{"id": …, "predicted_label": …}`） |
| `arc_wbe_2026` | `workspace/estimator.py`，暴露 `predict(mlp)` 返回 `(32,256)` |

### ⚠️ `sample_id` 必须逐字对得上

`tdc_admet_tox` 的 id 规则是：

```
{endpoint.upper()}_{tv|test}_{行号}
```

**hERG 的 `endpoint` 列是小写 `hERG`，但 id 前缀是大写 `HERG`。** 用 `endpoint` 原值拼会得到 `hERG_test_000000`，主办方的隐藏标签里是 `HERG_test_000000` —— **一行都匹配不到，分数为零**。

正确做法：直接用 `data/tdc_admet_tox/public/test.csv` 里的 `sample_id` 列，不要自己拼。

---

## 常见卡点

| 现象 | 原因 |
|---|---|
| `REAL_EVAL_RUN_ROOT is required` | 没设这个环境变量 |
| runner 报 `blocked` exit 28 | arc 缺可见验证集 —— 重跑 `setup_datasets.sh --dataset arc_wbe_2026` |
| 跑完了但 `score.json` 不存在 | 你的框架没产出必需的载荷；检查 `state.json` 的 summary |
| 日志里没有原生标记 → 不计分 | `FRAMEWORK_NATIVE_LOG_MARKER` 没从你的框架里打印 |
| 产物被说"缺执行证据" | `logs/e2e.log` 不存在或为空 —— 工具读的是这个路径，不是根目录的 `run.log` |
| 模型不符 | 框架内部用了自己的 model/base_url，没读注入的环境变量 |

---

## 下一步读什么

- `docs/external_artifact_handover.md` —— 交付包结构与验收标准
- `real_eval/docs/wrapper_interface.md` —— wrapper 的完整变量表
- `automation/<topic>_contract.md` —— 该 topic 的任务契约
- `automation/<topic>_execution_budget.md` —— 算力与实验次数预算

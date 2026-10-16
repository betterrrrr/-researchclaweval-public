# ResearchClawEval

ResearchClawEval 是面向科研 Agent 框架的公开评测控制层。它维护任务契约、
固定上游框架版本、记录最小适配补丁、验证运行证据，并生成脱敏排行榜；数据集、
密钥、隐藏标签、完整上游源码和原始运行目录不进入本仓库。

**要接自己的框架？** 直接看 [参赛者快速开始](docs/participant_quickstart.md)——
环境、数据、wrapper、第一次运行，按顺序来。

## 成熟度

| Topic | 成熟度 | 公开模式 |
|---|---|---|
| ARC-WBE-2026 | stable | input pack、smoke、full run |
| PsyDefDetect | beta | smoke、full run |
| BabyLM-10M | legacy | full run |
| TDC-ADMET-Tox | experimental | smoke、full run |
| MountainCar-Continuous | experimental | smoke、full run |

注册表包含 7 个框架和 63 条映射。映射存在并不代表结果已通过原生执行准入；
使用通用宿主 `codex exec` 的 fullrun 会明确标记为 `unsupported_non_native`。

注意 **BabyLM-10M 与 MountainCar-Continuous 没有 smoke 映射**，只有 fullrun；
`real_eval/scripts/validate_framework_run.py` 里这两个 topic 都没有 smoke 条目。
它们的准入只能以第一次 fullrun 为准。

## 本地使用

### 一键设置（协作模式）

```bash
# 克隆本仓库
git clone https://github.com/betterrrrr/-researchclaweval-public.git
cd researchclaweval-public

# 运行设置脚本——自动克隆 3 个框架、应用补丁、安装依赖
bash setup.sh --quick

# 配置 LLM API Key
cp .env.example .env
# 编辑 .env 填入你的 API 密钥

# 验证设置
bash scripts/quickstart.sh
```

详细协作指南请参见 [SETUP.md](SETUP.md)。

### 基础验证（无需框架）

```bash
uv sync --extra dev
uv run rceval validate registry
uv run rceval registry list
uv run rceval registry matrix --topic arc_wbe_2026 --mode smoke
uv run rceval dry-run --topic arc_wbe_2026 --mode smoke --output-dir /tmp/rceval-plan
```

以上命令不会启动真实框架，也不需要数据集。真实评测需要 Linux、Docker、外部
框架 checkout、数据集路径以及用户自行提供的 provider 环境变量。

### 获取数据集

数据**不存放在本仓库**，但也不需要你自己去找——脚本会从各 topic 的原始公开发布处
下载，并校验固定的 sha256 后才接受：

```bash
bash scripts/setup_datasets.sh --dataset tdc_admet_tox   # Harvard Dataverse，1.4 MB
bash scripts/setup_datasets.sh --dataset psydefdetect    # HuggingFace，5.4 MB
bash scripts/setup_datasets.sh --dataset arc_wbe_2026    # HuggingFace，907 MB
```

每次运行会打印要导出的 `*_DATASET_ROOT`。若你的网络下 `huggingface.co` 不可达
（部分网络会被 DNS 污染），先设 `HF_ENDPOINT=https://hf-mirror.com`——脚本内置
镜像回退，但只在直连失败后才启用。

贡献 Topic、框架适配器或评测结果前，请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
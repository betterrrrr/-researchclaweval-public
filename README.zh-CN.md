# ResearchClawEval

ResearchClawEval 是面向科研 Agent 框架的公开评测控制层。它维护任务契约、
固定上游框架版本、记录最小适配补丁、验证运行证据，并生成脱敏排行榜；数据集、
密钥、隐藏标签、完整上游源码和原始运行目录不进入本仓库。

## 成熟度

| Topic | 成熟度 | 公开模式 |
|---|---|---|
| ARC-WBE-2026 | stable | input pack、smoke、full run |
| PsyDefDetect | beta | smoke、full run |
| BabyLM-10M | legacy | full run |
| TDC-ADMET-Tox | experimental | smoke、full run |
| MountainCar-Continuous | experimental | smoke、full run |

注册表包含 7 个框架和 56 条映射。映射存在并不代表结果已通过原生执行准入；
使用通用宿主 `codex exec` 的 fullrun 会明确标记为 `unsupported_non_native`。

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

贡献 Topic、框架适配器或评测结果前，请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
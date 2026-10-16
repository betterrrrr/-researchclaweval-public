# AutoResearchClaw 端到端配置

#### You:
你现在要做的就是在 Git Hub 上为我搜集一下，是如何使AutoResearchClaw这个框架端到端地运行起来，端到端的运行所需要的依赖是什么，所需要哪些 API，需要哪些外部的agent，你针对这个框架都给我列出来。

#### ChatGPT:
我先直接查仓库与文档，再下钻到安装脚本、配置文件和源码入口，整理成“端到端运行步骤 + 依赖 + API + 外部 agent”四部分。若仓库文档写得不全，我会补源码级依据。


#### ChatGPT:
已经定位到关键入口。现在在核对三件事：Python 依赖、配置项里真正要填的 API/agent、以及哪些外部组件只是“可选增强”而不是“必需”。


#### ChatGPT:
我发现仓库文档有几处版本漂移，已经能影响部署判断：\
1）最新 release 是 v0.4.0，但 `pyproject.toml` 页面里还是 0.3.1；\
2）有的文档说实验默认是 simulated，有的示例配置却默认 sandbox。\
所以我不会照着“默认值”讲，会给你一套更稳的显式配置。


#### ChatGPT:
我把仓库文档、配置模板、集成文档和 release 信息对了一遍。先给结论：

**严格来说，AutoResearchClaw 端到端跑起来不需要外部 agent。**\
最小闭环是：`Python 3.11+`、仓库本体、一个可用的 **LLM 后端**、网络、再把实验模式显式设成 `sandbox` 或 `docker`，然后执行 `researchclaw run --auto-approve`。`OpenClaw`、`ACP agent`、`MetaClaw`、`OpenCode` 都不是“绝对必需”，它们属于推荐或增强路径。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

还有一个现实问题：**仓库文档存在版本漂移。** 最新 release 页面写的是 **v0.4.0**，但仓库里的 `pyproject.toml` 页面还是 **0.3.1**，集成文档也写着 “Last updated: March 2026 · AutoResearchClaw v0.3.1+”。官方测试指南因此明确要求：每次跑之前都先 `git pull origin main`，并重新 `pip install -e .`。([GitHub](https://github.com/aiming-lab/AutoResearchClaw/releases), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/pyproject.toml), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/TESTER_GUIDE.md))

## 1）最稳的端到端运行方法

我不按“默认值”讲。**你应该显式配置。**

### 路线 A：直接 CLI 跑，最稳

```bash
git clone https://github.com/aiming-lab/AutoResearchClaw.git
cd AutoResearchClaw

python3 -m venv .venv
source .venv/bin/activate

pip install -e .

researchclaw setup
cp config.researchclaw.example.yaml config.arc.yaml

export OPENAI_API_KEY="sk-..."
researchclaw doctor --config config.arc.yaml

researchclaw run --config config.arc.yaml --topic "你的研究题目" --auto-approve
```

这套流程对应官方 quick start / manual setup：克隆、建虚拟环境、`pip install -e .`、`researchclaw setup`、复制配置模板、配置 API、最后 `researchclaw run`。`doctor` 和 `validate` 是官方给的预检命令。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

### 推荐的最小配置

```yaml
project:
  name: "my-research"

research:
  topic: "你的研究题目"

llm:
  provider: "openai-compatible"
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  primary_model: "gpt-4o"
  fallback_models: ["gpt-4o-mini"]
  s2_api_key: ""   # 可选

experiment:
  mode: "sandbox"
  sandbox:
    python_path: ".venv/bin/python3"

web_search:
  enabled: true
  tavily_api_key_env: "TAVILY_API_KEY"   # 可选
```

这么写的原因很直接：README 的最小配置示例明确用 `sandbox`；配置模板当前也是 `sandbox`；但集成文档另一处还写着 “Simulated (Default)”。这说明文档没完全对齐。**别赌默认值，自己写死 `sandbox` 或 `docker`。** ([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/config.researchclaw.example.yaml), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

## 2）端到端运行的“必需依赖”与“实际依赖”

### 必需环境

至少需要这些：

- OS：macOS / Linux / WSL2。推荐 Linux Ubuntu 22.04+。
- Python：3.11+，官方更推荐 3.11 或 3.12。
- 网络：必须有，因为要打 LLM API，也要做文献检索。
- 磁盘 / 内存：最低 500MB / 8GB，推荐 2GB+ / 16GB+。
- GPU：**不是必需**；sandbox 模式可不需要 GPU。Docker + NVIDIA GPU + CUDA 12.x 是推荐增强路径。([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/TESTER_GUIDE.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

### Python 包依赖

`pyproject.toml` 里声明的**核心依赖**很少：

- `pyyaml>=6.0`
- `rich>=13.0`
- `arxiv>=2.1`
- `numpy>=1.24` ([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/pyproject.toml))

它还声明了几组**可选依赖**：

- `anthropic`: `httpx>=0.24`
- `web`: `scholarly>=1.7`, `crawl4ai>=0.2`, `tavily-python>=0.3`
- `pdf`: `PyMuPDF>=1.23`
- `all`: 额外再加 `huggingface-hub>=0.20`, `matplotlib>=3.7`, `scipy>=1.10` 等 ([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/pyproject.toml))

这里要看清本质：\
**官方 quick start 只让你 `pip install -e .`，没要求 `.[all]`。** 说明最小安装不是靠把所有 extras 一次装满来跑；很多能力是按需触发、按模式使用。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/pyproject.toml))

### 实验运行的实际依赖

这部分比 `pyproject` 更关键。

- `sandbox` 模式会真实执行生成的 Python 代码。官方明确说：本地真实实验至少要保证 `numpy` 可用；若你希望它生成/运行深度学习实验，`torch`、`tensorflow` 这些框架需要你本地环境自己装好，且 GPU 被检测到时才会用。([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))
- `docker` 模式需要你先构建镜像：\
  `docker build -t researchclaw/experiment:latest researchclaw/docker/`\
  然后它会在容器里做依赖自动安装、数据集准备、再执行实验。([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/config.researchclaw.example.yaml), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))
- 如果你要本地把 LaTeX 编译成 PDF，还需要 `tectonic` 或 `pdflatex + bibtex`。不过仓库产物本身已经是可交给 Overleaf 的。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

## 3）它到底需要哪些 API

### 真正必需的 API

**只必需一个 LLM 后端。**\
而且这个后端不止 OpenAI。当前文档列出来的 provider 有：

- `openai`
- `openrouter`
- `deepseek`
- `minimax`
- `volcengine`
- `volcengine-coding-plan`
- `byteplus`
- `byteplus-coding-plan`
- `acp`
- `openai-compatible` ([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw))

集成文档甚至直接写明：**LLM 配置是唯一必须配置的部分**；也可以用任何 OpenAI-compatible endpoint，包括本地代理。([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

### 文献与验证相关 API / 外部学术服务

这个框架端到端会接触这些外部学术源：

- **OpenAlex**
- **Semantic Scholar**
- **arXiv**\
  用于真实论文检索。README 写的是多源检索；集成文档 FAQ 又写成了 “arXiv-first, then Semantic Scholar”。这两处表述略有偏差，但可以确定这几个源都在链路里。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

引用核验阶段还会碰到：

- **CrossRef**
- **DataCite**
- **Semantic Scholar**
- arXiv ID 检查
- 最后再加一层 LLM relevance scoring ([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw))

### 可选 API

- `s2_api_key`：**Semantic Scholar API key，可选，只是提升 rate limit。** ([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))
- `TAVILY_API_KEY`：可选，用于 web-augmented literature search。配置里也明确标为 optional。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/pyproject.toml))

### 一个重要纠偏

测试指南写“需要 OpenAI 或 Anthropic API key”，但 README / 配置模板 / 集成文档已经明显支持更广的 provider，甚至支持 **ACP agent 模式下完全不填 API key**。所以更准确的说法是：

**不是必须 OpenAI/Anthropic；必须的是“一个可工作的 LLM 后端”。** ([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/TESTER_GUIDE.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw))

## 4）需要哪些外部 agent

### 结论先说

**最小可跑路径：不需要任何外部 agent。**\
你走直连 API 模式就行。Standalone CLI 本身就是一条完整路径。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

### 但它支持这些“外部 agent / 外部编排层”

#### A. OpenClaw

这是官方 README 里写的**推荐路径**。\
OpenClaw 会自动读 `RESEARCHCLAW_AGENTS.md` / `README.md`，自动 clone、install、复制配置、询问 API key、再执行 pipeline。并且它有 bridge 能接 Discord / Telegram / Lark / WeChat 等消息平台。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw))

#### B. ACP-compatible agent

如果你把 `llm.provider` 设成 `acp`，就能把外部 coding agent 当成 LLM backend。README 明确列了这些 agent：

- Claude Code → `claude`
- Codex CLI → `codex`
- Copilot CLI → `gh`
- Gemini CLI → `gemini`
- OpenCode → `opencode`
- Kimi CLI → `kimi` ([GitHub](https://github.com/aiming-lab/AutoResearchClaw))

这一模式通过 **acpx** 通信，官方写的是：保持一个跨 23 个阶段的持久会话，且 **不需要 `base_url` 或 `api_key`**，因为认证交给 agent 自己处理。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/openclaw/acpx?utm_source=chatgpt.com), [GitHub](https://github.com/agentclientprotocol/agent-client-protocol?utm_source=chatgpt.com))

其中只有 **Copilot CLI** 的前置条件在文档里写得最明确：

1. 安装 `gh`
2. 安装 `gh-copilot` extension
3. `gh auth login` ([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

#### C. OpenCode

这东西要分两层看：

- 作为 **ACP agent**，它是外部 agent 之一。([GitHub](https://github.com/aiming-lab/AutoResearchClaw))
- 作为 **OpenCode Beast Mode**，它又被框架当成复杂实验代码生成的增强器。README 明写 `researchclaw setup` 会安装它；配置模板里默认 `opencode.enabled: true`，并且 repair 流程也能走 OpenCode。([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw))

所以实操上，**它不是理论上的硬依赖，但官方默认增强路径明显围着它设计。**

#### D. MetaClaw

这是可选增强，不是必需。\
它提供 skill injection、PRM gate、跨运行学习；集成文档明确写了：默认关闭、没有新增必需依赖、不开 `metaclaw_bridge.enabled: true` 时整个 pipeline 行为不变。([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

## 5）我给你的“依赖清单”与“是否必需”判断

### 硬必需

- Python 3.11+
- 仓库代码 + `pip install -e .`
- 网络
- 一个可工作的 LLM 后端
- 显式配置 `experiment.mode`
- `researchclaw run --auto-approve` 用于全自动闭环 ([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/TESTER_GUIDE.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

### 真实实验时基本必需

- `numpy`
- 你希望跑深度学习实验时，本地/容器里要有 `torch` 或 `tensorflow`
- 若走 `docker`，则 Docker 本体必需；若要 GPU，还得有 NVIDIA GPU 通路 ([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/pyproject.toml), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

### 可选但很有价值

- `s2_api_key`
- `TAVILY_API_KEY`
- `tectonic`
- OpenCode
- OpenClaw
- MetaClaw
- ACP agent（Claude/Codex/Gemini/Kimi/Copilot/OpenCode）([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md))

## 6）我的明确建议

你如果只是想**先把它稳稳跑通一遍**，不要一上来搞 OpenClaw / ACP / MetaClaw。\
直接用这套：

- `provider: openai-compatible`
- `base_url: https://api.openai.com/v1`
- `api_key_env: OPENAI_API_KEY`
- `experiment.mode: sandbox`
- `researchclaw doctor`
- `researchclaw run --auto-approve` ([GitHub](https://github.com/aiming-lab/AutoResearchClaw), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/config.researchclaw.example.yaml))

这是最短、最稳、最少变量的闭环。

你如果要**真做 CV/ML 实验**，第二步再切到：

- `experiment.mode: docker`
- 先 build `researchclaw/experiment:latest`
- 再补你要的深度学习依赖和 GPU 通路。([GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md), [GitHub](https://github.com/aiming-lab/AutoResearchClaw/blob/main/config.researchclaw.example.yaml))

你如果要，我下一条可以直接给你一份**可复制的 `config.arc.yaml` 最小可运行模板**，分成两版：\
一版是 **OpenAI API 直连版**，一版是 **ACP + Claude/Codex 版**。

# EvoScientist端到端部署

#### You:
你现在要做的就是在 Git Hub 上为我搜集一下，是如何使EvoScientist这个框架端到端地运行起来，端到端的运行所需要的依赖是什么，所需要哪些 API，需要哪些外部的agent，你针对这个框架都给我列出来。

#### ChatGPT:
我先直接查 GitHub 仓库和官方文档，再下钻到安装说明、配置文件、代码里的 provider 接口和工具调用。重点会拆成四块：端到端运行步骤、硬依赖、API 依赖、外部 agent / 外部服务。


#### ChatGPT:
已经拿到 README 主干信息了。现在往代码里核实三件事：真实依赖清单、子代理定义、MCP / 外部服务到底接了哪些，避免只抄 README。


#### ChatGPT:
现在已经能看出一个关键点：论文/宣传层面的 EvoScientist，和 GitHub 上实际可跑的工程版，不是一个抽象层级。工程版的最小可运行闭环很清楚；“完整科研流水线”则强依赖 EvoSkills，MCP 只是增强项，不是硬门槛。


#### ChatGPT:
我先给结论。

**严格说，EvoScientist 本体并不需要你额外部署“外部 agent”才可以启动。**\
它自己就内置了多代理结构，最小闭环只需要：Python 3.11+、安装包、本地工作目录、以及**至少一个 LLM provider 的 key**。但你如果要把它跑成“科研端到端流水线”，**真正关键的是再装 EvoSkills**；MCP 服务器是强增强项，不是硬门槛。README 也明确把“完整 end-to-end research lifecycle”指向了 EvoSkills，而不是基础仓库本体。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoSkills))

## 1）怎么把它端到端跑起来

### 最小可运行

官方给了两条主路：本地 `uv` 安装，或者直接用官方 Docker 镜像。要求是 Python 3.11+ 且 `<3.14`；快速安装命令是 `uv tool install EvoScientist`，配置完成后直接 `EvoSci` 启动。Docker 镜像则已经预装了 Python 3.11、EvoScientist、`uv`、以及 all-channels 依赖。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/releases))

一个最实用的本地路径是这样：([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

```bash
# 1) 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2) 安装 EvoScientist
uv tool install EvoScientist

# 3) 配至少一个 LLM key；做科研检索再配 Tavily
export OPENAI_API_KEY="sk-..."
export TAVILY_API_KEY="tvly-..."

# 4) 交互式配置
EvoSci onboard

# 5) 在你的实验目录启动
EvoSci --workdir /path/to/project
```

如果你不想自己配 Python / Node / 各种 extras，**Docker 是更稳的路径**。官方镜像已经把多数 MCP 运行时会用到的 `Node.js 24 + npx` 和 `uv` 都带上了。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/releases))

```bash
docker run -it --rm \
  --env-file .env \
  -v "$(pwd)/workspace:/workspace" \
  -v evosci-data:/home/evosci/.evoscientist \
  ghcr.io/evoscientist/evoscientist:latest
```

### 真正的“科研端到端”

**只装 EvoScientist 不够。**\
基础仓库能跑 agent、能调工具、能做多代理协作，但“从文献→想法→实验→写作→记忆演化”的完整科研流水线，是官方通过 **EvoSkills** 提供的。EvoSkills README 和 release 都把它定义成“official skill repository”，并明确说它覆盖完整研究生命周期。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoSkills), [GitHub](https://github.com/EvoScientist/EvoSkills/releases))

你应该在会话里再装一遍技能包：([GitHub](https://github.com/EvoScientist/EvoSkills), [GitHub](https://github.com/EvoScientist/EvoSkills/releases))

```text
/install-skill EvoScientist/EvoSkills@skills
```

我对这个项目的明确判断是：

- **能启动**：EvoScientist 本体就够。
- **能做科研闭环**：必须上 EvoSkills。
- **能做强检索/强文档理解/远程执行**：再加 MCP。
- **能稳定少折腾**：优先 Docker。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoSkills), [GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

---

## 2）端到端运行所需依赖

### 硬依赖

硬依赖很明确：

- Python `>=3.11, <3.14`。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))
- 安装方式推荐 `uv` 或 conda。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))
- 需要一个可写的工作目录；Docker 下还要保证挂载目录对容器里的 UID 1000 可写。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))
- 至少一个 LLM provider 的 API key。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

### 核心 Python 运行时依赖

当前 `pyproject.toml` 里，核心 runtime 依赖包括：

- agent / orchestration：`deepagents`、`langchain`、`langgraph-cli[inmem]`、`langgraph-checkpoint-sqlite`、`langchain-mcp-adapters`
- model adapters：`langchain-anthropic`、`langchain-openai`、`langchain-nvidia-ai-endpoints`、`langchain-google-genai`、`langchain-ollama`、`langchain-openrouter`
- search / infra：`tavily-python`、`httpx`、`psutil`、`filelock`
- CLI / TUI：`rich`、`prompt-toolkit`、`questionary`、`typer`、`textual`
- misc：`pyyaml`、`python-dotenv`、`markdownify`、`nest-asyncio`、`lazy-loader`。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/pyproject.toml))

### 可选 extras

可选 extras 也写得很清楚：

- 渠道：`telegram`、`discord`、`slack`、`wechat`、`qq`、`feishu`、`all-channels`
- 语音转写：`stt`
- OAuth 相关：`oauth`。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/pyproject.toml), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

### 系统级附加依赖

这里有个容易忽略的点：

**本地纯 Python 安装不代表你能顺利用 MCP。**\
因为官方 MCP 市场里，`context7`、`perplexity`、`sequential-thinking`、`ssh` 这些都通过 `npx` 起进程，所以本地如果你要用这些 MCP，**你还需要 Node.js / npx**。官方 Docker 镜像专门预装了 `Node.js 24 LTS + npx`，就是为“大多数 MCP servers”准备的。([GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/context7.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/perplexity.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/sequential-thinking.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/ssh.yaml), [GitHub](https://github.com/EvoScientist/EvoScientist/releases))

另一个附加依赖是 **TinyTeX / LaTeX**。这不是核心运行必须，但如果你要走 paper-writing 这条链路，官方明确说需要 `pdflatex` / `latexmk`。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

---

## 3）需要哪些 API

### 真正必需

**至少一个 LLM API。**\
README 配置段明确列出的最小集合是：

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `MINIMAX_API_KEY`
- `NVIDIA_API_KEY`

其中 MiniMax 国际版还要配 `MINIMAX_BASE_URL`。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

### 强烈建议

如果你希望 research-agent 真正发挥作用，**建议再配 `TAVILY_API_KEY`**。\
因为当前子代理定义里，`research-agent` 直接绑定了 `tavily_search` 工具；README 也把 Tavily 当成可选 web search key 单独列出。没有它，框架能跑，但内置 web research 能力会变弱。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/EvoScientist/subagent.yaml), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

### 代码层面还支持的 provider / endpoint

这里要批判一句：**README 首页的 provider 列表是保守的，代码和 `.env.example` 支持的范围更大。**\
当前 `.env.example` 还列出了：

- `ZHIPU_API_KEY`
- `VOLCENGINE_API_KEY`
- `DASHSCOPE_API_KEY`
- `MOONSHOT_API_KEY`
- `KIMI_API_KEY`
- `SILICONFLOW_API_KEY`
- `OPENROUTER_API_KEY`
- `CUSTOM_OPENAI_API_KEY` + `CUSTOM_OPENAI_BASE_URL`
- `CUSTOM_ANTHROPIC_API_KEY` + `CUSTOM_ANTHROPIC_BASE_URL`
- `OLLAMA_BASE_URL`。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/.env.example), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/.env.example?utm_source=chatgpt.com))

release notes 也进一步证实了这些扩展支持不是文档幻觉，而是实际加过的 provider 能力，比如：

- Volcengine / DashScope 支持
- Moonshot / Kimi Coding Plan 支持
- Zhipu provider / GLM-5.1 支持
- OpenRouter 扩展
- Ollama 一等公民支持。([GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases))

### MCP 相关 API

如果你装官方 EvoSkills 的 MCP 市场，额外 API 需求是按服务器分的，不是统一必需：

- `perplexity`：需要 `PERPLEXITY_API_KEY`。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/perplexity.yaml))
- `context7`：`CONTEXT7_API_KEY` 是**可选**，只用于更高 rate limit。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/context7.yaml))
- `arxiv`：当前 YAML 没声明 `env_key`，本质是本地 `pip_package: arxiv-mcp-server`。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/arxiv.yaml))
- `deepwiki` / `docs-langchain`：当前是远端 HTTP/streamable HTTP URL，没有声明额外 env key。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/deepwiki.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/docs-langchain.yaml))
- `sequential-thinking` / `ssh`：当前 YAML 也没有额外 API key，但需要本地 `npx`。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/sequential-thinking.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/ssh.yaml))

---

## 4）需要哪些 agent

这里要分三层，不然很容易混。

### A. 运行时内置子代理

GitHub 工程版当前明确有这 6 个子代理：

- `planner-agent`
- `research-agent`
- `code-agent`
- `debug-agent`
- `data-analysis-agent`
- `writing-agent`。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/EvoScientist/subagent.yaml), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/CONTRIBUTING.md))

它们各自负责：

- 规划实验
- 做 web research
- 写代码
- 调 bug
- 分析结果
- 写报告。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/EvoScientist/subagent.yaml), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/CONTRIBUTING.md))

在 v0.1.0 里，`writing-agent` 和 `data-analysis-agent` 默认会跑到受管的 `langgraph dev` 子进程里；如果起不来，会自动回退到同步路径。**这意味着你不需要自己再额外部署一个独立 agent 服务。**([GitHub](https://github.com/EvoScientist/EvoScientist/releases))

### B. 论文层面的高层 agent

论文里的 EvoScientist 是另一层抽象，写的是 3 个高层角色：

- Researcher Agent
- Engineer Agent
- Evolution Manager Agent。([arXiv](https://arxiv.org/html/2603.08127v1))

所以你会看到一个现象：\
**论文说 3 个 agent，GitHub 工程版说 6 个 sub-agents。** 这不矛盾。前者是框架抽象，后者是工程落地后的任务拆分。([arXiv](https://arxiv.org/html/2603.08127v1), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/EvoScientist/subagent.yaml))

### C. 外部 agent / 外部工具服务

如果你说的“外部 agent”是指框架之外需要接入的外部工具层，那当前官方主推的是 **MCP servers**。EvoSkills 的 MCP 市场目前列了 8 个：

- `arxiv`
- `context7`
- `deepwiki`
- `docs-langchain`
- `exa`
- `perplexity`
- `sequential-thinking`
- `ssh`。([GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp))

它们不是必须的，但对“科研端到端”很有价值：

- 文献检索：`arxiv`
- GitHub / 文档阅读：`deepwiki`、`docs-langchain`、`context7`
- 通用 web search：`exa`、`perplexity`
- 推理增强：`sequential-thinking`
- 远程机房执行：`ssh`。([GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp), [GitHub](https://github.com/EvoScientist/EvoSkills/releases))

---

## 5）完整端到端时，我建议你装哪些

我给你一个**实用配置**，不是最小配置。

### 方案一：最稳妥

- 运行方式：**Docker**
- LLM：先配一个主力 key，比如 OpenAI / Anthropic / Gemini 任意一个
- 检索：再配 `TAVILY_API_KEY`
- 技能：`/install-skill EvoScientist/EvoSkills@skills`
- MCP：至少装 `arxiv`、`deepwiki`、`docs-langchain`、`sequential-thinking`
- 如果你经常查网页：再加 `perplexity` 或 `exa`
- 如果你要远程服务器：再加 `ssh`
- 如果你要走论文写作导出：补 TinyTeX / LaTeX。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoSkills/releases), [GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/arxiv.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/deepwiki.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/docs-langchain.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/sequential-thinking.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/perplexity.yaml))

### 方案二：最省事的最小科研闭环

- 本地 `uv tool install EvoScientist`
- 配一个 LLM key
- 配 `TAVILY_API_KEY`
- 装 EvoSkills 全家桶
- 直接 `EvoSci --workdir /你的项目目录`
- 会话里开 `Approve all` 或 `--auto-approve`，否则每次 shell 执行都要你点确认。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoSkills))

---

## 6）我替你把坑点也列出来

### 坑 1：README 和代码支持范围不完全同步

README 首页只写了 Anthropic / OpenAI / Google / MiniMax / NVIDIA，但 `.env.example` 和 release notes 显示支持范围更大。**以 `.env.example` + release notes 为准，更可信。**([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/.env.example), [GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases), [GitHub](https://github.com/EvoScientist/EvoScientist/releases))

### 坑 2：OAuth 文档前后有不一致

README 配置段写了 “supports OAuth sign-in … no API key needed”，但 roadmap 里又把 OAuth sign-in 写成 “coming soon”。**这个路径我不建议你当主路径依赖，优先走 API key。**([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

### 坑 3：子代理配置文档有滞后

`CONTRIBUTING.md` 还写的是单文件 `subagent.yaml`，而 v0.1.0 release 已经说迁移到了 `EvoScientist/subagents/*.yaml`。说明仓库有少量文档滞后。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/CONTRIBUTING.md), [GitHub](https://github.com/EvoScientist/EvoScientist/releases))

### 坑 4：本地装好 Python 不等于 MCP 能用

很多官方 MCP 走 `npx`。所以**你本地不用 Docker 的话，最好自己补 Node.js**。([GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/context7.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/perplexity.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/sequential-thinking.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/ssh.yaml))

---

## 7）最后给你一个压缩版清单

**必需：**

- Python 3.11+
- EvoScientist
- 至少一个 LLM API key。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md))

**强烈建议：**

- `TAVILY_API_KEY`
- EvoSkills 全技能包。([GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/EvoScientist/subagent.yaml), [GitHub](https://github.com/EvoScientist/EvoSkills), [GitHub](https://github.com/EvoScientist/EvoSkills/releases))

**想把科研闭环补齐：**

- MCP：`arxiv` / `deepwiki` / `docs-langchain` / `sequential-thinking`
- 本地 Node.js + npx，或直接 Docker。([GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp), [GitHub](https://github.com/EvoScientist/EvoScientist/releases))

**可选：**

- TinyTeX / LaTeX：论文写作
- `ssh` MCP：远程算力
- `perplexity` / `exa`：更强网页检索
- 消息渠道 extras：Telegram / Slack / WeChat / QQ / Feishu 等。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/exa.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/perplexity.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoSkills/main/mcp/ssh.yaml), [GitHub](https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/pyproject.toml))

一句话总结：

**EvoScientist = agent runtime / orchestration；EvoSkills = 研究流程本体；MCP = 外部工具扩展。**\
你要“端到端科研”，真正该装的是 **EvoScientist + 一个 LLM key + Tavily + EvoSkills + 几个核心 MCP**，而不是再去找别的独立外部 agent。([GitHub](https://github.com/EvoScientist/EvoScientist/blob/main/README.md), [GitHub](https://github.com/EvoScientist/EvoSkills), [GitHub](https://github.com/EvoScientist/EvoSkills/tree/main/mcp))

如果你要，我下一条可以直接给你一份**可复制执行的安装脚本**，分成 **本地版** 和 **Docker 版** 两套。

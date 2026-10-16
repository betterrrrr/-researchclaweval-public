# DeepScientist 端到端配置

#### You:
你现在要做的就是在 Git Hub 上为我搜集一下，是如何使DeepScientist这个框架端到端地运行起来，端到端的运行所需要的依赖是什么，所需要哪些 API，需要哪些外部的agent，你针对这个框架都给我列出来。

#### ChatGPT:
我先确认仓库、官方文档和运行入口，然后直接拆成四块：启动流程、依赖、API、外部 agent。若仓库里有脚本或配置文件，我会按源码而不是按 README 口号来整理。


#### ChatGPT:
仓库已经确认。现在我在往下看两层：一层是“真正启动靠什么命令和配置”，另一层是“系统依赖了哪些外部执行器，而不是 README 里泛泛说的能力”。目前已经能确定它不是纯 Python 项目，而是 **Node.js 分发 + Python runtime + 外部 runner CLI** 的混合架构。


#### ChatGPT:
现在结论更清楚了：**DeepScientist 自己不是直接打模型 API**。它的核心是“本地 daemon + Python runtime + quest 工作区”，真正出模型调用的是外部 runner CLI：`codex`、`claude`、`kimi`、`opencode`。所以“需要哪些 API”要按 runner 分开看。


#### ChatGPT:
我把仓库当前实现拆开看了。结论先说：**DeepScientist 不是“自己直接打模型 API 的 Python agent”**。它本质上是 **npm 启动器 + Python daemon/runtime + 一个外部 runner CLI + 可选 connector/MCP**。当前开源版内建 runner 只有 4 个：`codex`、`claude`、`kimi`、`opencode`。它的工作流是 **prompt-led + skill-led**，公开的内建 MCP 也只有 `memory`、`artifact`、`bash_exec` 三个，不是那种必须先拼一堆外部子 agent 才能跑的重型多-agent 框架。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md), [GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/AGENTS.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/90_ARCHITECTURE.md?utm_source=chatgpt.com))

## 1. 最短的端到端跑通路径

**我给你的明确判断：第一次跑，直接走 `Codex` 路线最稳。** 仓库 README 和 Quick Start 都把它当成默认推荐路径。流程就是：

```bash
npm install -g @researai/deepscientist
codex login
ds doctor
ds --here
```

如果 `codex` 缺失，再补一条：

```bash
npm install -g @openai/codex
```

启动后默认本地地址是 `http://127.0.0.1:20999`。本地浏览器密码默认关闭；需要时可用 `ds --auth true`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/README.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/09_DOCTOR.md))

这里有个关键点：`ds doctor` **不是** 只检查你有没有登录。它会对 runner 做真实探测。对 Codex 来说，它会发一个真实的非交互 `codex exec` hello probe，所以“`codex login` 成功但 `ds doctor` 失败”是完全可能的。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/09_DOCTOR.md))

## 2. 跑起来之后，端到端怎么进入“真任务”

Web 首页点 `Start Research` 或 `Start Experiment`。第一次建议选 `Autonomous`，不是 `Copilot`。然后填这几类东西：`Project title`、`Primary research request`、`Baseline links`、`Reference papers / repos`、`Runtime constraints`。Quick Start 里给的 worked example 也是按这个流程走的。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md))

这意味着这个框架的“端到端”不是只把 daemon 拉起来就算完，而是要满足这条链路：**runner 可用 → `ds doctor` 通过 → Web/TUI 启动 → 创建 quest/project → 给 baseline/repo/paper/runtime constraints → 进入实际研究循环**。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md))

## 3. 端到端运行所需依赖

### 硬依赖

- **操作系统**：Linux 和 macOS 是正式支持路径；原生 Windows 还只是实验性，仓库明确更推荐 WSL2。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md))
- **Node.js / npm**：`Node.js >=18.18`，`npm >=9`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md), [GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/package.json))
- **Python**：Python `>=3.11`。如果你已经激活 conda 且版本满足，`ds` 会优先用它；否则用 `uv` 在 DeepScientist home 下自举受管 Python。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md), [GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/pyproject.toml))
- **uv**：它被用于管理锁定的本地 Python runtime；缺失时，首次 `ds` 启动会自动补本地副本。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/09_DOCTOR.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/install.sh))
- **git**：必须安装，而且最好先配好 `git config user.name` 和 `git config user.email`，因为配置校验会检查这些。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/09_DOCTOR.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))
- **至少一个 runner CLI**：`codex`、`claude`、`kimi`、`opencode` 四选一。没有 runner，DeepScientist 只是空壳。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md))

### Python runtime 依赖

仓库 `pyproject.toml` 里当前列出的核心 Python 依赖是：`cryptography`、`httpx`、`lark-oapi`、`mcp`、`Pillow`、`PyYAML`、`rich`、`textual`、`websockets`。([GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/pyproject.toml))

### npm 包层依赖

当前 `package.json` 里最关键的 npm 依赖是：`@openai/codex`、`@anthropic-ai/claude-code`、`opencode-ai`，另外还有 TUI/UI 相关包 `ink`、`react`、`react-dom`、`qrcode` 等。注意这里**没有把 Kimi CLI 作为对等 npm 依赖列进去**，所以 Kimi 路线本质上更偏“外部 CLI 复用”。([GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/package.json), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/README.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/27_KIMI_CODE_PROVIDER_SETUP.md))

### 可选依赖

- **LaTeX / pdflatex / TinyTeX**：只在你要本地编译论文 PDF 时需要，不是核心启动依赖。`install.sh` 还提供 `--with-tinytex`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/install.sh), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/install.sh), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/09_DOCTOR.md))
- **源码开发时的 UI/TUI 依赖**：如果你是从 GitHub 源码开发 UI/TUI，而不是只运行发布包，还要额外执行：
  ```bash
  npm --prefix src/ui install
  npm --prefix src/tui install
  ```
  ([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/README.md))

## 4. 从 GitHub 源码端到端跑起来

如果你不是走 npm 全局安装，而是直接跑仓库源码，官方给的路径是：

```bash
git clone https://github.com/ResearAI/DeepScientist.git
cd DeepScientist
bash install.sh
ds
```

`install.sh` 默认装到 `~/DeepScientist/cli`，launcher wrapper 默认放在 `~/.local/bin`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/README.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/install.sh))

这里我给一个更实际的判断：**普通使用者走 npm 安装；要改源码再走 `git clone + bash install.sh`。** 因为公开 npm 包已经带预构建的 `src/ui/dist/` 和 `src/tui/dist/`，这是仓库级约束，不想让终端用户依赖 postinstall 自编译。([GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/package.json), [GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/AGENTS.md))

## 5. 你真正需要哪些 API

核心原则只有一句：**DeepScientist 不直接打模型服务；它通过 runner CLI 复用底层 provider/API。** 所以“需要哪些 API”要按 runner 看。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))

### A. `codex` 路线

这是默认推荐路线。它支持两大类方式：

- **OpenAI 正常登录流**：`codex login`，然后 `ds doctor`、`ds`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/09_DOCTOR.md))
- **provider-backed profile**：在 `~/.codex/config.toml` 里配 provider/profile，再让 DeepScientist 复用。DeepScientist 还支持在 `runners.yaml` 里写 `profile`、`model`、`env`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))

仓库文档里明确写到的 Codex provider/API 例子有：

- **OpenAI**：标准 `codex login` 路线。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md))
- **Ollama**：要走最新 Codex 路线，**必须**先确认本地 `http://localhost:11434/v1/responses` 可用，不是只有 `/v1/chat/completions`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md))
- **Gemini**：有 OpenAI-compatible endpoint `https://generativelanguage.googleapis.com/v1beta/openai/`，但仓库文档明确说 **Gemini 不推荐走 Codex + DeepScientist 默认路**，更推荐 OpenCode。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md))
- **MiniMax**：推荐官方 Coding Plan 路线，`Base URL = https://api.minimaxi.com/v1`，环境变量 `MINIMAX_API_KEY`，推荐模型 `MiniMax-M2.5`；`MiniMax-M2.7` 文档明确说当前官方 Codex 兼容路径不够稳。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md))
- **Alibaba Bailian / Qwen**：只支持 **Bailian Coding Plan endpoint**，不是通用 Bailian/DashScope Qwen API；文档给的 Base URL 是 `https://coding.dashscope.aliyuncs.com/v1`，key 形态通常是 `sk-sp-...`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md))

### B. `claude` 路线

DeepScientist 复用本机已可用的 `claude` CLI，以 headless 模式运行，并注入 `memory`、`artifact`、`bash_exec` 三个 MCP server。它要求你先把 Claude Code 自己跑通。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/24_CLAUDE_CODE_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/24_CLAUDE_CODE_PROVIDER_SETUP.md))

这一条路你实际会涉及的 API / 环境变量主要是：

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_BASE_URL`

仓库还做了一个兼容层：当 `ANTHROPIC_API_KEY` 为空时，会把 `ANTHROPIC_AUTH_TOKEN` 镜像成 `ANTHROPIC_API_KEY`。所以 Claude 也能挂到兼容网关，甚至挂到本地 Ollama。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/24_CLAUDE_CODE_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/24_CLAUDE_CODE_PROVIDER_SETUP.md))

### C. `kimi` 路线

Kimi 路线不是让你在 DeepScientist 里手工填一堆 API key。当前文档要求的是：先装官方 `kimi` CLI，先做 `kimi login`，确认 `kimi --version` 和最小 prompt 都正常，然后再 `ds doctor --runner kimi`。DeepScientist 复用的是 `~/.kimi` 下的登录态和配置。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/27_KIMI_CODE_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/27_KIMI_CODE_PROVIDER_SETUP.md))

所以，**Kimi 这条线的关键依赖是 CLI 登录态，不是 DeepScientist 自己的 API 配置面板。** ([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/27_KIMI_CODE_PROVIDER_SETUP.md))

### D. `opencode` 路线

OpenCode 是当前文档里**最灵活**的一条 provider 路线。DeepScientist 会运行 `opencode run --format json --pure ...`，并把 `memory`、`artifact`、`bash_exec` 作为 quest-local MCP server 注入进去。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/25_OPENCODE_PROVIDER_SETUP.md))

文档里写得最明确的 OpenCode provider/API 例子是：

- **Gemini**：`GEMINI_API_KEY`，Base URL 是 `https://generativelanguage.googleapis.com/v1beta/openai/`。而且文档明确说：**Gemini 推荐走 OpenCode，而不是 Codex。** ([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/25_OPENCODE_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/25_OPENCODE_PROVIDER_SETUP.md))
- **Ollama**：可以直接走 `ollama/<model>`，也可以把它当成 `http://localhost:11434/v1` 的 OpenAI-compatible endpoint 自定义 provider。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/25_OPENCODE_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md))
- **其他 provider**：OpenCode 文档面向 `provider/model-id` 命名和自定义 provider 系统，不是仓库硬编码死名单。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/25_OPENCODE_PROVIDER_SETUP.md))

### E. 本地推理后端

如果你想让 DeepScientist 跑本地模型，仓库的立场很清楚：

- **vLLM**：推荐。前提是 `/v1/models` 和 `/v1/responses` 都能用。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md))
- **Ollama**：可用，但要区分 runner；对最新 Codex 而言，必须先验证 `/v1/responses`。对 OpenCode/Claude 则更宽松。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md))
- **SGLang**：如果只有 `/v1/chat/completions`、没有可靠的 `/v1/responses`，那就**不兼容最新 Codex runner**。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md))

## 6. 需要哪些外部 agent

### 必需的“外部 agent / 执行器”

真正必须的只有一个层面：**外部 runner CLI**。四选一：

- `codex`
- `claude`
- `kimi`
- `opencode` ([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/00_QUICK_START.md))

而且它们都不是“DeepScientist 内部自己实现的模型调用器”，而是 **DeepScientist 去调用这些 CLI**。这点很关键。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))

### 不必装的东西

- **外部 MCP server**：不是必须。内建 MCP 就三个：`memory`、`artifact`、`bash_exec`。额外 MCP server 走 `mcp_servers.yaml`，属于可选扩展。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))
- **外部 connector sidecar**：大多数 connector 文档都在强调“推荐路径不需要公网回调，不需要额外 bridge/plugin”。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/10_WEIXIN_CONNECTOR_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/03_QQ_CONNECTOR_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/18_FEISHU_CONNECTOR_GUIDE.md))

### 可选的外部 connector / channel

这些都不是“核心端到端跑通”的必须项，但如果你要从聊天平台继续任务，就要配：

- **Weixin**：仓库内置 Weixin iLink runtime；不需要 OpenClaw、不需要 `npx`、不需要额外本地桥。扫码绑定即可。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/10_WEIXIN_CONNECTOR_GUIDE.md))
- **QQ**：官方 QQ Gateway direct，**不需要公网 callback**；要 `app_id + app_secret`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/03_QQ_CONNECTOR_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))
- **Telegram**：推荐 polling 路径；核心凭证是 BotFather token。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md))
- **Feishu/Lark**：推荐 long-connection；核心凭证是 `app_id + app_secret`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/18_FEISHU_CONNECTOR_GUIDE.md))
- **WhatsApp**：推荐 `local_session`，不是 webhook-first；本地 session runtime 负责收发。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))
- **Lingzhu / Rokid**：DeepScientist 自己在 daemon/web 端口上提供 `GET /metis/agent/api/health` 和 `POST /metis/agent/api/sse`，真机绑定要求可被外部设备访问的公网地址。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/04_LINGZHU_CONNECTOR_GUIDE.md))

## 7. 一个更本质的判断

从当前开源仓库的实现看，**DeepScientist 的核心不是“多外部 agent 协作”**，而是 **一个长期运行的本地研究 runtime**。内部更像“阶段技能 + 文件/Git 持久化 + runner 复用”，而不是 AutoGen/crew 那种强编排多 agent。仓库里定义的 canonical stage anchors 也只是 `scout`、`baseline`、`idea`、`experiment`、`analysis-campaign`、`write`、`finalize`，`decision` 还是跨阶段 skill，不是另一个必须安装的 agent。([GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/AGENTS.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/zh/06_RUNTIME_AND_CANVAS.md?utm_source=chatgpt.com))

所以你可以把它理解为：

**DeepScientist = 一个研究工作区操作系统。\
模型能力来自 runner。\
消息渠道来自 connector。\
工具扩展来自 MCP。\
不是“主框架自己包办一切”。** ([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/90_ARCHITECTURE.md?utm_source=chatgpt.com), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/01_SETTINGS_REFERENCE.md))

## 8. 我给你的最终建议

最稳的落地组合只有两套：

- **想最快跑通**：`npm install -g @researai/deepscientist` + `codex login` + `ds doctor` + `ds --here`。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/README.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/09_DOCTOR.md))
- **想接 Gemini 或更灵活的 provider**：`opencode` 路线，不要硬把 Gemini 塞进 Codex 默认路径。([GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/25_OPENCODE_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/15_CODEX_PROVIDER_SETUP.md), [GitHub](https://github.com/ResearAI/DeepScientist/blob/main/docs/en/25_OPENCODE_PROVIDER_SETUP.md))

再给你一个很实际的提醒：仓库现在存在**版本字符串不完全同步**的问题，`package.json` 是 `1.6.0`，但 `pyproject.toml` 还是 `1.5.17`。这说明 npm 分发层和 Python core 层至少在版本标记上有过不同步。你做复现时最好**固定 commit**，不要只信 README 里的版本号。([GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/pyproject.toml), [GitHub](https://raw.githubusercontent.com/ResearAI/DeepScientist/main/package.json))

如果你要，我下一条可以直接给你一份 **“按 Codex / Claude / Kimi / OpenCode 四条路线分别写的可执行安装清单”**，每条路线我会写到命令级。

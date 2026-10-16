# Dr. Claw 端到端配置

#### You:
你现在要做的就是在 Git Hub 上为我搜集一下，是如何使dr-claw这个框架端到端地运行起来，端到端的运行所需要的依赖是什么，所需要哪些 API，需要哪些外部的agent，你针对这个框架都给我列出来。

#### ChatGPT:
我先确认仓库本体、官方文档和源码入口。然后我会把“能跑起来”拆成四块：依赖、环境变量/API、外部 agent、端到端启动流程。


#### ChatGPT:
目前能确认三件事：它不是“纯网页项目”，而是一个前端 + Node 后端 + 本地 CLI agent 编排器；真正执行任务的是外部 agent，不是它自己内置大模型；最少要装 1 个执行后端，官方点名 Claude Code / Gemini CLI / Codex，OpenRouter 走 API 不走本地 CLI。([github.com](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [github.com](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [github.com](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))


#### ChatGPT:
我先给结论。

**Dr. Claw 想真正“端到端跑起来”，核心不是把前端点亮，而是把 4 个环节串通：**

1. Dr. Claw 本体启动起来。
2. 至少接上 **1 个可执行 agent 后端**。
3. 在项目里生成 `.pipeline/docs/research_brief.json` 和 `.pipeline/tasks/tasks.json`。
4. 让选定 agent 去执行这些任务，手动逐个执行，或用 Auto Research 顺序跑完整条流水线。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

## 一、最小可运行闭环

**最小闭环**是这样的：

```bash
git clone https://github.com/OpenLAIR/dr-claw.git
cd dr-claw
npm install
cp .env.example .env
npm run dev
```

然后你还要 **额外装一个执行后端**：`Claude Code CLI`、`Gemini CLI`、`Codex CLI` 三选一；或者走 `OpenRouter`。仅把 Dr. Claw 启动起来，不装这些后端，研究任务不会真正执行。官方的使用流也明确写了：先配置 agent，再在 Chat 里生成 research brief 和 tasks，再在 Research Lab 里选 backend 执行，或者点 Auto Research 连续执行。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

**我建议直接用 Node 22。** 官方先决条件写的是 Node 20+，推荐 v22 LTS；FAQ 还点名说 Node 25 容易把 `better-sqlite3` 编译打爆。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/docs/faq.md))

## 二、你真正需要的依赖

### 1）系统级依赖

必须有这些：

- **Node.js**：官方要求 `20.x || 22.x || 24.x`，README 推荐 Node 22 LTS。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/package.json), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **npm**：因为官方安装方式就是 `npm install` / `npx dr-claw`。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **原生构建工具链**：因为依赖里有 `node-pty`、`better-sqlite3` 这类 native 模块；README 和 FAQ 都明确提示某些系统上需要本地编译工具。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/docs/faq.md))

### 2）Node 侧依赖

仓库 `package.json` 里，运行 Dr. Claw 的关键依赖可以分成 5 组：

- **Agent / LLM 接入**：`@anthropic-ai/claude-agent-sdk`、`@openai/codex`、`@openai/codex-sdk`、`@modelcontextprotocol/sdk`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/package.json))
- **后端服务**：`express`、`ws`、`cors`、`node-fetch`、`multer`、`mime-types`、`chokidar`、`cross-spawn`、`glob`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/package.json))
- **本地终端 / 数据库**：`node-pty`、`better-sqlite3`、`sqlite`、`sqlite3`、`bcryptjs`、`jsonwebtoken`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/package.json))
- **前端 UI / 编辑器 / 终端**：`react`、`react-dom`、`react-router-dom`、CodeMirror 一组包、`@xterm/xterm` 和 xterm addons。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/package.json))
- **Markdown / LaTeX / 图表渲染**：`react-markdown`、`rehype-katex`、`remark-math`、`remark-gfm`、`mermaid`、`katex`、`react-syntax-highlighter`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/package.json))

开发态还要用到 `vite`、`typescript`、`electron`、`tailwindcss`、`concurrently`、`vitest` 等 devDependencies。因为 `npm run dev` 本身就依赖 `concurrently` 和 `vite`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/package.json), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/package.json))

### 3）Python 侧依赖

这部分**不是 Web UI 本体必需**。它只在你要接 **OpenClaw / drclaw CLI 控制面** 时需要。

`agent-harness/setup.py` 写得很清楚：

- Python `>=3.8`
- `click>=8.0`
- `requests>=2.28`
- `websockets>=11.0`

安装方式是：

```bash
pip install -e ./agent-harness
```

这会装出 `drclaw` / `dr-claw` / `vibelab` 这些 CLI 入口。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/agent-harness/setup.py), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

## 三、你需要哪些 API / 密钥

我按“必需”和“可选”分开说。

### A. 真正必需的

**你至少要有一种模型执行身份。**

四种主路径里，凭证要求分别是：

- **Claude Code CLI**：先全局安装，再跑 `claude`，按 OAuth 登录。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **Gemini CLI**：先全局安装；可走 Google 登录，也可设 `GOOGLE_API_KEY`。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **Codex CLI**：先全局安装；可 `codex login`，也可设 `OPENAI_API_KEY`。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/.env.example))
- **OpenRouter**：不需要本地 CLI，但必须有 `OPENROUTER_API_KEY`，可选 `OPENROUTER_MODEL`。源码里 `queryOpenRouter()` 直接检查 `OPENROUTER_API_KEY`，没有就报错。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/openrouter.js))

### B. 可选但常见的

- **Resend API Key**：用于 Auto Research 完成后的邮件通知。文档把它放进 Auto Research 的操作步骤里，但另一个段落又说这是“email notifications”。本质上它是通知链路，不是 agent 执行链路本身。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **Feishu / Lark channel**：只在你要用 OpenClaw watcher 做推送时才需要，比如 `--push-channel feishu:<chat_id>`。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **ARIS 的 API Key**：如果你在 Auto Research Hub 里选 ARIS，官方说明要求配置 `MCP Reviewer`，并输入对应 API key。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **Ollama 本地地址**：如果你要用源码里那个 `local-gpu` provider，默认打的是 `http://localhost:11434`，而且代码限制只能走 loopback 地址。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/local-gpu.js), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/local-gpu.js))
- **Nano Claude Code 相关变量**：如果你要启用源码里隐藏的 nano provider，要有 `nano-claude-code` CLI，并可配 `NANO_CLAUDE_CODE_COMMAND`、`NANO_CLAUDE_CODE_MODEL`、`NANO_CLAUDE_CODE_STREAMING`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/.env.example), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/nano-claude-code.js))

## 四、你需要哪些外部 agent

### 1）当前官方稳定执行后端

这是你现在应该优先考虑的：

- **Claude Code CLI**
- **Gemini CLI**
- **Codex CLI**
- **OpenRouter provider**

README 的“执行后端选择器”和架构说明都把这四个写成当前主线。Auto Research v1 也明确支持这四类执行引擎。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

### 2）OpenClaw：不是必须，但它是外部编排层

如果你要的是 **mobile / voice / secretary layer** 那条链路，就还要接 **OpenClaw**。README 把它定义成三层集成：

- OpenClaw 本地执行 `drclaw --json ...`
- `openclaw.*` 结构化 schema 作为协议
- watcher 把重要变化推到 Feishu / Lark

但这条链路是 **增强集成**，不是 Web UI 自身运行的前提。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/agent-harness/cli_anything/drclaw/SCHEMA.md))

### 3）Auto Research Hub 里的第三方工具包

如果你想让 Dr. Claw 跑“更完整的研究代理工作流”，那还可以装这些 pack：

- **ARIS**：端到端 autonomous pipeline，带跨模型 adversarial review；**需要 MCP Reviewer**。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **Autoresearch**：目标驱动迭代引擎，**零依赖**。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- **DeepScientist**：13-stage research OS，**零依赖**。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

这三者都属于 **可选的外部 workflow agent / tool pack**。不是 Dr. Claw 基础启动的前提。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

### 4）代码里存在、但我不建议你当主线的 provider

源码还接了这些：

- **Cursor**
- **local-gpu / Ollama**
- **nano-claude-code**

但这里要注意一个关键判断：

- `server/index.js` 确实已经 import 了 `spawnCursor`、`queryLocalGPU`、`spawnNanoClaudeCode`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/index.js))
- `.env.example` 也确实给了 `CURSOR_CLI_PATH`、`NANO_CLAUDE_CODE_*`。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/.env.example))
- **可 README 仍然明确写着 “Cursor agent support is in progress / coming soon”。**([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

所以我的判断很明确：\
**当前稳定 E2E 路线不要选 Cursor。** 它更像“代码已埋点、文档未放行”的状态。`local-gpu` 和 `nano-claude-code` 也是偏源码能力，不是当前 README 主推路径。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/index.js), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/nano-claude-code.js), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/local-gpu.js), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

## 五、端到端运行的实际流程

你真要把它跑通，按这个顺序最稳：

1. **Node 22 + npm install**。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/docs/faq.md))
2. **复制 `.env.example` 为 `.env`**。默认端口相关配置包括后端 `3001`、前端 dev `5173`，CLI 路径也在这里配。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/.env.example), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/docs/configuration.md))
3. **安装并登录一个执行后端**：Claude / Gemini / Codex / OpenRouter 四选一。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
4. **启动 Dr. Claw**：源码模式 `npm run dev`；`package.json` 里这会同时起 server 和 Vite client。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/package.json), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
5. **创建或打开项目**。Dr. Claw 会自动建立工作区目录、`.claude/`、`.agents/`、`.gemini/`、研究阶段目录和 `instance.json`。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
6. **在 Chat 里描述研究问题**，让 `inno-pipeline-planner` 生成 `research_brief.json` 和 `tasks.json`。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
7. **去 Research Lab 执行任务**：选 backend，然后让 agent 执行。手动逐任务也行，点 Auto Research 连续跑也行。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
8. **如果要自动跑网页搜索 / 工具调用**，还得把 provider 的权限开对：Claude 要 `WebSearch` / `WebFetch`，Gemini 要 `google_web_search` / `web_fetch`，Codex 要 `Bypass Permissions`，且别把 `CODEX_SANDBOX_NETWORK_DISABLED=1` 留着。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/docs/faq.md))

## 六、最实用的清单

### 必需

- Node 22
- npm install
- 一个执行 agent：Claude Code / Gemini CLI / Codex CLI / OpenRouter
- `.env`
- 项目目录
- 权限配置正确的 shell / web tools 能力([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

### 仅在这些场景下才需要

- Python + `agent-harness`：只在接 OpenClaw 时需要。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/agent-harness/setup.py))
- Resend API：只在邮件通知链路里需要。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- Feishu / Lark：只在 watcher 推送里需要。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- MCP Reviewer + API key：只在 ARIS pack 里需要。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))
- Ollama：只在 local-gpu provider 里需要。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/local-gpu.js), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/local-gpu.js))
- nano-claude-code：只在 nano provider 里需要。([GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/.env.example), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/nano-claude-code.js))

## 七、我对这个项目当前状态的判断

**它现在最稳的主线是：Dr. Claw UI + Claude/Gemini/Codex/OpenRouter 其中一个执行后端。**\
**OpenClaw、ARIS、Autoresearch、DeepScientist、Feishu/Lark、Resend 都是增强层，不是基础必需。**\
**Cursor 不该算进当前稳定 E2E 路线。** 源码有钩子，文档没放行。([GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md), [GitHub](https://raw.githubusercontent.com/OpenLAIR/dr-claw/main/server/index.js), [GitHub](https://github.com/OpenLAIR/dr-claw/blob/main/README.md))

如果你要，我下一条可以直接给你一份 **“从零到跑通 dr-claw 的最短命令清单”**，按 Linux/macOS 写成可直接执行的版本。

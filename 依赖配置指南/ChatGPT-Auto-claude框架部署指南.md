# Auto-claude框架部署指南

#### You:
你现在要做的就是在 Git Hub 上为我搜集一下，是如何使Auto-claude-code-research-in-sleep这个框架端到端地运行起来，端到端的运行所需要的依赖是什么，所需要哪些 API，需要哪些外部的agent，你针对这个框架都给我列出来。

#### ChatGPT:
我先直接查仓库和文档，再下沉到代码层面核对启动链路、环境变量、API 调用点和外部依赖。重点不是复述 README，而是把“端到端跑通最小闭环”拆清楚。


#### ChatGPT:
我已经确认一件关键事：它不是传统“Python 框架”。本体是 **Markdown skills + MCP 桥接 + 外部模型协作**。所以真正要搞清楚的不是 `pip install`，而是“谁执行、谁审稿、桥接怎么接、各阶段依赖什么”。


#### ChatGPT:
现在可以下结论了：默认主线并不复杂，真正复杂的是“替代组合”和“可选扩展”。默认跑通只要两件核心外部能力：**执行器** 和 **审稿器**。前者默认是 Claude Code，后者默认是 Codex MCP。其余基本都是可选增强。


#### ChatGPT:
我先给结论。

**ARIS 不是一个“装完 pip 就跑”的 Python 框架。**\
它本质上是一个 **Markdown skill 编排层**：执行端负责写代码、跑实验、写论文；审稿端负责跨模型批判、打分、逼你补实验。仓库宣传里写了“zero dependencies”，但那句话只对“skill 文件本体”成立；你真要把 **`/research-pipeline` 从 idea 跑到 paper PDF**，至少还要有执行器、审稿器、MCP 桥接，以及论文编译或实验后端。([GitHub](https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/README.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/AGENT_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

### 一、默认主线怎么端到端跑起来

仓库当前默认主线是：

1. **执行器**：Claude Code。
2. **审稿器**：Codex MCP。
3. **安装 skill**：把仓库 `skills/*` 装到 Claude Code 能发现的位置。
4. **跑工作流**：`/idea-discovery` → `/experiment-bridge` → `/auto-review-loop` → `/paper-writing`，或者直接 `/research-pipeline` 一把串起来。
5. **如果要自动跑实验**：在项目的 `CLAUDE.md` 里写好 GPU 环境。
6. **如果要出论文 PDF**：本地必须有 `latexmk` 和 `pdfinfo`。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/AGENT_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

最简单的全局装法，仓库 README 给的是：

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
mkdir -p ~/.claude/skills/
cp -r Auto-claude-code-research-in-sleep/skills/* ~/.claude/skills/

npm install -g @openai/codex
codex setup
claude mcp add codex -s user -- codex mcp-server

claude
# 然后在 Claude Code 里：
/research-pipeline "your research direction"
```

但仓库现在**更推荐**的是 **project-local flat symlink install**，也就是在每个项目里用 `tools/install_aris.sh` 把 skill 以扁平 symlink 方式挂到 `.claude/skills/<skill-name>`。这个方式更稳，也更符合 Claude Code 的 slash-command 发现机制。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

### 二、默认端到端运行的“硬依赖”

按默认方案，不绕弯，真正必需的是这几项：

**1）Claude Code**\
README 把它定义成 execution backbone。没有它，默认主线不存在。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**2）Codex CLI + MCP 注册**\
默认 review-heavy skills 依赖 Codex MCP；`research-review`、`auto-review-loop` 之类的 skill 明确要求 `mcp__codex__codex` / `mcp__codex__codex-reply`。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/skills/research-review/SKILL.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/auto-review-loop/SKILL.md))

**3）OpenAI 侧 reviewer 能力**\
默认组合表里写得很清楚：默认 executor/reviewer 组合需要 Claude API 和 OpenAI API。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**4）LaTeX 编译环境**\
只有当你要跑 Workflow 3，也就是 `paper-writing` / `paper-compile` 出 PDF 时才必需。README 明确要求 `latexmk` 和 `pdfinfo`；只跑 Workflow 1 和 2 可以不装。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**5）GPU 后端（仅实验阶段需要）**\
如果你只想做文献、idea、review、paper polish，不需要 GPU。\
如果你要让 `/experiment-bridge` 和 `/auto-review-loop` 自动补实验，就要给它一个实验后端：本地 GPU、SSH 远端 GPU、Vast.ai，或者 Modal。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/serverless-modal/SKILL.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/vast-gpu/SKILL.md))

### 三、一个很关键的坑：文档里有版本漂移

仓库很多文字还在说 reviewer 是 **GPT-5.4**，但当前 Quick Start 已经要求 `codex setup` 时选 **gpt-5.5**，而且多个核心 skill 的 `REVIEWER_MODEL` 也已经改成了 **`gpt-5.5`**。\
所以你真要按今天的仓库跑，**以最新 skill 文件和 Quick Start 为准，不要再按旧文案死配 5.4**。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/auto-review-loop/SKILL.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-review/SKILL.md?utm_source=chatgpt.com))

### 四、默认方案下需要哪些 API

默认主线需要两类 API：

**执行器 API**\
Claude Code 侧。默认是 Anthropic/Claude 这一路。替代时也可以换成 Anthropic-compatible 端点，比如 Z.ai(GLM)、Kimi、LongCat、MiniMax Anthropic endpoint、阿里百炼 Coding Plan、ModelScope 等。仓库把这类执行器配置统一放在 `ANTHROPIC_*` 环境变量上。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/LLM_API_MIX_MATCH_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**审稿器 API**\
默认是 Codex MCP，也就是 OpenAI 这一路。替代时可以换成 generic `llm-chat` MCP，对接任意 OpenAI-compatible reviewer API；如果 reviewer 供应商不支持 OpenAI 的 Responses API，就不能直接走 Codex MCP。这个正是 MiniMax 和很多第三方 reviewer 需要单独 bridge 的原因。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/LLM_API_MIX_MATCH_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/MINIMAX_MCP_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/LLM_API_MIX_MATCH_GUIDE.md))

### 五、除了主线 API，哪些外部接口是“可选但常见”的

这些都不是默认硬依赖，但很多 workflow 会吃到：

**文献检索相关**

- **arXiv API**：`/research-lit` 默认就会查，**不用额外配置**。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))
- **DBLP / CrossRef**：`/paper-write` 做真实 BibTeX 获取时默认开启。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))
- **Semantic Scholar API**：只有你显式把 `semantic-scholar` 放进 `sources` 才会用；不带 key 也能跑，但仓库建议配 `SEMANTIC_SCHOLAR_API_KEY` 提高限额。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/semantic-scholar/SKILL.md?utm_source=chatgpt.com))
- **DeepXiv**：可选，需 `pip install deepxiv-sdk`。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))
- **Exa**：可选，需 `pip install exa-py` 和 `EXA_API_KEY`。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/exa-search/SKILL.md?utm_source=chatgpt.com))
- **Zotero**：可选，`uv tool install zotero-mcp-server` 或 `pip install zotero-mcp-server`，本地桌面版或 Web API 都行。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))
- **Obsidian**：可选，推荐 `mcpvault`。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**实验后端相关**

- **远端 GPU 服务器**：在 `CLAUDE.md` 里写 SSH、conda env、代码目录、screen 运行方式。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/ANTIGRAVITY_ADAPTATION.md?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-pipeline/SKILL.md?utm_source=chatgpt.com))
- **Vast.ai**：可选，需 `vastai` CLI、Python ≥ 3.10、Vast API key、提前上传 SSH 公钥。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/vast-gpu/SKILL.md))
- **Modal**：可选，需 `pip install modal` + `modal setup`。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/serverless-modal/SKILL.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/serverless-modal/SKILL.md))
- **W\&B**：可选，`WANDB=false` 默认关闭；开了以后要在 `CLAUDE.md` 里写 `wandb_project`。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**协作/通知相关**

- **Feishu/Lark webhook**：可选，用于推送或交互式通知。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))
- **Overleaf Git bridge**：可选，做本地 paper 目录与 Overleaf 的双向同步。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

### 六、你问的“外部 agent”到底有哪些

这里我给你拆成两层。

#### 1）真正的执行 / 审稿 agent

这是 ARIS 的核心。

- **默认执行 agent**：Claude Code。([GitHub](https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/README.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))
- **默认审稿 agent**：Codex MCP 背后的 OpenAI reviewer。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/skills/research-review/SKILL.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/auto-review-loop/SKILL.md))
- **可替代执行 agent**：Codex CLI、OpenClaw、Cursor、Trae、Antigravity。仓库明确说这些都能跑同一套 workflow，只是适配方式不同。([GitHub](https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/README.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))
- **可替代审稿 agent**：Oracle 上的 GPT-5.4 Pro、Claude Code CLI reviewer、Gemini reviewer、generic OpenAI-compatible reviewer、MiniMax reviewer。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/reviewer-routing.md?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/CODEX_CLAUDE_REVIEW_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/LLM_API_MIX_MATCH_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/MINIMAX_MCP_GUIDE.md))

#### 2）桥接这些 agent 的外部 MCP / bridge

这些不是“研究 agent”，但它们是你跑通链路的关键中间层。

- **`codex` MCP**：默认 reviewer transport。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/skills/research-review/SKILL.md))
- **`llm-chat` MCP**：通用 reviewer transport，适合 DeepSeek / GLM / MiniMax / Kimi 等 OpenAI-compatible reviewer。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/LLM_API_MIX_MATCH_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/LLM_API_MIX_MATCH_GUIDE.md))
- **`minimax-chat` MCP**：因为 MiniMax 不支持 Responses API，所以要单独 bridge。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/MINIMAX_MCP_GUIDE.md))
- **`claude-review` MCP**：Codex 做执行器、Claude Code CLI 做 reviewer 时用。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/CODEX_CLAUDE_REVIEW_GUIDE.md))
- **`gemini-review` MCP**：Codex 做执行器、Gemini 做 reviewer 时用。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md?utm_source=chatgpt.com))
- **`oracle` MCP**：显式传 `- reviewer: oracle-pro` 时走它。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/reviewer-routing.md?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/reviewer-routing.md))

### 七、如果你只想“最快跑通”，我给你明确判断

**最快、最稳、文档最完整的路径：**\
**Claude Code + Codex MCP + 本地或 SSH GPU + LaTeX**。这是仓库主线。别一开始就上 MiniMax/DeepSeek/ModelScope 混搭。混搭方案都能跑，但要额外处理 MCP、自定义 env、甚至批量改写那 12 个 reviewer skill。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/LLM_API_MIX_MATCH_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/MINIMAX_MCP_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/MODELSCOPE_GUIDE.md?utm_source=chatgpt.com))

**最低成本路径：**\
**ModelScope** 或 **llm-chat 混搭**。优点是便宜，甚至免费；缺点是要装 Python 依赖、配置自定义 reviewer bridge，并且把依赖 Codex MCP 的 12 个 skill 改写到本地副本。([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/MODELSCOPE_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/MODELSCOPE_GUIDE.md?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/CURSOR_ADAPTATION.md?utm_source=chatgpt.com))

### 八、我替你压成一份“总清单”

**默认必需**

- Claude Code
- Codex CLI
- ARIS `skills/*`
- Claude API
- OpenAI reviewer API
- Git / npm
- LaTeX + `latexmk` + `pdfinfo`（仅出 PDF 时）
- GPU 后端（仅自动实验时）([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**默认可选**

- Zotero / Obsidian
- DeepXiv / Exa / Semantic Scholar key
- Vast.ai / Modal
- W\&B
- Feishu / Lark
- Overleaf Git bridge
- Research Wiki / Meta logging([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/serverless-modal/SKILL.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/vast-gpu/SKILL.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep))

**外部 reviewer/agent 备选**

- Oracle MCP
- llm-chat MCP
- minimax-chat MCP
- claude-review MCP
- gemini-review MCP([GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/reviewer-routing.md?utm_source=chatgpt.com), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/LLM_API_MIX_MATCH_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/MINIMAX_MCP_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/raw/refs/heads/main/docs/CODEX_CLAUDE_REVIEW_GUIDE.md), [GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/CODEX_GEMINI_REVIEW_GUIDE_CN.md?utm_source=chatgpt.com))

如果你要，我下一条可以直接给你一份 **“Linux/macOS 上按默认主线一条条执行的安装脚本”**，或者我也可以直接给你整理成 **“默认方案 / 低成本方案 / 无 OpenAI 方案” 三套落地配置单**。

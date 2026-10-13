结论：**不要给 7 个项目各写一套完全不同的 Dockerfile。最省事、最稳的做法是按项目形态复用少量基础镜像，再为需要双层执行环境的项目记录清楚主控镜像与实验/执行镜像。**

当前 7 个项目为：AI-Researcher、AI-Scientist-v2、Auto-claude-code-research-in-sleep、AutoResearchClaw、DeepScientist、dr-claw、EvoScientist。

## 总体选择

| 项目                                            | 我建议的方案                                                           | 原因                                                                                                                                                                   |
| --------------------------------------------- | ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AI-Researcher**                              | 两层：主控用 Python 3.11 + uv + Playwright 镜像；实验/命令执行环境使用官方/项目 Docker 镜像 `tjbtech1/airesearcher:v1` 或从 `AI-Researcher/docker/Dockerfile` 构建 | 项目 README 明确要求宿主侧 `uv venv --python 3.11`、`uv pip install -e .`、`playwright install`，研究 agent 运行时还会使用 Docker 执行环境；仓库已提供 `.env.template`、`docker/Dockerfile`、`docker/requirements.txt`、`research_agent/` 和 `paper_agent/`。 |
| **EvoScientist**                              | 直接用官方镜像 `ghcr.io/evoscientist/evoscientist:latest`               | 官方已经提供 Dockerfile、docker-compose、GHCR 镜像，且内置 Python 3.11、Node 24、uv、MCP 运行依赖。最省事。([GitHub][1])                                                                       |
| **AutoResearchClaw**                          | 两层：主控用 Python 3.11 镜像；实验执行用它自带的 `researchclaw/experiment:latest` | 仓库自带 GPU 实验沙箱 Dockerfile，基于 `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04`，装了 PyTorch、Transformers、datasets、vision 常用包。([GitHub][2])                                   |
| **AI-Scientist-v2**                           | 自己写 CUDA + Python 3.11 + PyTorch 镜像                              | 官方 README 明确要求 Linux + NVIDIA GPU + CUDA + PyTorch，并建议放进 Docker 沙箱，但仓库没有成熟官方 Dockerfile。([GitHub][3])                                                                |
| **DeepScientist**                             | 用统一 Node 22 + Python 3.11 “agent-runtime” 镜像                     | 它本质是本地研究工作区 + runner wrapper。官方推荐 `npm install -g @researai/deepscientist`，并依赖 Codex / Claude / Kimi / OpenCode 这类 runner。([GitHub][4])                              |
| **dr-claw**                                   | 同样用 Node 22 + Python 3.11 “agent-runtime” 镜像                     | 它是 Node/React/Vite/Express/SQLite/agent CLI workspace。官方推荐 `npx dr-claw` 或 `npm install -g dr-claw`，Node 22 更稳，FAQ 也明确说 Node 25 会触发 native module 编译问题。([GitHub][5]) |
| **Auto-claude-code-research-in-sleep / ARIS** | 不单独做重镜像；作为 skills/CLI 放进 agent-runtime 镜像                        | 它自己宣称是 Markdown-only、zero dependencies、no Docker to configure，本质更像 skill pack / workflow，而不是完整 daemon。([GitHub][6])                                                  |

---

# 我建议你采用 3 类基础镜像，并为 AI-Researcher 单独记录主控镜像

## 1. `research-cuda-py311`

给 **AI-Scientist-v2** 和 **AutoResearchClaw 实验沙箱** 用。

```dockerfile
# Dockerfile.cuda-py311
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3.11-venv python3-pip \
    git curl ca-certificates \
    build-essential cmake make gfortran \
    libopenblas-dev liblapack-dev \
    poppler-utils chktex \
    texlive-latex-base texlive-latex-recommended texlive-fonts-recommended texlive-bibtex-extra \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && python3 -m pip install --upgrade pip setuptools wheel \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

WORKDIR /workspace
CMD ["/bin/bash"]
```

### 用法：AI-Scientist-v2

```bash
docker build -f Dockerfile.cuda-py311 -t research-cuda-py311:cu124 .

git clone https://github.com/SakanaAI/AI-Scientist-v2.git

docker run --rm -it --gpus all \
  --env-file .env \
  -v "$PWD/AI-Scientist-v2:/workspace" \
  -w /workspace \
  research-cuda-py311:cu124 \
  bash -lc "pip install -r requirements.txt && bash"
```

`.env` 至少放：

```bash
OPENAI_API_KEY=...
GEMINI_API_KEY=...
S2_API_KEY=...
# 如果走 Claude Bedrock：
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION_NAME=...
```

AI-Scientist-v2 的 README 明确提到 `OPENAI_API_KEY`、`GEMINI_API_KEY`、AWS Bedrock 凭据和 `S2_API_KEY`。([GitHub][3])

---

## 1.5. `ai-researcher-py311`

给 **AI-Researcher 主控进程** 用；它的真实代码/实验执行环境仍然应使用项目提供的 Docker 执行镜像。

建议主控镜像包含：

- Python 3.11
- uv
- Playwright 及浏览器依赖
- Docker CLI（如需从容器内调度宿主 Docker，需要挂载 Docker socket，并在报告中记录安全风险）
- LaTeX / poppler / chktex（paper agent 需要 PDF 或 TeX 编译时）

AI-Researcher 的执行镜像优先选择：

```bash
docker pull tjbtech1/airesearcher:v1
```

或从项目目录构建：

```bash
docker build -t tjbtech1/airesearcher:v1 AI-Researcher/docker
```

主控安装示例：

```bash
cd AI-Researcher
uv venv --python 3.11
uv pip install -e .
playwright install
```

最小运行前需要根据 `AI-Researcher/.env.template` 准备环境变量。至少应关注：`BASE_IMAGES`、`DOCKER_WORKPLACE_NAME`、`COMPLETION_MODEL`、`CHEEP_MODEL`、`OPENROUTER_API_KEY`、`GITHUB_AI_TOKEN`、`CATEGORY`、`INSTANCE_ID`、`TASK_LEVEL`、`MAX_ITER_TIMES`。API key 可以按用户要求写入本地 env 文件、Report 或 To-Do List，但不得写入 Dockerfile 或镜像层，也不得上传或外传。

---

## 2. `agent-runtime-node22`

给 **DeepScientist、dr-claw、ARIS** 共用。

```dockerfile
# Dockerfile.agent-runtime
FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    git curl ca-certificates bash openssh-client \
    build-essential make g++ python3-dev pkg-config \
    sqlite3 \
    poppler-utils chktex \
    texlive-latex-base texlive-latex-recommended texlive-fonts-recommended texlive-bibtex-extra \
    && npm install -g npm@latest \
    && npm install -g @openai/codex @anthropic-ai/claude-code opencode-ai \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash agent
USER agent
WORKDIR /workspace

ENV PATH="/home/agent/.local/bin:${PATH}"

CMD ["/bin/bash"]
```

构建：

```bash
docker build -f Dockerfile.agent-runtime -t agent-runtime-node22:latest .
```

### 用法：DeepScientist

```bash
docker run --rm -it \
  --env-file .env \
  -p 21888:21888 \
  -v "$PWD/workspace:/workspace" \
  -v deepscientist-home:/home/agent \
  agent-runtime-node22:latest \
  bash -lc "npm install -g @researai/deepscientist && ds --here"
```

DeepScientist 官方推荐先保证一个 runner 可用，最直接路线是 `npm install -g @researai/deepscientist`、`codex login`、`ds --here`；Claude、Kimi、OpenCode 也是 runner 选项。([GitHub][4])

### 用法：dr-claw

```bash
docker run --rm -it \
  --env-file .env \
  -p 3001:3001 \
  -v "$PWD/drclaw-workspaces:/home/agent/dr-claw" \
  -v drclaw-home:/home/agent \
  agent-runtime-node22:latest \
  bash -lc "npm install -g dr-claw && dr-claw"
```

dr-claw 官方推荐 `npx dr-claw` 或全局安装后运行，并默认打开 `http://localhost:3001`。 ([GitHub][5])

### 用法：ARIS

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD/workspace:/workspace" \
  -v aris-home:/home/agent \
  agent-runtime-node22:latest \
  bash -lc "git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git /opt/aris && bash"
```

ARIS 不适合重 Docker 化。它是 Markdown skills + workflow。真正需要容器的是它调用的执行环境，例如 Codex、Claude Code、Python 实验环境、LaTeX、GPU 实验环境。它自己不是服务端型程序。([GitHub][6])

---

## 3. EvoScientist 官方镜像

这个不要重写。直接用官方的。

```bash
docker run -it --rm \
  --env-file .env \
  -v "$(pwd)/workspace:/workspace" \
  -v evosci-data:/home/evosci/.evoscientist \
  ghcr.io/evoscientist/evoscientist:latest
```

官方 README 已说明这三个挂载的用途：`.env` 放 API key，`workspace` 是 agent 工作目录，`evosci-data` 保存 session、skills、memory、config、mcp 配置。([GitHub][7])

需要 LaTeX 或 oauth/stt 时，再派生：

```dockerfile
FROM ghcr.io/evoscientist/evoscientist:latest

USER root
RUN uv pip install --python /opt/venv/bin/python "EvoScientist[stt,oauth]"
USER evosci
```

---

# 最终推荐

我会这样落地：

```text
docker/
  Dockerfile.cuda-py311          # AI-Scientist-v2 + AutoResearchClaw 实验
  Dockerfile.ai-researcher       # AI-Researcher 主控：Python 3.11 + uv + Playwright + Docker CLI
  Dockerfile.agent-runtime       # DeepScientist + dr-claw + ARIS
  docker-compose.yml             # 统一启动
.env
workspace/
```

核心判断：

1. **EvoScientist：直接用官方镜像。**
2. **AutoResearchClaw：复用它官方 GPU experiment Dockerfile，不要自己重造实验镜像。**
3. **AI-Scientist-v2：用 CUDA 12.4 + PyTorch + Python 3.11 自建镜像。**
4. **AI-Researcher：主控用 Python 3.11 + uv + Playwright，执行环境用它官方/项目 Docker 镜像。**
5. **DeepScientist / dr-claw / ARIS：共用 Node 22 + Python 3.11 agent-runtime。**

最不推荐的方案是：给每个项目都写一个单独 Dockerfile。那会导致 API key、runner 登录态、workspace、LaTeX、GPU、Node native module 全部分散，后期维护很痛苦。

[1]: https://github.com/EvoScientist/EvoScientist?utm_source=chatgpt.com "Harness Vibe Research with Self-evolving AI Scientists · ..."
[2]: https://raw.githubusercontent.com/aiming-lab/AutoResearchClaw/main/researchclaw/docker/Dockerfile "raw.githubusercontent.com"
[3]: https://raw.githubusercontent.com/SakanaAI/AI-Scientist-v2/main/README.md "raw.githubusercontent.com"
[4]: https://github.com/ResearAI/DeepScientist "GitHub - ResearAI/DeepScientist: Now, Stronger AI Pushes Frontiers, Stronger Our Shared Future. · GitHub"
[5]: https://github.com/OpenLAIR/dr-claw "GitHub - OpenLAIR/dr-claw: A Super AI Lab with massive AI Doctors as Assistants. Best IDE for Research via AI Power. · GitHub"
[6]: https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/README.md "raw.githubusercontent.com"
[7]: https://github.com/EvoScientist/EvoScientist "GitHub - EvoScientist/EvoScientist:  Harness Vibe Research with Self-evolving AI Scientists · GitHub"

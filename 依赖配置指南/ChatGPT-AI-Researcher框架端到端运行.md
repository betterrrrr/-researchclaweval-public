# AI-Researcher框架端到端运行

#### You:
你现在要做的就是在 Git Hub 上为我搜集一下，是如何使AI-Researcher这个框架端到端地运行起来，端到端的运行所需要的依赖是什么，所需要哪些 API，需要哪些外部的agent，你针对这个框架都给我列出来。

#### ChatGPT:
我先定位你说的这个 “AI-Researcher” 到底指哪个 GitHub 项目，然后直接沿着 README、requirements、源码和配置文件，把端到端运行链路拆开。若 GitHub 上有多个同名项目，我会按星数、活跃度和“框架化程度”选最可能的那个，并把歧义点说清。


#### ChatGPT:
已经定位到两个同名仓库，但更像你要的，是 HKUDS 这个：它不是单纯“想点子”，而是完整的研究自动化框架，含 benchmark、research agent、web GUI、Docker 执行环境。下一步我直接看源码和配置，确认它真实依赖了哪些 API、工具和外部 agent，而不是只复述 README。


#### ChatGPT:
目前可以下一个明确判断：这个项目不是“单一 agent + 若干脚本”，而是一个多 agent 编排系统，研究实现和论文写作是两段链路。研究链路我已经确认了核心 agent 角色、Docker 执行环境、模型网关和代码/论文检索入口；接着我把论文生成这一段也补齐，避免把“端到端”误说成只到实验结束。


#### ChatGPT:
我按 **HKUDS/AI-Researcher** 这个仓库来回答。GitHub 上还有一个同名的 **NoviScl/AI-Researcher**，但那个更偏研究想法生成；HKUDS 这个仓库明确把自己定位成从 **concept 到 publication** 的自动科研框架，更符合你说的“端到端运行”。 ([GitHub](https://github.com/hkuds/ai-researcher?utm_source=chatgpt.com), [GitHub](https://github.com/NoviScl/AI-Researcher?utm_source=chatgpt.com), [GitHub](https://github.com/hkuds/ai-researcher))

先给结论。

这个项目不是“装几个包就跑”的轻量 agent。它的本质是：**宿主机 Python 负责编排，多 agent 负责决策，Docker 容器负责真实代码执行和训练，外部再接 LLM、GitHub 检索、arXiv 检索/源码下载，以及可选的 Web GUI。** 而且它的“端到端”其实分两段：**研究链路** 和 **论文生成链路**。论文不是自动顺手产出的，要再单独跑一段。 ([GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/run_infer_plan.py), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/research_agent/run_infer_idea.py), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/docker/tcp_server.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/main_ai_researcher.py), [GitHub](https://github.com/hkuds/ai-researcher))

## 一、怎么把它端到端跑起来

最稳的路线，不是 GUI，而是 **CLI 脚本 + Docker + 单独的 paper agent**。README 给出的基础安装是：Python 3.11，推荐 `uv`，然后 `uv venv --python 3.11`、`uv pip install -e .`，再执行 `playwright install`。之后还要准备 Docker 镜像。README 写的是拉取 `tjbtech1/airesearcher:v1` 或自己从 `docker/Dockerfile` 构建。`.env.template` 里还默认把平台写成了 `linux/amd64`。 ([GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/.env.template))

研究阶段有两条主线。仓库把它们分成 **Level 1** 和 **Level 2**。实际脚本文件是 `research_agent/run_infer_level_1.sh` 和 `research_agent/run_infer_level_2.sh`。前者最终调用 `run_infer_plan.py`，后者调用 `run_infer_idea.py`。主入口 `main_ai_researcher.py` 也印证了这一点：它把任务分成 **Detailed Idea Description**、**Reference-Based Ideation**、以及单独的 **Paper Generation Agent**。也就是说，研究和写作本来就是分开的两个任务入口。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_1.sh), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_2.sh), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/main_ai_researcher.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/main_ai_researcher.py))

真正跑起来时，研究脚本会先创建 **DockerEnv**，初始化容器，再建 **BrowserEnv** 和 **RequestsMarkdownBrowser**，然后把这些环境交给 `InnoFlow` 这套多 agent 流程去跑。底层容器侧还有一个 `tcp_server.py`，它会监听端口，然后直接在工作目录里执行 bash 命令，把输出再回传给上层 agent。说白了，这个框架不是“让模型嘴上做研究”，而是**真在容器里改代码、跑命令、跑训练、拿结果**。 ([GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/run_infer_plan.py), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/docker/tcp_server.py))

论文阶段是另一段。README 给了 `paper_agent/writing.py` 入口；代码里它会依次生成 methodology、related work、experiments、introduction、conclusion、abstract，最后清理 tex 并编译 PDF。这里还有一个隐藏要求：`paper_agent/tex_writer.py` 会直接调用 `pdflatex` 和 `bibtex`。所以 **LaTeX 工具链是隐式依赖**，README 没写清楚，但代码是实打实依赖的。 ([GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/writing.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/tex_writer.py))

## 二、端到端运行需要哪些依赖

### 1）宿主机 Python 依赖

这个项目的宿主机依赖很重，不是只有 `openai` 和 `requests`。`setup.cfg` 里能看到几大类核心包：\
**LLM/编排**：`openai>=1.52.0`、`litellm==1.55.0`、`instructor`、`tiktoken`、`tenacity`；\
**浏览器/网页处理**：`playwright==1.39.0`、`browsergym==0.13.0`、`beautifulsoup4`、`html2text`、`markdownify`；\
**文档/知识处理**：`docling`、`pdfminer.six`、`python_pptx`、`mammoth`、`puremagic`、`arxiv`；\
**数据/实验**：`numpy`、`pandas`、`matplotlib`、`datasets`、`networkx`、`sentence_transformers`；\
**音视频与转写**：`moviepy`、`faster_whisper`、`youtube_transcript_api`、`SpeechRecognition`、`pydub`；\
**服务/UI**：`Flask`、`uvicorn`、`gradio`。这说明它不是单任务科研脚本，而是把浏览、文档、多模态处理、UI 都揉进去了。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/setup.cfg), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/setup.cfg), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/setup.cfg), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/setup.cfg), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/setup.cfg), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/setup.cfg))

### 2）Docker 容器依赖

容器内还有另一套依赖。`docker/requirements.txt` 里有 `fastapi`、`uvicorn`、`pyautogui`、`pytesseract`、`Pillow`、`tensorboard`、`tokenizers`、`pycocotools` 等。Dockerfile 还装了大量系统包，比如 **Xvfb / x11vnc / tigervnc / supervisor**，以及 **poppler-utils、wkhtmltopdf、antiword、unrtf、catdoc、jq、csvkit、xmlstarlet**。这说明容器不是单纯 Python 运行时，而是一个**带 GUI/桌面、文档转换和命令行工具箱的执行环境**。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/docker/requirements.txt), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/docker/Dockerfile), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/docker/Dockerfile))

### 3）GPU 与平台

如果你真要按它的设计跑“端到端科研”，**GPU 基本是刚需**。虽然 `.env.template` 允许 `GPUS=None`，但 agent 的提示词明确要求在真实数据集上实现算法，并在 GPU 上训练，初次实现甚至写死了“先跑 2 epochs”这一类执行要求。再加上 `.env.template` 默认平台是 `linux/amd64`，所以最顺手的环境就是 **Ubuntu/Linux + Docker + NVIDIA**。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/.env.template), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/research_agent/run_infer_idea.py), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/research_agent/run_infer_idea.py), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/research_agent/run_infer_idea.py))

## 三、需要哪些 API

这里要分 **最小必需** 和 **GUI 扩展**。

### 1）最小必需 API：CLI 研究链路

按 `.env.template` 和 `research_agent/constant.py` 看，CLI 研究链路最核心的是：

- `OPENROUTER_API_KEY`
- 一个 OpenAI-compatible / LiteLLM 可调的模型配置，比如 `COMPLETION_MODEL`、`CHEEP_MODEL`、`EMBEDDING_MODEL`
- `GITHUB_AI_TOKEN` 这个变量也被读取了\
  默认模板里甚至直接把模型写成 `openrouter/google/gemini-2.5-pro-preview-05-20`，API Base 写成 `https://openrouter.ai/api/v1`。所以**最现实的最小配置，就是 OpenRouter key + 模型名 + 容器/工作目录参数**。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/.env.template), [GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/constant.py))

### 2）论文生成 API

README 在 paper agent 的示例里单独写了 `OPENAI_API_KEY`。这说明**论文生成链路默认按 OpenAI key 来走**，至少 README 是这样写的。也就是说，研究链路和写作链路的 API 配置并不完全统一。 ([GitHub](https://github.com/hkuds/ai-researcher))

### 3）GUI 路线额外 API

`web_ai_researcher.py` 里内置了一套更复杂的环境模板，里面除了 `OPENAI_API_KEY`，还包括 **Azure OpenAI** 配置、`QWEN_API_KEY`、`DEEPSEEK_API_KEY`、`GOOGLE_API_KEY`、`SEARCH_ENGINE_ID`、`CHUNKR_API_KEY`、`FIRECRAWL_API_KEY`。这说明 **GUI 路线把搜索、抓取、解析、多个模型供应商都预留进去了**。但这不代表你全都必须配；它更像一个“大而全”的 UI 配置面板。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/web_ai_researcher.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/web_ai_researcher.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/web_ai_researcher.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/web_ai_researcher.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/web_ai_researcher.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/web_ai_researcher.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/web_ai_researcher.py))

## 四、需要哪些外部 agent / 外部工具

这个项目我没有看到它强依赖 OpenHands、AutoGen 这类外部 agent 平台。它更像是**自己在仓库里定义了多 agent 角色**，外部接的是环境和检索工具。

研究链路里我确认到的 agent 角色有：

- `Prepare Agent`
- `Idea Agent`（主要在 level 2）
- `Code Survey Agent`
- `Survey Agent`
- `Coding Plan Agent`
- `Machine Learning Agent`
- `Judge Agent`
- `Exp Analyser Agent`。 ([GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/research_agent/run_infer_idea.py), [GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/run_infer_plan.py), [GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/run_infer_plan.py))

它调用的外部工具/环境有：

- `DockerEnv`：真实代码执行和训练环境
- `BrowserEnv`：浏览器交互环境
- `RequestsMarkdownBrowser`：网页内容抓取/转 markdown
- `search_github_repos`、`search_github_code`：GitHub 仓库和代码搜索
- `get_arxiv_paper_meta`、`download_arxiv_source_by_title`：arXiv 元数据和源码下载。 ([GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/research_agent/run_infer_idea.py), [GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/run_infer_plan.py))

论文链路则是另一组写作 agent/module。`paper_agent/writing.py` 负责拆分章节并串起来，`tex_writer.py` 负责 LaTeX 编译。换句话说，它不是一个单一 agent，而是**研究多 agent + 写作多模块**。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/writing.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/tex_writer.py))

## 五、这个项目现在的真实状态：能跑，但不够整齐

我直接说判断：**它有真实的端到端设计，也有真实的执行链路，但工程一致性一般，文档和代码有明显漂移。** 这不是“README 一把梭稳定复现”的项目。这个判断不是拍脑袋，是因为我看到几处很硬的冲突：

- README / `.env.template` 写的基础镜像是 `tjbtech1/airesearcher:v1`，但实际 level 1/2 脚本里分别写成了 `tjbtech1/metachain:amd64_latest` 和 `tjbtech1/paperagent:latest`；
- README 里提到 `paper_agent/run_infer.sh`，但仓库里实际是 `run_paper.sh`；
- Dockerfile 注释写“PyTorch 2.3.0 + CUDA 11.8”，实际安装命令却是 **torch 1.13.1 + cu116**；
- README 自己也承认文档 “on its way”，还没补齐。 ([GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/.env.template), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_1.sh), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_2.sh), [GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/HKUDS/AI-Researcher/tree/main/paper_agent), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/docker/Dockerfile))

所以我给你的实话是：**这个框架不是不能跑，而是你要按源码和脚本去跑，不能只信 README。** 尤其是镜像名、paper agent 入口、模型 key、以及 LaTeX 工具链，要自己核对。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_1.sh), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_2.sh), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/writing.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/tex_writer.py))

## 六、我给你的最小可跑清单

你如果要在 Ubuntu 上尽快跑通，最小闭环我会这样配：

1. **Python 3.11 + `uv`**。先 `uv venv --python 3.11`，再 `uv pip install -e .`。 ([GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/hkuds/ai-researcher))
2. **Playwright**。执行 `playwright install`。 ([GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/hkuds/ai-researcher))
3. **Docker + Linux/amd64 + NVIDIA GPU**。这是它默认假设的平台。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/.env.template), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/research_agent/run_infer_idea.py))
4. **研究链路 API**：先配 `OPENROUTER_API_KEY`，再配模型名；`GITHUB_AI_TOKEN` 也一起准备。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/.env.template), [GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/constant.py))
5. **按实际脚本核对镜像名**。不要盲信 README 里的单一镜像名。 ([GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_1.sh), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/research_agent/run_infer_level_2.sh))
6. **先跑 research\_agent**，再单独跑 `paper_agent/writing.py`。论文阶段另备 `OPENAI_API_KEY` 和 LaTeX。 ([GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/main_ai_researcher.py), [GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/tex_writer.py))

一句话总结：**AI-Researcher 是一个“多 agent + 容器执行 + 外部检索 + 论文生成”的重型科研自动化框架。能端到端，但门槛高，配置散，文档漂移明显。最稳的做法是按源码而不是按 README 跑。** ([GitHub](https://github.com/hkuds/ai-researcher), [GitHub](https://raw.githubusercontent.com/HKUDS/AI-Researcher/refs/heads/main/research_agent/run_infer_plan.py), [GitHub](https://github.com/HKUDS/AI-Researcher/raw/refs/heads/main/docker/tcp_server.py), [GitHub](https://github.com/HKUDS/AI-Researcher/blob/main/paper_agent/writing.py))

你要的话，我下一条直接给你一份 **面向 Ubuntu 的可执行部署清单**，我会按“安装顺序 + 命令 + `.env` 示例 + 容易踩坑点”写。

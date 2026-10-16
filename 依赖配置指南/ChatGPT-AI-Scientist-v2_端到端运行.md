# AI-Scientist-v2 端到端运行

#### You:
你现在要做的就是在 Git Hub 上为我搜集一下，是如何使AI-Scientist-v2这个框架端到端地运行起来，端到端的运行所需要的依赖是什么，所需要哪些 API，需要哪些外部的agent，你针对这个框架都给我列出来。

#### ChatGPT:
我先直接查仓库和官方文档，再顺着安装脚本、requirements、示例命令把整条运行链路拆出来。重点会放在四件事：端到端流程、依赖、API、外部 agent/服务。


#### ChatGPT:
目前能确认两点：\
1）它不是“一条命令直接全自动”的黑盒，标准链路是“先生成 idea，再跑 BFTS 实验，再写论文，再审稿”。\
2）默认配置是多模型混用，不是单一 API 就能跑通。README 和配置文件里已经把这一点写死了。


#### ChatGPT:
我已经把最关键的“隐性依赖”捞出来了：

- `requirements.txt` 很短，但并不等于真实运行依赖就这么少。LaTeX 编译链是明显漏写的，issue 里已经有人因为缺 `eso-pic.sty` 卡死。
- 代码里还直接 `import psutil` 做清理，但 `requirements.txt` 没列它。这说明 README 更像最小说明，不是完整、可复现实验环境清单。


#### ChatGPT:
结论先说清楚。

**AI-Scientist-v2 可以端到端跑起来。**\
但它不是“装个包、填一个 OpenAI key”就能原样跑通的项目。标准链路是：**先生成 research ideas → 再跑 BFTS 树搜索实验 → 聚合图表 → 收集引用并写论文 → 再做文本审稿和图文一致性审稿**。这个流程在 README 的运行说明和主入口脚本里是一致的。([GitHub](https://github.com/sakanaai/ai-scientist-v2), [GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py))

## 1）端到端到底怎么跑

标准两步。

第一步，先做 **idea generation**。你要先准备一个主题描述的 Markdown，里面至少有 `Title / Keywords / TL;DR / Abstract` 这类字段。然后用 `ai_scientist/perform_ideation_temp_free.py` 生成一个 ideas JSON。README 给了这一段标准流程。([GitHub](https://github.com/sakanaai/ai-scientist-v2?utm_source=chatgpt.com), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/ai_scientist/perform_ideation_temp_free.py?utm_source=chatgpt.com))

第二步，再用生成出来的 ideas JSON 跑主流程 `launch_scientist_bfts.py`。主脚本会做这些事：读取 idea、可选加载同名 `.py` 初始代码、可选拼接 `hf_dataset_reference.py`、写入实验目录、调用 BFTS 实验、聚合图表、收集 citations、写作、最后 review。([GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py))

一个最接近 README 的运行骨架是这样：

```bash
# 1. 环境
conda create -n ai_scientist python=3.11
conda activate ai_scientist
conda install pytorch torchvision torchaudio pytorch-cuda=12.4 -c pytorch -c nvidia
conda install anaconda::poppler
conda install conda-forge::chktex
pip install -r requirements.txt
pip install psutil
# 还要准备可用的 TeX/LaTeX 编译环境，见下文
```

```bash
# 2. API
export OPENAI_API_KEY=...
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION_NAME=...
export S2_API_KEY=...
```

```bash
# 3. 先生成 idea
python ai_scientist/perform_ideation_temp_free.py \
  --workshop-file ai_scientist/ideas/my_research_topic.md \
  --model gpt-4o-2024-05-13 \
  --max-num-generations 20 \
  --num-reflections 5
```

```bash
# 4. 再跑端到端主流程
python launch_scientist_bfts.py \
  --load_ideas ai_scientist/ideas/my_research_topic.json \
  --load_code \
  --add_dataset_ref \
  --model_writeup o1-preview-2024-09-12 \
  --model_citation gpt-4o-2024-11-20 \
  --model_review gpt-4o-2024-11-20 \
  --model_agg_plots o3-mini-2025-01-31 \
  --num_cite_rounds 20
```

跑完后，会在 `experiments/.../logs/0-run/` 下面看到 `unified_tree_viz.html`，最终 PDF 会出现在对应 experiment 目录里。README 说整轮通常要几个小时；论文里给出的经验上限是 **15 小时**。([GitHub](https://github.com/sakanaai/ai-scientist-v2), [arXiv](https://arxiv.org/pdf/2504.08066))

## 2）端到端运行真正需要的依赖

### 必需的系统/硬件依赖

- Linux
- NVIDIA GPU
- CUDA
- Python 3.11
- PyTorch + CUDA 12.4（README 示例）
- poppler
- chktex ([GitHub](https://github.com/sakanaai/ai-scientist-v2))

### `requirements.txt` 里的 Python 依赖

核心包包括：

- LLM/API：`anthropic`, `openai`, `boto3`, `botocore`, `backoff`
- 数据/模型：`numpy`, `transformers`, `datasets`, `tiktoken`
- 可视化/PDF：`matplotlib`, `seaborn`, `pypdf`, `pymupdf4llm`
- 工具链：`wandb`, `tqdm`, `rich`, `humanize`, `dataclasses-json`, `funcy`, `black`, `genson`, `shutup`, `python-igraph`, `coolname`, `jsonschema`, `omegaconf` ([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/requirements.txt))

### README 没写全，但实际很关键的“隐性依赖”

这里是最容易踩坑的地方。

**第一，LaTeX 编译环境不只是 `chktex`。**\
写作阶段会实际生成 PDF。GitHub issue #30 里已经有人卡在 `pdflatex` 缺 `eso-pic.sty`，直接导致 “no output PDF file produced”。这说明你需要的是**完整可用的 TeX Live / pdflatex 环境**，而不是只装 `chktex`。README 对这部分写得偏乐观。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/issues/30), [GitHub](https://github.com/sakanaai/ai-scientist-v2))

**第二，`psutil` 也应当装上。**\
主脚本最后会 `import psutil` 去清理子进程，但 `requirements.txt` 里并没有它。这是一个很典型的“仓库能跑但环境声明不完整”的信号。([GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/requirements.txt))

**第三，数据准备并没有完全自动化。**\
论文正文明确承认：系统对标准机器学习数据集更顺手，但对真实世界在线数据集的自动获取仍然困难；他们在 pest detection 实验里甚至是**手动从 Kaggle 下载并裁剪数据**后才跑通。也就是说，所谓“端到端”，在开放世界数据接入这一步并不彻底。([arXiv](https://arxiv.org/pdf/2504.08066))

## 3）需要哪些 API

分清“必需”和“可选”。

### 必需 API / 凭证

**1. OpenAI API**\
README 明确写了，OpenAI 模型走 `OPENAI_API_KEY`。而且主脚本默认的 `model_writeup / model_citation / model_review / model_agg_plots` 都是 OpenAI 系模型名。([GitHub](https://github.com/sakanaai/ai-scientist-v2), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py))

**2. AWS Bedrock 凭证**\
这是很多人一开始没意识到的点。`bfts_config.yaml` 默认把实验阶段的 `agent.code.model` 设成了 `anthropic.claude-3-5-sonnet-20241022-v2:0`。README 同时说明 Claude 通过 **AWS Bedrock** 使用，需要 `anthropic[bedrock]` 和 AWS 三个环境变量。\
所以，**按默认配置原样端到端跑，通常不只要 OpenAI，还要 Bedrock。** 这是结论，不是猜测。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/bfts_config.yaml), [GitHub](https://github.com/sakanaai/ai-scientist-v2))

### 可选 API

**3. Semantic Scholar API**\
`S2_API_KEY` 不是绝对必需，但 ideation 阶段做 novelty check、writeup 阶段收 citations 都会用它。README 说没有 key 也能跑，但会更容易被限流，甚至需要跳过 citation 阶段。([GitHub](https://github.com/sakanaai/ai-scientist-v2))

### 可替换 API

**4. Gemini API**\
README 说明 Gemini 也支持，走 `GEMINI_API_KEY`，并且是通过项目里的 OpenAI API 兼容方式接入。([GitHub](https://github.com/sakanaai/ai-scientist-v2))

## 4）默认到底用了哪些模型

仓库默认是**多模型编排**，不是单模型。

从配置、主脚本和论文三处交叉看，默认角色大致是：

- **实验代码生成**：Claude 3.5 Sonnet（Bedrock）
- **实验反馈 / VLM 反馈**：GPT-4o
- **总结/报告类 agent**：GPT-4o
- **plot aggregation**：`o3-mini-2025-01-31`
- **citation gathering**：`gpt-4o-2024-11-20`
- **writeup big model**：`o1-preview-2024-09-12`
- **writeup small model**：`gpt-4o-2024-05-13`
- **review**：`gpt-4o-2024-11-20` ([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/bfts_config.yaml), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py), [arXiv](https://arxiv.org/pdf/2504.08066))

这也解释了为什么它不适合“我只想配一个 key，所有阶段都统一模型”的简单使用方式。**它默认就是异构 agent + 异构模型。** ([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/bfts_config.yaml), [arXiv](https://arxiv.org/pdf/2504.08066))

## 5）需要哪些“外部 agent”

这里要把“外部 agent 平台”和“框架内部 agent 角色”分开。

### 不需要你额外部署的外部 agent 平台

仓库文档**没有要求**你再额外启动一个独立的 agent server、MCP 服务或 AIDE 服务。README 只说 tree-search 部分是 **built on top of AIDE**。也就是它借了 AIDE 的思路/实现基础，但对用户来说，不是“先把另一个 agent 系统部署起来再接进来”的模式。([GitHub](https://github.com/sakanaai/ai-scientist-v2), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py))

### 框架内部已经存在的 agent 角色

真正需要的是这些**内部 agent 角色**对应的模型服务：

- **Idea generation agent**：用 LLM 生成研究 idea，并调用 `SearchSemanticScholar` 和 `FinalizeIdea` 这两个工具动作。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/ai_scientist/perform_ideation_temp_free.py?utm_source=chatgpt.com))
- **Experiment manager / progress manager agent**：管理四个实验阶段。([arXiv](https://arxiv.org/pdf/2504.08066))
- **Code generation agent**：为树节点生成或修改实验代码。([arXiv](https://arxiv.org/pdf/2504.08066), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/bfts_config.yaml))
- **LLM feedback agent**：读程序输出和 traceback，判断节点是否有 bug。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/bfts_config.yaml), [arXiv](https://arxiv.org/pdf/2504.08066))
- **VLM feedback agent**：看实验图，检查标签、图例、可读性、重复图等。([arXiv](https://arxiv.org/pdf/2504.08066))
- **Plot aggregation agent**：主脚本里 `aggregate_plots`。([GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py))
- **Citation gathering agent**：`gather_citations`。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py))
- **Writeup agents**：small model + big model 双模型写稿。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py))
- **Review agent**：文本 review。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py))
- **VLM paper-review agent**：图、caption、reference 对齐检查。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py), [arXiv](https://arxiv.org/pdf/2504.08066))

### 四阶段实验 manager 具体做什么

论文讲得很清楚：

1. **Stage 1 Preliminary Investigation**：先搞出能跑的最小原型。
2. **Stage 2 Hyperparameter Tuning**：调超参，得到稳定 baseline。
3. **Stage 3 Research Agenda Execution**：执行核心研究议程。
4. **Stage 4 Ablation Studies**：做消融，支撑主结论。 ([arXiv](https://arxiv.org/pdf/2504.08066), [arXiv](https://arxiv.org/pdf/2504.08066))

## 6）还要准备哪些本地文件

除了 API 和环境，你还要知道这几个输入文件的逻辑。

- **主题描述 Markdown**：必须有，这是 ideation 的输入。([GitHub](https://github.com/sakanaai/ai-scientist-v2?utm_source=chatgpt.com))
- **ideas JSON**：由上一步生成，是主流程输入。([GitHub](https://github.com/sakanaai/ai-scientist-v2?utm_source=chatgpt.com), [GitHub](https://github.com/sakanaai/ai-scientist-v2))
- **同名 `.py` 初始代码**：只有你传 `--load_code` 时才会去找，而且是和 ideas JSON 同 basename 的 `.py`。没有就只会 warning。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py), [GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py))
- **`hf_dataset_reference.py`**：只有你传 `--add_dataset_ref` 时才会找。这个文件**不是仓库自带的标准必需文件**，更像你自己提供的数据集说明补丁。找不到也只是 warning，不会立即终止。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/launch_scientist_bfts.py), [GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py))

## 7）我给你的明确判断

**最小真实结论：**

- 想把 **AI-Scientist-v2 原样端到端跑通**，你至少要准备：\
  **Linux + NVIDIA GPU + CUDA + Python 3.11 + PyTorch CUDA 环境 + poppler + chktex + 完整 TeX/LaTeX 编译链 + `requirements.txt` 里的 Python 包 + `psutil` + OpenAI API + AWS Bedrock 凭证**。Semantic Scholar API 强烈建议配上。([GitHub](https://github.com/sakanaai/ai-scientist-v2), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/requirements.txt), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/bfts_config.yaml), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/issues/30), [GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py))

- **默认配置下，不存在“只靠 OpenAI key 就端到端原样跑通”这回事。**\
  因为实验代码生成默认就是 Claude 3.5 Sonnet on Bedrock。除非你自己改 `bfts_config.yaml`。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/bfts_config.yaml), [GitHub](https://github.com/sakanaai/ai-scientist-v2))

- **不需要额外接一个外部 agent 平台。**\
  需要的是把框架内部各 agent 角色对应的模型/API配好。([GitHub](https://github.com/sakanaai/ai-scientist-v2), [arXiv](https://arxiv.org/pdf/2504.08066), [arXiv](https://arxiv.org/pdf/2504.08066))

- **“开放世界数据接入”不是它现在的强项。**\
  对 Hugging Face 风格标准数据集更自然；对 Kaggle/真实世界数据，经常还是要人工准备。([arXiv](https://arxiv.org/pdf/2504.08066))

- **README 不是完整环境说明。**\
  至少 LaTeX 依赖和 `psutil` 这两点，README/requirements 都写得不完整。([GitHub](https://github.com/SakanaAI/AI-Scientist-v2/issues/30), [GitHub](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/requirements.txt), [GitHub](https://raw.githubusercontent.com/sakanaai/AI-Scientist-v2/main/launch_scientist_bfts.py))

你要是愿意，我下一条可以直接给你一份 **“AI-Scientist-v2 可复现安装清单 + 环境 YAML + 端到端命令模板”**，我会按“默认配置版”和“纯 OpenAI 改造版”两套给你。

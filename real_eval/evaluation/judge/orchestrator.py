#!/usr/bin/env python3
"""
Plan-Execution-Evidence Scoring Orchestrator
Evaluates a research run across 7 dimensions by calling an LLM judge.
"""
import json, os, sys, argparse, time, glob, re
from pathlib import Path
from datetime import datetime, timezone
import urllib.request, urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(BASE_DIR, "prompts")

# e2e.log 超出此长度就取头尾各半。原值 500000（头尾各 250K），
# 实测 152 个有日志的 run 里 17 个会被截断。
LOG_LIMIT_CHARS = 120000
# 中继已从 api.bianxie.ai 迁到 paratera。注意 paratera 的模型 ID **区分大小写**
# （`DeepSeek-V4-Flash` / `GPT-6-Luna`，小写会报 "no healthy deployments"）。
DEFAULT_MODEL = os.environ.get("JUDGE_MODEL", "DeepSeek-V4-Flash")
DEFAULT_API_BASE = os.environ.get("JUDGE_API_BASE", "https://llmapi.paratera.com/v1")


def require_api_key() -> str:
    """判官凭据**只从环境变量读**。

    历史上这里有一个硬编码的 fallback 密钥，并随公开仓库泄露过。
    现在不再提供任何默认值 —— 缺失即报错退出，避免同类事故重演。
    """
    for name in ("JUDGE_API_KEY", "OPENAI_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    raise SystemExit(
        "缺少判官 API 密钥。\n"
        "请设置 JUDGE_API_KEY（或 OPENAI_API_KEY）后重试。\n"
        "凭据只从环境变量读取；源码里刻意不保留任何默认值。"
    )

DIMENSIONS = ["pq", "pea", "er", "ou", "ecc", "sc", "cc"]
DIM_NAMES = {
    "pq": "Plan Quality", "pea": "Plan-Execution Alignment",
    "er": "Execution Robustness", "ou": "Observation Utilization",
    "ecc": "Evidence-Conclusion Closure", "sc": "State Consistency",
    "cc": "Contract Compliance",
}

PILOT_RUNS = [
    "f06-start-babylm-deepseek-v4-flash-20260914-231304",
    "f06-start-psydef-gpt-5-6-luna-20260916-035436",
    "f06-start-mountaincar-deepseek-v4-flash-20260914-055306",
]

def load_artifacts(run_dir):
    run_name = os.path.basename(run_dir)
    artifacts = {}
    # Framework-specific artifact paths
    if run_name.startswith(("f03-",)):
        path_map = {
            "research_idea": os.path.join("workspace", "research_idea.json"),
            "experiment_trace": os.path.join("workspace", "experiment_trace.json"),
            "final_report": os.path.join("workspace", "final_report.md"),
            "e2e_log": os.path.join("logs", "e2e.log"),
        }
    elif run_name.startswith(("f05-", "ds-full-")):
        path_map = {
            "research_idea": os.path.join("workspace", "research_idea.json"),
            "experiment_trace": os.path.join("workspace", "experiment_trace.json"),
            "final_report": os.path.join("workspace", "final_report.md"),
            "e2e_log": os.path.join("logs", "e2e.log"),
        }
    elif run_name.startswith(("01_", "02_")):
        # 01/02 是**外部交付包**的 run（`real_eval/runs_0102/`），产物在 `workspace/` 下，
        # 与 f03/f05 同布局。不加这一支会掉进下面的 else（根目录布局）→
        # 四个产物**全部** "<FILE NOT FOUND>"，而判官**照样给分** —— 静默的假分。
        #
        # 刻意**不**改成"探测哪个布局文件多"的通用写法：那会让 f06/f07 里同时存在
        # 两种布局的 run 改变分支，已发布的判官分不再可复现。这里只补 01_/02_ 一支。
        path_map = {
            "research_idea": os.path.join("workspace", "research_idea.json"),
            "experiment_trace": os.path.join("workspace", "experiment_trace.json"),
            "final_report": os.path.join("workspace", "final_report.md"),
            # 01 的完整日志叫 e2e.log；**02 的 run 全部叫 native.log**
            # （实测：01 侧 24/24 有 e2e.log，02 侧 0/24、只有 native.log）。
            # 写死 e2e.log 会让 02 的日志维度**盲评**。
            "e2e_log": next(
                (c for c in ("logs/e2e.log", "logs/native.log", "logs/native_stdout.log")
                 if os.path.exists(os.path.join(run_dir, c))),
                os.path.join("logs", "e2e.log"),
            ),
        }
    else:  # f04 / f06 / f07 等：**按实际存在的布局探测**，不靠名字前缀
        # 2026-10-12 实测：04/06/07 的单元**两种布局都有**（06：76 个只有 workspace 布局、
        # 34 个只有 root 布局、**0 个两者都有**；已判过的 10 个 06 run 全是 root 布局）。
        # 所以「有 workspace/research_idea.json 就用 workspace 布局，否则用 root」是安全的 ——
        # 已发布的判官分不会被改变，而此前被判成 FILE NOT FOUND 的单元这才有可能被判。
        if os.path.exists(os.path.join(run_dir, "workspace", "research_idea.json")):
            path_map = {
                "research_idea": os.path.join("workspace", "research_idea.json"),
                "experiment_trace": os.path.join("workspace", "experiment_trace.json"),
                "final_report": os.path.join("workspace", "final_report.md"),
                "e2e_log": next(
                    (c for c in ("logs/e2e.log", "logs/native.log", "logs/native_stdout.log")
                     if os.path.exists(os.path.join(run_dir, c))),
                    os.path.join("logs", "e2e.log")),
            }
        else:
            path_map = {
                "research_idea": "research_idea.json",
                "experiment_trace": "experiment_trace.json",
                "final_report": "final_report.md",
                "e2e_log": "e2e.log",
            }
    for name, rel_path in path_map.items():
        path = os.path.join(run_dir, rel_path)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError as exc:
                # 权限受限（实测有 root:600 的产物）：**不能当"读到了"** ——
                # 判官遇到空/占位内容照样给分，所以显式记 readable=False 让调用方跳过。
                artifacts[name] = {"path": path, "size": 0, "readable": False,
                                   "content": f"<UNREADABLE: {exc.strerror or exc}>"}
                continue
            artifacts[name] = {"path": path, "size": len(content), "content": content}
        else:
            artifacts[name] = {"path": path, "size": 0, "readable": False, "content": "<FILE NOT FOUND>"}
    if artifacts["e2e_log"]["size"] > LOG_LIMIT_CHARS:
        c = artifacts["e2e_log"]["content"]
        half = LOG_LIMIT_CHARS // 2
        artifacts["e2e_log"]["content"] = (
            c[:half] + "\n...TRUNCATED...\n" + c[-half:]
        )
    return artifacts


# 每个维度在提示词里声明要读的文件。er/sc/cc 以 e2e.log 为主要证据
# （judge_er.md 原文：「不因日志长度或最终报告写得好而替代日志证据」），
# 所以这些 artifact 缺失时不能照常打分。
REQUIRED_ARTIFACTS = {
    "pq": ["research_idea"],
    "pea": ["research_idea", "experiment_trace"],
    "er": ["e2e_log"],
    "ou": ["experiment_trace", "final_report"],
    "ecc": ["experiment_trace", "final_report"],
    "sc": ["research_idea", "experiment_trace", "final_report", "e2e_log"],
    "cc": ["research_idea", "experiment_trace", "final_report", "e2e_log"],
}

# 提示词里出现的占位符名 → artifacts 的键
PLACEHOLDER_KEYS = {
    "research_idea.json": "research_idea",
    "experiment_trace.json": "experiment_trace",
    "final_report.md": "final_report",
    "e2e.log": "e2e_log",
}

def load_prompt(dim):
    path = os.path.join(PROMPT_DIR, f"judge_{dim}.md")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt not found: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()

def _artifacts_section(artifacts, names=None):
    """把若干 artifact 拼成带路径标注的一段。"""
    out = ""
    for name in (names or ["research_idea", "experiment_trace", "final_report", "e2e_log"]):
        a = artifacts[name]
        out += f"<{a['path']}>\n{a['content']}\n</{a['path']}>\n\n"
    return out


def build_prompt(template, artifacts):
    """把提示词里的占位符替换成真正的文件内容。

    原来只替换 `{{ARTIFACTS}}`，但七个提示词没有一个用它 —— 它们用的是
    `{{research_idea.json}}` / `{{e2e.log}}` 这些具体名字。结果是占位符原样
    发给模型，内容被堆在后面的 `## Artifacts` 附录里，而提示词正文写着
    「下面是 XXX 全文：」后面跟着一个空的 `{{...}}`。
    """
    out = template
    for placeholder, key in PLACEHOLDER_KEYS.items():
        token = "{{" + placeholder + "}}"
        if token in out:
            out = out.replace(token, artifacts[key]["content"])
    if "{{all_artifacts}}" in out:
        out = out.replace("{{all_artifacts}}", _artifacts_section(artifacts))
    if "{{ARTIFACTS}}" in out:  # 旧写法，保留兼容
        out = out.replace("{{ARTIFACTS}}", _artifacts_section(artifacts))

    # 只有还有没替换掉的占位符时才附附录，避免内容重复送两遍。
    leftover = re.findall(r"\{\{[^}]+\}\}", out)
    if leftover:
        out += "\n\n## Artifacts\n\n" + _artifacts_section(artifacts)
    return out

def parse_json(text):
    if not text:
        return {"error": "empty response"}
    text = text.strip()
    # Try markdown code block
    cb = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', text)
    if cb:
        try:
            return json.loads(cb.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try balanced braces
    start = text.find('{')
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        pass
    # Try whole text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    return {"error": "parse failed", "raw_response": text[:8000]}

def call_llm(prompt, model=DEFAULT_MODEL, api_base=DEFAULT_API_BASE, max_retries=3):
    headers = {
        "Authorization": f"Bearer {require_api_key()}",
        "Content-Type": "application/json",
    }
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16384,
        "temperature": 0.01,
    }).encode()
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{api_base}/chat/completions", data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]
            parsed = parse_json(content)
            # 空响应 / 解析失败也是**可重试**的。原来只有抛异常才重试，
            # 于是判官偶尔返回空内容时会静默变成 {"error": "empty response"}——
            # 下游看到的是"这一维没有值"，和一个真实的低分无法区分。
            if isinstance(parsed, dict) and "error" in parsed:
                raise ValueError(f"unusable response: {parsed['error']}")
            return parsed
        except Exception as e:
            print(f"  API attempt {attempt+1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                return {"error": str(e)[:200], "score": None,
                        "justification": f"failed after {max_retries} attempts"}

def judge_run(run_dir, model=DEFAULT_MODEL, dims=None):
    run_name = os.path.basename(run_dir)
    print(f"\n{'='*60}")
    print(f"Evaluating: {run_name}")
    print(f"{'='*60}")
    artifacts = load_artifacts(run_dir)
    parts = run_name.split("-")
    framework = "06"
    topic = parts[2] if len(parts) > 2 else "unknown"
    model_name = "-".join(parts[3:-2]) if len(parts) > 4 else "unknown"
    if dims is None:
        dims = DIMENSIONS
    scores = {}
    skipped = {}
    for i, dim in enumerate(dims):
        print(f"  [{i+1}/{len(dims)}] {DIM_NAMES.get(dim, dim)}...", end="", flush=True)

        # 该维声明要读的文件若缺失或不可读，这一维没有证据可依。
        # 判官面对 <FILE NOT FOUND> 照样会给一个分数，所以必须在这里拦。
        missing = [
            name for name in REQUIRED_ARTIFACTS.get(dim, [])
            if not artifacts[name].get("readable", artifacts[name]["size"] > 0)
        ]
        if missing:
            skipped[dim] = ", ".join(missing)
            scores[dim] = {
                "score": None,
                "error": f"required artifact missing or unreadable: {', '.join(missing)}",
            }
            print(f" SKIPPED（缺 {', '.join(missing)}）")
            continue

        prompt = build_prompt(load_prompt(dim), artifacts)
        result = call_llm(prompt, model=model)
        scores[dim] = result
        print(f" score={result.get('score', 'ERR')}")
    # Merge with existing score.json if present
    score_path = os.path.join(run_dir, "score.json")
    existing = {}
    if os.path.exists(score_path):
        try:
            with open(score_path, encoding="utf-8") as f:
                existing = json.load(f)
            existing_scores = existing.get("evaluation", {}).get("dimensions", {})
            for k, v in existing_scores.items():
                if k not in scores:
                    scores[k] = v
        except:
            pass
    output = {
        "framework": framework, "topic": topic, "model": model_name,
        "run_dir": run_name,
        "evaluation": {
            "judge_model": model,
            "judge_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "artifact_sizes": {k: v["size"] for k, v in artifacts.items()},
            "artifact_readable": {k: bool(v.get("readable", v["size"] > 0))
                                  for k, v in artifacts.items()},
            "dimensions_skipped": skipped,
            "dimensions": scores,
        },
    }
    with open(score_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  -> Saved: {score_path} (merged {len(scores)} dims)")
    return output

def main():
    parser = argparse.ArgumentParser(description="Plan-Execution-Evidence Scoring")
    parser.add_argument("--run", help="Run directory path")
    parser.add_argument("--pilot", action="store_true", help="3 predefined pilot runs")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dims", nargs="+", choices=DIMENSIONS, default=None)
    args = parser.parse_args()
    runs_root = os.environ.get(
        "REAL_EVAL_RUN_ROOT",
        str(Path(__file__).resolve().parents[3] / "real_eval" / "runs"),
    )
    if args.pilot:
        dirs = [os.path.join(runs_root, r) for r in PILOT_RUNS]
    elif args.run:
        dirs = [args.run]
    else:
        parser.print_help()
        sys.exit(1)
    for d in dirs:
        if not os.path.isdir(d):
            print(f"Not a dir: {d}"); continue
        judge_run(d, model=args.model, dims=args.dims)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Hybrid judge: single call for the stable dimensions, a containerised agent for
the evidence-heavy ones.

Why the split
-------------
Both paths were measured on the same five cells with two runs each:

    single call (orchestrator.py)   mean |Δ| 0.052   84% identical
    container agent (opencode)      mean |Δ| 0.102   63% identical

The single call is twice as reproducible, but it only ever sees a head/tail
slice of the log, so its justifications for ER / SC / CC -- the dimensions whose
rubric says "judge from the log, not from how well the report reads" -- cannot
cite specifics. The agent greps the log, counts distinct error events and checks
stage markers, which is what those rubrics ask for, and it produced a score for
CC where the single call twice returned an empty response. It costs that
reproducibility though: with the agent, ER was different on all 3 comparable
cells.

So: keep the single call where it is already stable, use the agent where the
justification has to be grounded in the log.

    pq / pea / ou / ecc   ->  single call  (orchestrator.py)
    er / sc / cc          ->  container agent (opencode)

Isolation
---------
The agent runs in a container with the sandbox bind-mounted read-only. The
sandbox holds only the four judge artifacts -- `workspace/score.json` (the
official score) and `provider.env` are deliberately absent, so the judge cannot
see the answer it is meant to be independent of.

Usage
-----
    python3 hybrid_judge.py --run <run_dir> [--agent-config opencode.json]
                            [--image autoresearchclaw:runtime-opencode]
                            [--dims pq pea ou ecc er sc cc] [--dry-run]

Needs Docker and, for the agent dimensions, an opencode config file whose
provider points at an OpenAI-compatible endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import orchestrator as orch  # noqa: E402

LLM_DIMS = ("pq", "pea", "ou", "ecc")
AGENT_DIMS = ("er", "sc", "cc")

# er 和 cc 走"枚举 → 程序算分"：让模型只负责数准、抄准、判准处置，分数由固定规则算出。
# 实测（3 格 × 2 遍）：让模型直接给分时 er 平均绝对差 0.083、0/3 一致；改成枚举算分后
# 3/3 完全一致、平均绝对差 0.000 —— 枚举的残余波动被"算分"这一步吸收了。
# sc 的锚点混了整体判断，暂时仍由模型直接给分。
# 只有 er 走枚举。**cc 曾经也走过，已撤回** —— cc 的"必需阶段"若从日志自己推导
# 就是循环定义（拿"跑了什么"当"应该跑什么"），永远发现不了缺失阶段，
# 实测会把 cc 抬高到 1.0。而 cc 用 agent 直接给分本来就 4/4 完全一致，不需要改。
ENUM_DIMS = ("er",)

# The agent prompt is assembled from the same rubric files the single call uses,
# minus their "## 维度定义" section -- the agent reads the files itself instead
# of being handed their contents.
#
# 维度名以 prompts/judge_<dim>.md 的标题为准 —— 那是判官实际读到的正文，两者必须一致。
# 此前 pea/ou/ecc/sc 四项与提示词标题不符；因 agent 路径只跑 er/sc/cc、且 er 走枚举
# 不拼标签，**实际只有 sc 受影响**（pq/pea/ou/ecc 四个标签在 agent 路径上是死代码）。
# ⚠️ 修 sc 会改变 agent 提示词，此前由 agent 路径产出的 sc 值需重判 ——
# 查 score.json 的 evaluation.judge_mode.agent_dims 是否含 "sc"。
DIM_LABELS = {
    "pq": "计划质量", "pea": "计划—执行一致性", "er": "执行稳健性", "ou": "观察利用",
    "ecc": "证据—结论闭合", "sc": "状态一致性", "cc": "合同合规",
}

PROMPT_HEADER = """# 科研代理运行评审任务

你被要求评审**一次研究代理框架的运行**。所有证据都在**当前工作目录**下：

- `research_idea.json`    —— 框架自己写的研究计划
- `experiment_trace.json` —— 框架自己记录的实验轨迹
- `final_report.md`       —— 框架自己写的最终报告
- `e2e.log`               —— **宿主抓取的端到端执行日志**，框架改不了它

## 重要

1. **只用当前目录里的文件**，不要到别处找。
2. 文件可能很大 —— 用 `grep` / `wc` / `sed` / `head` / `tail` 自己去找证据，
   **不要只读开头和结尾**。
3. 报告和计划是框架自己写的，**日志才是宿主记录的事实**。两者冲突时以日志为准。
4. 某个文件不存在时，该维度如实说明「无证据」，`score` 用 `null`。
5. 每一项评分都要有**来自文件原文的具体引用**作为依据。

下面是对各维度逐一评分的要求。

---
"""


def build_agent_prompt(dims: tuple[str, ...]) -> str:
    """组装 agent 提示词：共同开头 + 各维的节 + **唯一一处**输出说明。

    不能把多份完整提示词直接拼接 —— 每份末尾都写着"只输出一个 JSON 对象"，
    互相矛盾，模型会退回成直接给分的格式。枚举维度（er/cc）用
    prompts/agent_<dim>.md（口径写死、只输出枚举、不给分），其余维度用
    prompts/judge_<dim>.md 的评分要求。
    """
    import json as _json

    parts = [(HERE / "prompts" / "agent_enum_header.md").read_text(encoding="utf-8").rstrip()]
    for d in dims:
        if d in ENUM_DIMS:
            parts.append((HERE / "prompts" / f"agent_{d}.md").read_text(encoding="utf-8").rstrip())
            continue
        text = (HERE / "prompts" / f"judge_{d}.md").read_text(encoding="utf-8")
        m = re.search(r"^## 维度定义", text, re.M)
        body = text[m.start():] if m else text
        body = re.sub(r"^## JSON 输出格式[\s\S]*$", "", body, flags=re.M)
        parts.append(f"## {d.upper()} —— {DIM_LABELS[d]}\n\n{body.strip()}\n")

    enum_schema = _json.loads(
        (HERE / "prompts" / "agent_enum_schema.json").read_text(encoding="utf-8"))
    want = {}
    for d in dims:
        want[d] = enum_schema[d] if d in ENUM_DIMS else {
            "score": "<0-1 之间，落在上面锚点里的档位>", "justification": "<引用原文的具体依据>"}
    parts.append(
        "\n# 输出\n\n只输出**一个 JSON 对象**，不要别的文字、不要代码围栏。"
        "键恰好是下面这些：\n\n```json\n"
        + _json.dumps(want, ensure_ascii=False, indent=2)
        + "\n```\n\n枚举维度里 `events` / `stages` 为空数组是合法结果。\n"
    )
    return "\n\n".join(parts)


def score_er(payload: dict) -> float | None:
    """按 judge_er.md 的五档锚点，从事件枚举算出分数。"""
    events = payload.get("events")
    if not isinstance(events, list):
        return None
    if not events:
        return 1.0
    n = len(events)
    cascading = sum(1 for e in events if e.get("impact") == "cascading")
    hard = sum(1 for e in events if e.get("disposition") in ("unrecovered", "ignored"))
    unverified = sum(1 for e in events if e.get("disposition") == "recovered_unverified")
    if cascading:
        return 0.0          # 级联失败
    if hard:
        return 0.25 if hard / n > 0.5 else 0.5
    if unverified:
        return 0.75         # 全部恢复，但部分缺验证
    return 1.0


def score_cc(payload: dict) -> float | None:
    """按 judge_cc.md 的五档锚点，从阶段清单算出分数。"""
    stages = payload.get("stages")
    if not isinstance(stages, list):
        return None
    required = payload.get("stages_required") or [s.get("name") for s in stages]
    total = len(required)
    if total == 0:
        return None
    done = sum(1 for s in stages if s.get("completed"))
    if done == total:
        return 1.0
    if done == 0:
        return 0.0
    ratio = done / total
    if ratio >= 0.75:
        return 0.75
    if ratio >= 0.5:
        return 0.5
    return 0.25


SCORERS = {"er": score_er, "cc": score_cc}


def build_sandbox(run_dir: pathlib.Path, dest: pathlib.Path) -> list[str]:
    """Copy only the four judge artifacts into a scratch directory.

    Deliberately excludes workspace/score.json (the official score) and
    provider.env. Returns the list of artifact names that were copied.
    """
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name, rel in (
        ("research_idea", "workspace/research_idea.json"),
        ("experiment_trace", "workspace/experiment_trace.json"),
        ("final_report", "workspace/final_report.md"),
    ):
        src = run_dir / rel
        if src.is_file():
            shutil.copy2(src, dest / pathlib.Path(rel).name)
            copied.append(name)
    for rel in ("logs/e2e.log", "logs/native.log", "logs/native_stdout.log"):
        src = run_dir / rel
        if src.is_file():
            shutil.copy2(src, dest / "e2e.log")
            copied.append("e2e_log")
            break
    return copied


def _json_objects(text: str) -> list[dict]:
    """抽出文本里**全部**顶层平衡括号的 JSON 对象。

    不能简单地"第一个 { 到最后一个 }" —— 模型经常按维度分段输出多个对象，
    那样切出来会把中间的说明文字包进去，导致解析失败。
    """
    out: list[dict] = []
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            out.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = None
    return out


def parse_agent_output(text: str, dims: tuple[str, ...]) -> dict:
    objs = _json_objects(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M))
    merged: dict = {}
    for o in objs:
        for k, v in o.items():
            merged[k] = v            # 后者覆盖前者
        if json.dumps(o, ensure_ascii=False) and any(d in o for d in dims):
            merged.update(o)
    missing = {d: {"score": None, "error": "dimension missing from agent output"}
               for d in dims if d not in merged}
    merged.update(missing)
    return {d: merged[d] for d in dims}


def finalize_agent_scores(base: dict) -> dict:
    """枚举维度：把 score 换成程序按固定规则算出的值。"""
    out = {}
    for dim, payload in base.items():
        if dim in ENUM_DIMS and isinstance(payload, dict) and "error" not in payload:
            computed = SCORERS[dim](payload)
            payload = dict(payload)
            payload["score"] = computed
            payload["score_basis"] = "computed_from_enumeration"
            if computed is None:
                payload["error"] = "enumeration missing required structure"
        out[dim] = payload
    return out


def run_agent(sandbox: pathlib.Path, prompt: str, agent_config: pathlib.Path,
              image: str, timeout: int) -> dict:
    out_dir = sandbox.parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{sandbox}:/sandbox:ro",
        "-v", f"{agent_config}:/oc.json:ro",
        "-v", f"{sandbox.parent/'prompt.md'}:/prompt.md:ro",
        "-w", "/sandbox",
        "--entrypoint", "bash", image, "-lc",
        "mkdir -p /tmp/h/.config/opencode && cp /oc.json /tmp/h/.config/opencode/opencode.json "
        "&& export HOME=/tmp/h && cd /sandbox && opencode run \"$(cat /prompt.md)\"",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 and not proc.stdout.strip():
        return {d: {"score": None, "error": f"agent failed: {proc.stderr.strip()[-300:]}"}
                for d in AGENT_DIMS}
    return parse_agent_output(proc.stdout, AGENT_DIMS)


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid judge: single call + container agent")
    ap.add_argument("--run", required=True, help="run directory")
    ap.add_argument("--agent-config", help="opencode.json for the agent provider")
    ap.add_argument("--image", default="autoresearchclaw:runtime-opencode")
    ap.add_argument("--model", default=orch.DEFAULT_MODEL, help="model for the single-call dims")
    ap.add_argument("--dims", nargs="+", choices=orch.DIMENSIONS, default=list(orch.DIMENSIONS))
    ap.add_argument("--timeout", type=int, default=2400, help="per-agent-run timeout, seconds")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the sandbox and prompts, print what would run, do nothing else")
    args = ap.parse_args()

    run_dir = pathlib.Path(args.run).resolve()
    if not run_dir.is_dir():
        print(f"not a directory: {run_dir}", file=sys.stderr)
        return 2

    llm_dims = tuple(d for d in args.dims if d in LLM_DIMS)
    agent_dims = tuple(d for d in args.dims if d in AGENT_DIMS)
    if agent_dims and not args.agent_config:
        print("--agent-config is required for the agent dimensions "
              f"({', '.join(agent_dims)})", file=sys.stderr)
        return 2

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="hybrid-judge-"))
    sandbox = workdir / "sandbox"
    copied = build_sandbox(run_dir, sandbox)
    (sandbox / "prompt.md").write_text(
        build_agent_prompt(agent_dims or AGENT_DIMS), encoding="utf-8")
    # run_agent mounts <sandbox>/../prompt.md
    shutil.move(str(sandbox / "prompt.md"), str(workdir / "prompt.md"))

    print(f"run        : {run_dir}")
    print(f"sandbox    : {sandbox}  ({', '.join(copied) or '空'})")
    print(f"单次调用    : {', '.join(llm_dims) or '—'}")
    print(f"容器 agent  : {', '.join(agent_dims) or '—'}")

    if args.dry_run:
        print("\n--dry-run：到此为止。沙箱内容：")
        for p in sorted(sandbox.iterdir()):
            print(f"   {p.name}  {p.stat().st_size} B")
        return 0

    scores: dict = {}
    if llm_dims:
        # 复用编排器的取产物/构造提示词/调用逻辑，保证与单次路径完全一致
        artifacts = orch.load_artifacts(str(run_dir))
        for dim in llm_dims:
            prompt = orch.build_prompt(orch.load_prompt(dim), artifacts)
            result = orch.call_llm(prompt, model=args.model)
            scores[dim] = result
            print(f"  [llm]   {dim}: {result.get('score', 'ERR')}")
    if agent_dims:
        cfg = pathlib.Path(args.agent_config).resolve()
        agent_scores = finalize_agent_scores(
            run_agent(sandbox, "", cfg, args.image, args.timeout))
        for dim in agent_dims:
            scores[dim] = agent_scores[dim]
            print(f"  [agent] {dim}: {agent_scores[dim].get('score', 'ERR')}")

    score_path = run_dir / "score.json"
    existing = {}
    if score_path.is_file():
        try:
            existing = json.loads(score_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    payload = dict(existing)
    ev = dict(payload.get("evaluation") or {})
    ev["dimensions"] = {**(ev.get("dimensions") or {}), **scores}
    ev["judge_mode"] = {
        "single_call_dims": list(llm_dims),
        "agent_dims": list(agent_dims),
        "agent_image": args.image if agent_dims else None,
    }
    payload["evaluation"] = ev
    score_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    print(f"\n写入 {score_path}")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

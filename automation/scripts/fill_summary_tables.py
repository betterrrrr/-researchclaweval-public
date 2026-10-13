#!/usr/bin/env python3
"""把 7 框架汇总报告里的**表格**从总表统一生成（幂等）。

汇总报告 `analysis/seven_frameworks_summary.md` 里的表格用标记占位：

    <!-- SUMMARY:matrix -->       官方分矩阵（7 框架 × 5 topic × 4 模型，每格最优）
    <!-- SUMMARY:coverage -->     覆盖矩阵（官方分 / 轨迹 / 判官 / ED 的覆盖进度）
    <!-- SUMMARY:champions -->    每 topic 的跨框架冠军（含方向与出处档位）
    <!-- SUMMARY:exclusions -->   剔除登记（三类污染）

正文（口径、边界、结论）由人写，脚本只填表 —— 保证 7 份报告与汇总**同源同口径**。
"""

from __future__ import annotations

import os

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2]))
REPORT = REPO / "analysis" / "evaluation_metrics.json"
SUMMARY = REPO / "analysis" / "seven_frameworks_summary.md"
EXCLUSIONS = REPO / "automation" / "scripts" / "score_exclusions.json"

FRAMEWORKS = ["01", "02", "03", "04", "05", "06", "07"]
FNAME = {"01": "AI-Researcher", "02": "AI-Scientist-v2", "03": "ARIS", "04": "AutoResearchClaw",
         "05": "DeepScientist", "06": "DrClaw", "07": "EvoScientist"}
TOPICS = ["arc", "mc", "babylm", "psydef", "tdc"]
MODELS = ["GPT-6-Luna", "GPT-5.6-Luna", "DeepSeek-V4", "Kimi-K2.6"]
DIRECTION = {"arc": -1, "babylm": -1, "mc": 1, "psydef": 1, "tdc": 1}
MARK = {"arc": "↓越低越好", "babylm": "↓越低越好", "mc": "↑越高越好",
        "psydef": "↑越高越好", "tdc": "↑越高越好"}
SRC_CLASS = {  # score_source → 档位
    "official_adapter_whest_run": "官方", "official_evaluate_py": "官方",
    "host_hidden_test_labels": "官方", "host_local_scorer": "官方",
    "manual_record": "手工记录", "framework_experiment_trace": "框架自报",
    "mountaincar-deepseek-launch.log": "非官方口径",
}


def fmt(v, digits=4):
    if v is None:
        return "—"
    if isinstance(v, float):
        if v != 0 and abs(v) < 1e-3:
            return f"{v:.2e}"
        return f"{v:.{digits}g}"
    return str(v)


def score_source_of(row):
    """该格官方分的**出处字段**（从 run 的 score.json / 旁挂 provenance 读，不猜）。

    与 `fill_metrics_blocks.provenance()` 同一套解析：两处若各写一份，迟早出现
    「同一格两个出处」，所以这里直接复用。
    """
    if row.get("exclusion_class"):
        return "已剔除"
    if row.get("official_final") is None:
        return "—"
    try:
        sys.path.insert(0, str(REPO / "automation" / "scripts"))
        import fill_metrics_blocks as FMB  # noqa: PLC0415
        return FMB.provenance(row, row["topic"])
    except Exception:  # noqa: BLE001
        return "⚠️ 出处未标"


def table_matrix(rows) -> str:
    by = {(r["framework"], r["topic"], r["model"]): r for r in rows}
    out = [f"| 框架 | topic | " + " | ".join(MODELS) + " |",
           "|---|---|" + "---|" * len(MODELS)]
    for fw in FRAMEWORKS:
        for topic in TOPICS:
            cells = []
            for m in MODELS:
                r = by.get((fw, topic, m))
                cells.append(fmt(r.get("official_final")) if r else "—")
            out.append(f"| {fw} {FNAME[fw]} <br>`{topic}` {MARK[topic]} | "
                       f"{topic} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def table_coverage(rows) -> str:
    out = ["| 框架 | 格子 | 官方分 | 其中官方评分器 | 其中框架自报 | 轨迹(trace_metric) | 轨迹(judge_ordinal) | 轨迹无值 | 判官七维 | ED |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for fw in FRAMEWORKS:
        sub = [r for r in rows if r["framework"] == fw]
        def n(pred): return sum(1 for r in sub if pred(r))
        out.append("| {} {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            fw, FNAME[fw], len(sub),
            n(lambda r: r.get("official_final") is not None),
            n(lambda r: r.get("basis_official") == "official_scorer"),
            n(lambda r: r.get("basis_official") == "framework_self_reported"),
            n(lambda r: r["basis_trajectory"] == "trace_metric"),
            n(lambda r: r["basis_trajectory"] == "judge_ordinal"),
            n(lambda r: r["basis_trajectory"] not in ("trace_metric", "judge_ordinal")),
            n(lambda r: str(r["basis_judge"]).startswith("judge_7dim")),
            n(lambda r: r.get("ed") is not None)))
    tot = len(rows)
    def N(pred): return sum(1 for r in rows if pred(r))
    out.append("| **合计** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** |".format(
        tot, N(lambda r: r.get("official_final") is not None),
        N(lambda r: r.get("basis_official") == "official_scorer"),
        N(lambda r: r.get("basis_official") == "framework_self_reported"),
        N(lambda r: r["basis_trajectory"] == "trace_metric"),
        N(lambda r: r["basis_trajectory"] == "judge_ordinal"),
        N(lambda r: r["basis_trajectory"] not in ("trace_metric", "judge_ordinal")),
        N(lambda r: str(r["basis_judge"]).startswith("judge_7dim")),
        N(lambda r: r.get("ed") is not None)))
    return "\n".join(out)


def table_champions(rows) -> str:
    out = ["| topic | 方向 | 冠军 | 值 | 出处档位 | 轨迹 basis | 备注 |", "|---|---|---|---|---|---|---|"]
    for topic in TOPICS:
        cand = [r for r in rows if r["topic"] == topic and r.get("official_final") is not None]
        cand.sort(key=lambda r: DIRECTION[topic] * r["official_final"], reverse=True)
        if not cand:
            out.append(f"| `{topic}` | {MARK[topic]} | — | — | — | — | 无有效分 |")
            continue
        t = cand[0]
        note = ""
        if topic == "babylm":
            note = ("⚠️ **框架自报**（`framework_experiment_trace`），非官方；"
                    "手工矩阵口径另有更优值 20.01（报告正文值，trace 里为 `None`，管线看不到）")
        if topic == "mc":
            note = ("同框架 `GPT-6-Luna` 列另有 85.2369（官方 `official_evaluate_py`，但 "
                    "`state.json` 记 Manual rescue、`exit_code=43`）—— 引用该格需注释产出路径")
        if topic == "arc":
            note = "官方 WHEST 适配器产出；同族 9.48e-05（GPT-6 列）已验证 `Failed MLPs: 0 of 100`"
        out.append(f"| `{topic}` | {MARK[topic]} | **{FNAME[t['framework']]} × {t['model']}** | "
                   f"{fmt(t['official_final'])} | {score_source_of(t)} | `{t['basis_trajectory']}` | {note} |")
    return "\n".join(out)


def table_exclusions(rows) -> str:
    payload = json.loads(EXCLUSIONS.read_text(encoding="utf-8")) if EXCLUSIONS.is_file() else {"exclusions": []}
    out = ["| run | 框架×topic×模型 | 记录值 | 类别 | scope | 处置 |", "|---|---|---|---|---|---|"]
    for e in payload.get("exclusions") or []:
        out.append("| `{}`{} | {}×{}×{} | {} | `{}` | `{}` | {} |".format(
            e.get("run_dir"), ("/" + e["unit_dir"]) if e.get("unit_dir") else "",
            e.get("framework"), e.get("topic"), e.get("model"),
            fmt(e.get("recorded_score")), e.get("class"), e.get("scope", "score"),
            e.get("action", "已从官方分与/或轨迹中置空")))
    return "\n".join(out)


BUILDERS = {"matrix": table_matrix, "coverage": table_coverage,
            "champions": table_champions, "exclusions": table_exclusions}
BLOCK = re.compile(r"<!-- SUMMARY:(\w+) -->(.*?)<!-- /SUMMARY:\1 -->", re.S)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not SUMMARY.is_file():
        print(f"[skip] 汇总报告还不存在: {SUMMARY}（先写正文骨架，表格标记会被填）")
        return 0
    rows = json.loads(REPORT.read_text(encoding="utf-8"))["rows"]
    text = SUMMARY.read_text(encoding="utf-8")
    filled = 0

    def render(name: str) -> str:
        return f"<!-- SUMMARY:{name} -->\n{BUILDERS[name](rows)}\n<!-- /SUMMARY:{name} -->"

    # ① 已成对的块：原地替换（幂等）
    for m in list(BLOCK.finditer(text)):
        name = m.group(1)
        if name not in BUILDERS:
            print(f"[warn] 未知表格标记: {name}")
            continue
        text = text[:m.start()] + render(name) + text[m.end():]
        filled += 1
    # ② 还没填过的单标记：就地插入，插入后自带闭合标记（下次走 ①）
    #    注意只处理**没有**闭合标记的那些，否则会把 ① 刚填好的块再替换一次（内容相同但计数虚高）。
    for name in BUILDERS:
        single = f"<!-- SUMMARY:{name} -->"
        if single in text and f"<!-- /SUMMARY:{name} -->" not in text:
            text = text.replace(single, render(name), 1)
            filled += 1

    if not args.dry_run:
        SUMMARY.write_text(text, encoding="utf-8")
    print(f"填入 {filled} 张表" + ("（dry-run）" if args.dry_run else f" → {SUMMARY}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

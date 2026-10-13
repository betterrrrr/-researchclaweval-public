#!/usr/bin/env python3
"""把 12 指标块**统一**填进 7 份框架技术报告。

为什么单独一个脚本：7 份报告里的数字必须**同源同口径**。让每份报告各自抄一遍，
迟早出现「同一格两个数」。这里只认一个来源 —— `analysis/evaluation_metrics.json` ——
并在数字旁带上 `basis_*` 档位（官方 / 框架自报 / 判官序数 / 结构性缺失）。

占位约定（写报告的人留下，本脚本替换）：
    <!-- METRICS:01:arc -->         框架码 + topic

**幂等**：填进去的块用 `<!-- METRICS-BLOCK:01:arc -->` … `<!-- /METRICS-BLOCK:01:arc -->`
包住，重跑时按这两个标记**原地替换**，不会重复插入、也不会串到别的 topic。

用法：
    python3 fill_metrics_blocks.py --check     # 只报告状态
    python3 fill_metrics_blocks.py             # 写入
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
ANALYSIS_DIR = REPO / "analysis"
RUN_ROOTS = (Path(os.environ.get("REAL_EVAL_RUN_ROOT", Path(__file__).resolve().parents[2] / "real_eval" / "runs")), Path(os.environ.get("REAL_EVAL_RUNS_0102_ROOT", Path(__file__).resolve().parents[2] / "real_eval" / "runs_0102")))

TOPIC_TITLE = {
    "arc": "ARC-WBE-2026", "mc": "MountainCar-Continuous", "babylm": "BabyLM-10M",
    "psydef": "PsyDefDetect", "tdc": "TDC-ADMET-Tox",
}
MODEL_ORDER = ("GPT-6-Luna", "GPT-5.6-Luna", "DeepSeek-V4", "Kimi-K2.6")
REPORTS = {
    "01": "analysis_01_ai_researcher.md", "02": "analysis_02_ai_scientist_v2.md",
    "03": "analysis_03_aris.md", "04": "analysis_04_autoresearchclaw.md",
    "05": "analysis_05_deepscientist.md", "06": "analysis_06_drclaw.md",
    "07": "analysis_07_evoscientist.md",
}
# 官方分的取值键（与 evaluation_metrics_report.OFFICIAL_KEY 一致）
OFFICIAL_KEY = {"arc": "score", "mc": "score", "babylm": "perplexity",
                "psydef": "psydefdetect_score", "tdc": "main_score"}
SOURCE_FIELDS = ("score_source", "source", "official_metric_implemented")


def fmt(value, digits=4):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if value != 0 and abs(value) < 1e-3:
            return f"{value:.2e}"
        return f"{value:.{digits}g}"
    return str(value)


def find_cell_score_file(row, topic):
    """定位该格官方分**实际来自哪个文件**（可能来自同格另一个 run，也可能嵌在批次目录下一层）。"""
    key = OFFICIAL_KEY.get(topic, "score")
    for name in (row.get("official_run_dir"), row.get("run_dir")):
        if not name:
            continue
        for root in RUN_ROOTS:
            if not root.is_dir():
                continue
            # 单元可能是 run 目录自身，也可能嵌在批次目录下一层（管线 iter_units 的口径）
            candidates = [root / str(name), *sorted(root.glob(f"*/{name}"))]
            for unit in candidates:
                for rel in ("workspace/score.json", "score.json"):
                    p = unit / rel
                    if not p.is_file():
                        continue
                    try:
                        d = json.loads(p.read_text(encoding="utf-8"))
                    except Exception:  # noqa: BLE001
                        continue
                    if isinstance(d, dict) and isinstance(d.get(key), (int, float)):
                        return p, d
                prov = unit / "workspace" / "score_provenance.json"
                if prov.is_file():
                    try:
                        return prov, json.loads(prov.read_text(encoding="utf-8"))
                    except Exception:  # noqa: BLE001
                        pass
    return None, None


def provenance(row, topic) -> str:
    if row.get("official_final") is None:
        return "该格无分"
    _, payload = find_cell_score_file(row, topic)
    if not isinstance(payload, dict):
        return "⚠️ 出处未标"
    for field in SOURCE_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value:
            return f"`{value}`"
    return "⚠️ 出处未标"


def judge_model_of(row) -> str | None:
    if row.get("basis_judge") != "judge_7dim":
        return None
    jd = row.get("judge_run_dir")
    for root in RUN_ROOTS:
        for rel in ("score.json", "workspace/score.json"):
            p = root / str(jd) / rel
            if p.is_file():
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                m = (d.get("evaluation") or {}).get("judge_model")
                if m:
                    return str(m)
    return None


def cell_tables(rows, topic) -> str:
    rows = sorted(rows, key=lambda r: MODEL_ORDER.index(r["model"]) if r["model"] in MODEL_ORDER else 99)
    out = ["| 模型 | 官方分 | 档位 | 官方分出处 | 轨迹 basis | 实验点 N | b0 | bT | AUP | aup_rel | UR | ED | 该格 run 数 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    CLASS_CN = {"official_scorer": "官方", "framework_self_reported": "**框架自报**",
                "manual_record": "手工记录", "none": "—", "unlabeled": "⚠️未标"}
    for r in rows:
        basis = {"trace_metric": "trace_metric（真实指标）",
                 "judge_ordinal": "judge_ordinal（序数⚠️）",
                 "none": "none（无值）"}.get(r["basis_trajectory"], r["basis_trajectory"])
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r["model"], fmt(r.get("official_final")),
            CLASS_CN.get(r.get("basis_official"), r.get("basis_official") or "—"),
            provenance(r, topic), basis,
            r.get("n_points") if r.get("n_points") is not None else "—",
            fmt(r.get("b0")), fmt(r.get("bT")), fmt(r.get("aup")), fmt(r.get("aup_rel")),
            fmt(r.get("ur")), fmt(r.get("ed")), r.get("n_runs_in_cell")))
    out += ["", "| 模型 | PQ | PEA | ER | OU | ECC | SC | CC | 判官 run | 判官模型 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        dims = " | ".join(fmt(r.get(k)) for k in ("pq", "pea", "er", "ou", "ecc", "sc", "cc"))
        out.append(f"| {r['model']} | {dims} | {r.get('judge_run_dir') or '—'} | {judge_model_of(r) or '—'} |")
    return "\n".join(out)


def footnotes(rows) -> list[str]:
    notes = []
    if any(r["topic"] == "babylm" for r in rows):
        notes.append("BabyLM 的分**一律是框架自报**（官方评分器本身就是读 trace 取最小有限值），"
                     "`basis_official = framework_self_reported`，**不可宣称官方**；"
                     "且 BabyLM 锚点 `status: pending` → **b0/bT 为 `null`**（原始尺度见 `b0_raw`/`bT_raw`）。")
    if any(r.get("basis_official") == "framework_self_reported" for r in rows):
        notes.append("`档位=框架自报` 的格子：管线在 `score.json` 没给分时按官方评分器**同一条规则**"
                     "回退到 trace，故有值但档位低 —— 见 `docs/evaluation_metrics.md` §8.9。")
    if any(str(r.get("basis_judge", "")).startswith("judge_7dim_substituted") for r in rows):
        notes.append("有格子的判官分**用了替身产物**（`basis_judge` 标 `judge_7dim_substituted(...)`）—— "
                     "与四件产物齐全的判官分**不可直接并列**。")
    if any(r.get("basis_trajectory") == "judge_ordinal" for r in rows):
        notes.append("`judge_ordinal` 是**裁判序数**，不是性能测量（`is_performance_measurement: false`），跨 topic 比大小无效。")
    if any(r["basis_ed"] == "unavailable" for r in rows):
        notes.append("`ED = —` 分两种：未跑（`basis_ed: not_run`）与**结构性不可算**（`unavailable`：实验点没有 approach 描述）。")
    if any(r.get("official_final") is not None and r.get("flat_trajectory") for r in rows):
        notes.append("`flat_trajectory` 为真表示该 run 全程无提升（AUP = 0，是**字面意义**的 0，不是缺值）。")
    models = sorted({judge_model_of(r) for r in rows if judge_model_of(r)})
    if models:
        notes.append("判官模型：" + "、".join(f"`{m}`" for m in models) + "（换模型等于换打分者；跨批比较前先看该字段）。")
    return notes


def build_block(fw: str, topic: str, rows) -> str:
    return "\n".join([
        f"<!-- METRICS-BLOCK:{fw}:{topic} -->",
        "",
        f"> 以下数字由 `automation/scripts/fill_metrics_blocks.py` 从 `analysis/evaluation_metrics.json` "
        f"统一生成（请勿手改；要改口径请改管线后重跑本脚本）。",
        "",
        f"**{TOPIC_TITLE.get(topic, topic)}**",
        "",
        cell_tables(rows, topic),
        "",
        *[f"- {n}" for n in footnotes(rows)],
        "",
        f"<!-- /METRICS-BLOCK:{fw}:{topic} -->",
    ])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 12 指标块统一填进框架报告")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    rows = json.loads(REPORT.read_text(encoding="utf-8"))["rows"]
    by: dict[tuple[str, str], list] = {}
    for r in rows:
        by.setdefault((r["framework"], r["topic"]), []).append(r)

    placed = replaced = stale = 0
    for fw, name in sorted(REPORTS.items()):
        path = ANALYSIS_DIR / name
        if not path.is_file():
            print(f"[skip] 报告还没写出来: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        for topic in TOPIC_TITLE:
            key = (fw, topic)
            if key not in by:
                continue
            block = build_block(fw, topic, by[key])
            block_re = re.compile(
                rf"<!-- METRICS-BLOCK:{fw}:{topic} -->.*?<!-- /METRICS-BLOCK:{fw}:{topic} -->",
                re.S)
            placeholder = f"<!-- METRICS:{fw}:{topic} -->"
            if block_re.search(text):
                new = block_re.sub(lambda m: block, text, count=1)
                if new != text:
                    replaced += 1
                else:
                    stale += 1
                text = new
            elif placeholder in text:
                text = text.replace(placeholder, block, 1)
                placed += 1
            else:
                print(f"[warn] {name} 里没有 {fw}:{topic} 的占位，也没块 —— 跳过")
        if not args.check:
            path.write_text(text, encoding="utf-8")
    print(f"新填入 {placed} 个 / 刷新 {replaced} 个 / 未变 {stale} 个"
          + ("（--check，未写盘）" if args.check else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

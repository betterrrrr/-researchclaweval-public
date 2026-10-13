#!/usr/bin/env python3
"""7 框架 × 12 指标：出图（热力图 / 分面柱状 / 雷达）。

## 口径（图里也会印出来）

- **数据源只有一个**：`analysis/evaluation_metrics.json`（与 7 份报告、汇总表同源）。
- **聚合用中位数**，不是均值 —— 这就是"别让某一次极大影响整体"的解法：
  一个 `AUP=1` 或 `bT=0` 的离群格不会把该框架的柱子抬起来/压下去。
  均值一并写进 CSV（`mean` 列）便于对照，图上只用 `median`。
- **不再额外归一化**：这 12 项本身已在 [0,1]（b0/bT 由锚点归一、AUP/UR/ED 与判官七维按构造如此），
  再做一次 min-max 只会引入"相对尺度"问题（加一个框架全表都变）。
- **缺失不补**：BabyLM 的 b0/bT 因锚点 `pending` 恒为 null；8 格无判官分。缺失格在图上留白/灰，
  并标出该格实际参与聚合的格数 `n/N`。
- **两条解读边界**：判官七维是**语义评分**（不是性能测量）；`CC` 只在框架内可比。

用法：
    python plot_12dim.py
"""

from __future__ import annotations

import os

import csv
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

REPO = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2]))
REPORT = REPO / "analysis" / "evaluation_metrics.json"
OUTDIR = REPO / "analysis" / "figures"

FW = {"01": "AI-Researcher", "02": "AI-Scientist-v2", "03": "ARIS", "04": "AutoResearchClaw",
      "05": "DeepScientist", "06": "DrClaw", "07": "EvoScientist"}
ORDER = ["01", "02", "03", "04", "05", "06", "07"]
# (字段, 中文名, 类别) —— 类别用于图上配色与脚注
DIMS = [
    ("b0", "b0 初始性能", "traj"), ("bT", "bT 最终性能", "traj"),
    ("aup", "AUP 进展面积", "traj"), ("ur", "UR 突破率", "traj"),
    ("ed", "ED 探索多样性", "traj"),
    ("pq", "PQ 计划质量", "judge"), ("pea", "PEA 计划-执行一致", "judge"),
    ("er", "ER 执行稳健", "judge"), ("ou", "OU 观察利用", "judge"),
    ("ecc", "ECC 证据-结论闭合", "judge"), ("sc", "SC 状态一致", "judge"),
    ("cc", "CC 合约完整", "judge"),
]
COLORS = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#DA8BC3"]


def load():
    rows = json.loads(REPORT.read_text(encoding="utf-8"))["rows"]
    med = {fw: {} for fw in ORDER}          # fw -> dim -> median
    n = {fw: {} for fw in ORDER}            # fw -> dim -> (有值格数, 总格数)
    mean = {fw: {} for fw in ORDER}
    for fw in ORDER:
        sub = [r for r in rows if r["framework"] == fw]
        for field, _, _ in DIMS:
            vals = [r[field] for r in sub if isinstance(r.get(field), (int, float))]
            med[fw][field] = statistics.median(vals) if vals else None
            mean[fw][field] = statistics.fmean(vals) if vals else None
            n[fw][field] = (len(vals), len(sub))
    return rows, med, mean, n


def fig_heatmap(med, n, mode="median"):
    fields = [d[0] for d in DIMS]
    labels = [d[1] for d in DIMS]
    M = np.full((len(ORDER), len(fields)), np.nan)
    for i, fw in enumerate(ORDER):
        for j, f in enumerate(fields):
            if med[fw][f] is not None:
                M[i, j] = med[fw][f]
    fig, ax = plt.subplots(figsize=(15, 5.2))
    cmap = plt.get_cmap("RdYlGn").copy()
    cmap.set_bad("#e8e8e8")
    im = ax.imshow(M, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(fields)), labels, rotation=38, ha="right", fontsize=10)
    ax.set_yticks(range(len(ORDER)), [f"{fw} {FW[fw]}" for fw in ORDER], fontsize=11)
    for i, fw in enumerate(ORDER):
        for j, f in enumerate(fields):
            have, tot = n[fw][f]
            if med[fw][f] is None:
                ax.text(j, i, "—", ha="center", va="center", color="#999", fontsize=11)
            else:
                ax.text(j, i, f"{med[fw][f]:.2f}", ha="center", va="center", fontsize=10,
                        color="black")
                ax.text(j, i + 0.30, f"n={have}", ha="center", va="center", fontsize=7, color="#444")
    # 视觉分隔：轨迹类 5 项 | 判官类 7 项
    ax.axvline(4.5, color="#333", lw=2)
    ax.text(2.0, -0.95, "轨迹类 5 项（性能尺度）", ha="center", fontsize=10, color="#333")
    ax.text(8.5, -0.95, "判官类 7 项（语义评分，非性能测量）", ha="center", fontsize=10, color="#333")
    zh = "中位数" if mode == "median" else "均值（⚠️ 会被离群格拉动，见脚注）"
    ax.set_title(f"7 框架 × 12 指标（每格 = 该框架 20 个格子的**{zh}**，全部已在 [0,1]；"
                 "n = 参与聚合的格数，共 20）", fontsize=13, pad=26)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.015, label="中位数（越大越好，已统一方向）")
    fig.tight_layout()
    p = OUTDIR / ("fig_12dim_heatmap_" + mode + ".png")
    fig.savefig(p, dpi=170)
    plt.close(fig)
    return p


def fig_facets(med, n, mode="median"):
    fig, axes = plt.subplots(2, 4, figsize=(19, 8), sharey=True)
    fields = [d[0] for d in DIMS]
    labels = [d[0] for d in DIMS]
    colors = ["#4C72B0"] * 5 + ["#C44E52"] * 7
    for k, fw in enumerate(ORDER):
        ax = axes.flat[k]
        vals = [med[fw][f] if med[fw][f] is not None else 0 for f in fields]
        miss = [med[fw][f] is None for f in fields]
        bars = ax.bar(range(len(fields)), vals, color=colors, edgecolor="black", lw=0.4)
        for i, m in enumerate(miss):
            if m:
                bars[i].set_color("#dddddd")
                bars[i].set_hatch("///")
        for i, v in enumerate(vals):
            have, _ = n[fw][fields[i]]
            ax.text(i, (v if v else 0) + 0.03, f"{have}" if not miss[i] else "", ha="center",
                    fontsize=6.4, color="#333")
        ax.set_title(f"{fw} {FW[fw]}", fontsize=12)
        ax.set_xticks(range(len(fields)), labels, rotation=60, fontsize=8)
        ax.set_ylim(0, 1.12)
        ax.grid(axis="y", alpha=0.25)
        if k % 4 == 0:
            ax.set_ylabel("中位数（[0,1]）", fontsize=10)
    ax = axes.flat[7]
    ax.axis("off")
    ax.legend(handles=[Patch(facecolor="#4C72B0", label="轨迹类 5 项（b0/bT 由锚点归一，AUP/UR/ED 按构造）"),
                       Patch(facecolor="#C44E52", label="判官类 7 项（语义评分，不是性能测量；CC 仅框架内可比）"),
                       Patch(facecolor="#dddddd", hatch="///", label="无值（BabyLM 的 b0/bT 因锚点 pending 恒 null；8 格无判官分）")],
              loc="upper left", fontsize=10, frameon=False)
    ax.text(0, 0.45, "柱上方数字 = 参与聚合的格数（满值 20）\n"
                     "缺失格不参与聚合、不补零 —— 灰色斜纹表示该列没有值",
            fontsize=10, color="#333")
    fig.suptitle(f"7 框架 × 12 指标：分面柱状（{'中位数，抗单点极值' if mode == 'median' else '均值，对照用 —— 受离群格影响'}）",
                 fontsize=15, y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    p = OUTDIR / ("fig_12dim_facets_" + mode + ".png")
    fig.savefig(p, dpi=170)
    plt.close(fig)
    return p


def fig_radar(med, mode="median"):
    fields = [d[0] for d in DIMS]
    angles = np.linspace(0, 2 * np.pi, len(fields), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(9.5, 9), subplot_kw=dict(polar=True))
    for k, fw in enumerate(ORDER):
        vals = [med[fw][f] if med[fw][f] is not None else np.nan for f in fields]
        vals = vals + vals[:1]
        ax.plot(angles, vals, color=COLORS[k], lw=2, label=f"{fw} {FW[fw]}")
        ax.fill(angles, vals, color=COLORS[k], alpha=0.06)
    ax.set_xticks(angles[:-1], fields, fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0], ["0.25", "0.50", "0.75", "1.00"], fontsize=8, color="#666")
    ax.set_title(f"7 框架 × 12 指标（{'中位数' if mode == 'median' else '均值'}）—— 轨迹类在左半、判官类在右半\n"
                 "⚠️ 两条读法：BabyLM 的 b0/bT 为 null 故该框架缺两角；判官类是语义评分，不与性能项等权解读",
                 fontsize=12.5, pad=26)
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.10), fontsize=10)
    fig.tight_layout()
    p = OUTDIR / ("fig_12dim_radar_" + mode + ".png")
    fig.savefig(p, dpi=170)
    plt.close(fig)
    return p


def dump_csv(med, mean, n):
    p = OUTDIR / "12dim_by_framework.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["framework", "framework_name", "indicator", "category",
                    "median", "mean", "n_cells", "n_total"])
        for fw in ORDER:
            for field, label, cat in DIMS:
                have, tot = n[fw][field]
                w.writerow([fw, FW[fw], field, cat,
                            "" if med[fw][field] is None else round(med[fw][field], 6),
                            "" if mean[fw][field] is None else round(mean[fw][field], 6),
                            have, tot])
    return p


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    _, med, mean, n = load()
    paths = []
    for mode, table in (("median", med), ("mean", mean)):
        paths += [fig_heatmap(table, n, mode), fig_facets(table, n, mode), fig_radar(table, mode)]
    paths.append(dump_csv(med, mean, n))
    for p in paths:
        print("写出:", p, f"({p.stat().st_size} B)")
    # 中位数 vs 均值：让"单点极值"的影响可见
    print("\n中位数与均值差异最大的 8 处（均值被离群格拉动的证据）：")
    diffs = []
    for fw in ORDER:
        for field, _, _ in DIMS:
            if med[fw][field] is None:
                continue
            diffs.append((abs(mean[fw][field] - med[fw][field]), fw, field,
                          med[fw][field], mean[fw][field], n[fw][field][0]))
    for d, fw, field, m, mu, cnt in sorted(diffs, reverse=True)[:8]:
        print(f"   {fw} {field:4s} 中位数 {m:.3f} vs 均值 {mu:.3f}  (差 {d:+.3f}, n={cnt})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

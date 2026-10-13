#!/usr/bin/env python3
"""一维度一图：12 张，每张横向排 7 个框架的均值 + 逐格原始值点。

与 plot_12dim_per_framework.py 互补：那张是「一框架一图」，这张是按维度转置。
聚合用均值（用户指定），分母只算该维在该框架有值的格，缺失不插补。
字体与数据加载复用 plot_12dim_per_framework，避免两套口径漂移。
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

from pathlib import Path
import statistics
import warnings

import matplotlib.pyplot as plt

from plot_12dim_per_framework import (  # noqa: E402  复用已验证的字体安装与数据口径
    DIMS,
    FW,
    JUDGE_TINT,
    ORDER,
    build,
    load_rows,
)

OUTDIR = Path(__file__).resolve().parents[2] / "analysis" / "figures"

GRID = (0.25, 0.50, 0.75)


def plot_dimension(key: str, label: str, cat: str, vals, grand: float | None,
                   out: Path) -> None:
    """vals[fw][key] -> [原始逐格值...]"""
    pool = []
    for fw in ORDER:
        v = vals[fw][key]
        if v:
            pool.append((statistics.fmean(v), fw, v))
    pool.sort(key=lambda t: t[0])  # 值小的在下，值大的在上

    fig, ax = plt.subplots(figsize=(9.4, 6.2))
    tint = "#c05621" if cat == "traj" else "#2b6cb0"
    ys = list(range(len(pool)))

    for y, (mean_v, fw, raw) in zip(ys, pool):
        ax.barh(y, mean_v, height=0.52, color=tint, alpha=0.9, zorder=3)
        ax.text(mean_v + 0.012, y, f"{mean_v:.3f}   n={len(raw)}",
                va="center", ha="left", fontsize=9.6, color="#1a202c", zorder=5)
        # 逐格原始值：判官维会看到它们叠在 0/.25/.5/.75/1 五条线上
        for v in raw:
            ax.plot([v], [y], marker="|", ms=13, mew=1.6,
                    color="#1a202c", alpha=0.7, zorder=4)

    ax.set_yticks(ys, [f"{fw}  {FW[fw]}" for _, fw, _ in pool], fontsize=10.5)
    if grand is not None:
        ax.axvline(grand, color="#718096", lw=1.4, ls="--", zorder=2)
        ax.text(grand, len(pool) - 0.32, f" 全框架均值 {grand:.3f}",
                fontsize=8.8, color="#4a5568", va="bottom", ha="left")

    for x in GRID:
        ax.axvline(x, color="#e2e8f0", lw=0.9, ls=":", zorder=0)

    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "0.25", "0.50", "0.75", "1.00"],
                  fontsize=9)
    ax.set_xlabel("指标均值（已归一化到 [0,1]，越大越好）", fontsize=10)
    kind = "轨迹类（性能尺度）" if cat == "traj" else "判官类（语义评分，非性能测量）"
    ax.set_title(f"{label}\n{kind} · 7 框架均值对比（跨 5 topic × 4 模型）",
                 fontsize=13.5, pad=14)
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)

    footnote = ("聚合=均值（分母仅计有值格，缺失不插补）；n=该框架参与聚合的格数（共 20）。"
                "深色竖线=逐格原始值。")
    if cat == "judge":
        footnote += " 本维为 5 点序数量表 {0,.25,.5,.75,1}，故落点集中。"
    fig.text(0.012, 0.014, footnote, fontsize=7.6, color="#4a5568")

    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)


def main() -> int:
    vals = build(load_rows())
    OUTDIR.mkdir(parents=True, exist_ok=True)

    missing: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for i, (key, label, cat) in enumerate(DIMS, 1):
            pool = [v for fw in ORDER for v in vals[fw][key]]
            grand = statistics.fmean(pool) if pool else None
            out = OUTDIR / f"fig_dim_{i:02d}_{key}_mean.png"
            plot_dimension(key, label, cat, vals, grand, out)
            print(f"  写出 {out}")
        for w in caught:
            if "missing from font" in str(w.message) or "Glyph" in str(w.message):
                missing.append(str(w.message))

    print(f"缺字形告警 {len(missing)} 条")
    for m in missing[:5]:
        print("   ", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""12 维雷达图（均值口径）。

产出两套，全部是雷达图：
  1. fig_radar_all7_mean.png           —— 7 框架叠在一张 12 轴雷达上（总览）
  2. fig_radar_fw{01..07}_mean.png      —— 一框架一张，本框架 vs 全框架均值

字体与数据加载复用 plot_12dim_per_framework，避免两套口径漂移。
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

from pathlib import Path
import statistics
import warnings

import numpy as np
import matplotlib.pyplot as plt

from plot_12dim_per_framework import DIMS, FW, ORDER, build, load_rows  # noqa: E402

OUTDIR = Path(__file__).resolve().parents[2] / "analysis" / "figures"

# 7 框架配色（定性色板，色盲较友好，顺序固定不随排序变）
COLORS = {
    "01": "#1f77b4",
    "02": "#ff7f0e",
    "03": "#2ca02c",
    "04": "#d62728",
    "05": "#9467bd",
    "06": "#8c564b",
    "07": "#17becf",
}
SHORT = {
    "b0": "b0\n起点",
    "bT": "bT\n终点",
    "aup": "AUP\n曲线面积",
    "ur": "UR\n提升率",
    "ed": "ED\n有效多样性",
    "pq": "PQ\n问题质量",
    "pea": "PEA\n计划充分",
    "er": "ER\n实验严谨",
    "ou": "OU\n产出可用",
    "ecc": "ECC\n外部校验",
    "sc": "SC\n科学贡献",
    "cc": "CC\n结论一致",
}
N_TRAJ = 5  # 前 5 维为轨迹类，其余判官类


def mean_of(vals_fw: dict) -> dict[str, float | None]:
    return {k: (statistics.fmean(v) if v else None) for k, v in vals_fw.items()}


def setup_axes(ax, labels: list[str], n: int) -> np.ndarray:
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ax.set_theta_zero_location("N")   # 第一维在正上方
    ax.set_theta_direction(-1)        # 顺时针
    ax.set_xticks(theta)
    ax.set_xticklabels(labels, fontsize=8.6)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.25, 0.50, 0.75, 1.00], ["0.25", "0.50", "0.75", "1.00"],
                  fontsize=7.4, color="#718096")
    ax.tick_params(axis="x", pad=6)
    ax.grid(color="#cbd5e0", lw=0.8, alpha=0.85)
    ax.spines["polar"].set_color("#a0aec0")
    return theta


def close(vals: list[float], theta: np.ndarray):
    """闭合多边形（首点补到末尾）。"""
    return np.append(theta, theta[0]), vals + [vals[0]]


def plot_all7(fwmean: dict[str, dict], grand: dict, out: Path) -> None:
    n = len(DIMS)
    labels = [SHORT[k] for k, _, _ in DIMS]
    fig, ax = plt.subplots(figsize=(10.4, 9.4), subplot_kw=dict(polar=True))
    theta = setup_axes(ax, labels, n)

    # 全框架均值作底
    gv = [grand[k] for k, _, _ in DIMS]
    gt, gvv = close([v if v is not None else 0.0 for v in gv], theta)
    ax.plot(gt, gvv, color="#4a5568", lw=1.6, ls="--", zorder=3,
            label="全框架均值")
    ax.fill(gt, gvv, color="#a0aec0", alpha=0.16, zorder=2)

    for fw in ORDER:
        vals = [fwmean[fw][k] for k, _, _ in DIMS]
        if any(v is None for v in vals):
            continue
        t, v = close(vals, theta)
        ax.plot(t, v, color=COLORS[fw], lw=2.0, zorder=4,
                label=f"{fw} {FW[fw]}")
        ax.fill(t, v, color=COLORS[fw], alpha=0.09, zorder=1)

    # 轨迹类 / 判官类 分界：在 5/12 与 6/12 圈处画两条辐条
    for i in (N_TRAJ - 0.5,):
        ang = 2 * np.pi * i / n
        ax.plot([ang, ang], [0, 1.0], color="#4a5568", lw=1.2, ls="--", zorder=5)

    ax.set_title("7 框架 × 12 维雷达（均值）\n虚线辐条左侧 5 维=轨迹类，右侧 7 维=判官类（语义评分，非性能测量）",
                 fontsize=13, pad=26)
    ax.legend(loc="upper right", bbox_to_anchor=(1.24, 1.10), fontsize=9.5,
              framealpha=0.95)
    fig.text(0.012, 0.014,
             "聚合=均值（分母仅计有值格，缺失不插补）；数值已全部落在 [0,1]，未再作维内缩放。"
             "判官维为 5 点序数量表 {0,.25,.5,.75,1}，故多边形常压在少数几条半径上。",
             fontsize=7.6, color="#4a5568")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)


def plot_one(fw: str, fwmean: dict, grand: dict, out: Path) -> None:
    n = len(DIMS)
    labels = [SHORT[k] for k, _, _ in DIMS]
    mine = [fwmean[fw][k] for k, _, _ in DIMS]
    ref = [grand[k] for k, _, _ in DIMS]

    fig, ax = plt.subplots(figsize=(9.6, 8.8), subplot_kw=dict(polar=True))
    theta = setup_axes(ax, labels, n)

    t, r = close([v if v is not None else 0.0 for v in ref], theta)
    ax.plot(t, r, color="#4a5568", lw=1.6, ls="--", zorder=3, label="全框架均值")
    ax.fill(t, r, color="#a0aec0", alpha=0.18, zorder=1)

    if any(v is None for v in mine):
        decorated_cov = sum(1 for v in mine if v is not None)
        ax.set_title(f"{fw}  {FW[fw]}   —   12 维雷达（均值，仅 {decorated_cov}/12 维有值）",
                     fontsize=13.5, pad=26)
        fig.text(0.012, 0.014,
                 "本框架存在无值维度，多边形不完整：缺失维按 0 绘制，勿据此比较面积。",
                 fontsize=8.2, color="#c53030")
        ax.legend(loc="upper right", bbox_to_anchor=(1.22, 1.10), fontsize=10)
        fig.tight_layout(rect=(0, 0.035, 1, 1))
        fig.savefig(out, dpi=150, facecolor="white")
        plt.close(fig)
        return

    t, v = close(mine, theta)
    ax.plot(t, v, color=COLORS[fw], lw=2.3, zorder=4, label=f"{fw} {FW[fw]}")
    ax.fill(t, v, color=COLORS[fw], alpha=0.20, zorder=2)

    # 顶点标数值，并标与全框架均值的差
    for ang, val, ref_v in zip(theta, mine, ref):
        ax.annotate(f"{val:.2f}", xy=(ang, val), fontsize=8.2, zorder=6,
                    color="#1a202c", ha="center", va="center",
                    xytext=(ang, min(val + 0.075, 1.09)),
                    textcoords="data")

    for i in (N_TRAJ - 0.5,):
        ang = 2 * np.pi * i / n
        ax.plot([ang, ang], [0, 1.0], color="#4a5568", lw=1.2, ls="--", zorder=5)

    deltas = [m - r for m, r in zip(mine, ref)]
    ax.set_title(f"{fw}  {FW[fw]}   —   12 维雷达（均值）\n"
                 f"相对全框架均值：高于 {sum(1 for d in deltas if d > 0.005)} 维，"
                 f"低于 {sum(1 for d in deltas if d < -0.005)} 维",
                 fontsize=13.5, pad=26)
    ax.legend(loc="upper right", bbox_to_anchor=(1.22, 1.10), fontsize=10)
    fig.text(0.012, 0.014,
             "聚合=均值（分母仅计有值格，缺失不插补）；顶点数字为该维均值。"
             "虚线辐条左侧 5 维=轨迹类，右侧 7 维=判官类（语义评分，非性能测量）。",
             fontsize=7.6, color="#4a5568")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)


def main() -> int:
    vals = build(load_rows())
    fwmean = {fw: mean_of(vals[fw]) for fw in ORDER}
    grand = {}
    for k, _, _ in DIMS:
        pool = [v for fw in ORDER for v in vals[fw][k]]
        grand[k] = statistics.fmean(pool) if pool else None

    OUTDIR.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = OUTDIR / "fig_radar_all7_mean.png"
        plot_all7(fwmean, grand, out)
        print(f"  写出 {out}")
        for fw in ORDER:
            out = OUTDIR / f"fig_radar_fw{fw}_mean.png"
            plot_one(fw, fwmean, grand, out)
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

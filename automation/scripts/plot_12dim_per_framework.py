#!/usr/bin/env python3
"""一框架一图：12 维均值棒图（本框架均值 vs 全框架均值），点层叠原始逐格值。

口径
----
* 聚合用**均值**（用户指定）。分母只算该维在该框架**有值**的格，缺失不插补。
* 12 维本身已全部落在 [0,1]（b0/bT 靠锚点定标，AUP/UR/ED/判官维靠构造），
  不再做维内 min-max —— 那会强行让每维最好的框架=1.0，破坏绝对可比性。
* 判官 7 维是 5 点序数量表 {0,.25,.5,.75,1}，所以均值/中位数会大量落在同一格点上，
  这是量表本身的性质，不是 bug；图上的散点把这点直接画出来。
"""
from __future__ import annotations

import csv
import json
import statistics
import warnings
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

# --- 中文字体：必须显式注册，matplotlib 默认字体无 CJK 字形 -------------------
from matplotlib import font_manager, pyplot as plt

_CJK_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
)


def install_cjk_font() -> str:
    """注册第一个可用的 CJK 字体，返回 family 名。失败则抛错（不静默降级）。"""
    for path in _CJK_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            font_manager.fontManager.addfont(path)
            family = font_manager.FontProperties(fname=path).get_name()
        except Exception:
            continue
        plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["axes.unicode_minus"] = False  # 负号用 ASCII，避免缺字形
        return family
    raise RuntimeError("找不到可用 CJK 字体；候选：" + ", ".join(_CJK_CANDIDATES))


FONT_FAMILY = install_cjk_font()

ROOT = Path(__file__).resolve().parents[2]
METRICS = ROOT / "analysis" / "evaluation_metrics.json"
OUTDIR = ROOT / "analysis" / "figures"

FW = {
    "01": "AI-Researcher",
    "02": "AI-Scientist-v2",
    "03": "ARIS",
    "04": "AutoResearchClaw",
    "05": "DeepScientist",
    "06": "DrClaw",
    "07": "EvoScientist",
}
ORDER = sorted(FW)

# (field, 中文标签, 类别)
DIMS = [
    ("b0", "b0 起点表现", "traj"),
    ("bT", "bT 终点表现", "traj"),
    ("aup", "AUP 曲线下面积", "traj"),
    ("ur", "UR 提升率", "traj"),
    ("ed", "ED 有效多样性", "traj"),
    ("pq", "PQ 问题质量", "judge"),
    ("pea", "PEA 计划充分性", "judge"),
    ("er", "ER 实验严谨性", "judge"),
    ("ou", "OU 产出可用性", "judge"),
    ("ecc", "ECC 外部校验", "judge"),
    ("sc", "SC 科学贡献", "judge"),
    ("cc", "CC 结论一致性", "judge"),
]

# b0/bT/AUP/UR 是从轨迹本身算出来的，所以它们的含义取决于轨迹是"怎么测的"。
# docs/evaluation_metrics.md §3：judge_ordinal 是裁判的序数排序映射，
# 是**非性能测量**，不可与性能尺度并列解读。因此这四维的均值只统计
# basis_trajectory == "trace_metric" 的行。
#
# ED 与七个判官维由判官产出，与轨迹 basis 无关，照旧合并统计。
BASIS_SENSITIVE = {"b0", "bT", "aup", "ur"}

JUDGE_TINT = "#2b6cb0"
TRAJ_TINT = "#c05621"
REF_TINT = "#a0aec0"


def load_rows() -> list[dict]:
    data = json.loads(METRICS.read_text())
    return data["rows"] if isinstance(data, dict) and "rows" in data else data


def field_of(row: dict, key: str):
    v = row.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    m = row.get("metrics")
    if isinstance(m, dict) and isinstance(m.get(key), (int, float)):
        return float(m[key])
    return None


def build(rows: list[dict]):
    """vals[fw][field] = [原始逐格值...]；framework 从行里的 framework 字段取。

    BASIS_SENSITIVE 的维度只收 trace_metric 行；其余行计入 excluded[field]。
    """
    vals: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    excluded: dict[str, int] = defaultdict(int)
    for row in rows:
        fw = str(row.get("framework", "")).strip()
        if fw not in FW:
            continue
        basis = row.get("basis_trajectory")
        for key, _, _ in DIMS:
            if key in BASIS_SENSITIVE and basis != "trace_metric":
                if field_of(row, key) is not None:
                    excluded[key] += 1
                continue
            v = field_of(row, key)
            if v is not None:
                vals[fw][key].append(v)
    return vals, excluded


def plot_framework(fw: str, vals, grand: dict[str, float | None], out: Path) -> None:
    labels = [lab for _, lab, _ in DIMS]
    mine = [statistics.fmean(vals[fw][k]) if vals[fw][k] else None for k, _, _ in DIMS]
    ns = [len(vals[fw][k]) for k, _, _ in DIMS]
    ref = [grand[k] for k, _, _ in DIMS]

    n = len(DIMS)
    fig, ax = plt.subplots(figsize=(11.2, 7.4))
    ys = list(range(n))[::-1]  # 第一维画在最上面

    h = 0.34
    for i, (y, key, cat) in enumerate(zip(ys, [k for k, _, _ in DIMS], [c for _, _, c in DIMS])):
        mine_v, ref_v = mine[i], ref[i]
        tint = TRAJ_TINT if cat == "traj" else JUDGE_TINT
        if mine_v is not None:
            ax.barh(y + h / 2, mine_v, height=h, color=tint, alpha=0.92,
                    label="本框架均值" if i == 0 else None, zorder=3)
            ax.text(mine_v + 0.012, y + h / 2, f"{mine_v:.3f}  (n={ns[i]})",
                    va="center", ha="left", fontsize=8.6, color="#1a202c", zorder=5)
        else:
            ax.text(0.012, y + h / 2, "无值", va="center", ha="left",
                    fontsize=8.6, color="#a0aec0", style="italic", zorder=5)
        if ref_v is not None:
            ax.barh(y - h / 2, ref_v, height=h, color=REF_TINT, alpha=0.95,
                    label="全框架均值" if i == 0 else None, zorder=3)
            ax.text(ref_v + 0.012, y - h / 2, f"{ref_v:.3f}", va="center",
                    ha="left", fontsize=8.2, color="#4a5568", zorder=5)

        # 点层叠：把该维逐格原始值画出来，展示序数量表的离散性
        for v in vals[fw][key]:
            ax.plot([v], [y + h / 2], marker="|", ms=7, mew=1.5,
                    color="#1a202c", alpha=0.75, zorder=4)

    ax.set_yticks(ys, labels, fontsize=10)
    ax.set_xlim(0, 1.24)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0],
                  ["0", "0.25", "0.50", "0.75", "1.00"], fontsize=9)
    ax.set_xlabel("指标值（已归一化到 [0,1]；判官 7 维为语义评分，非性能测量）", fontsize=10)
    ax.grid(axis="x", ls=":", color="#cbd5e0", alpha=0.8, zorder=0)
    ax.set_axisbelow(True)

    # 轨迹类 / 判官类 分隔线
    n_traj = sum(1 for _, _, c in DIMS if c == "traj")
    ax.axhline(ys[n_traj] + 0.5, color="#4a5568", lw=1.6, ls="--", zorder=2)
    ax.text(1.235, ys[n_traj] + 0.62, "▲ 轨迹类 5 项", ha="right", va="bottom",
            fontsize=8.5, color=TRAJ_TINT)
    ax.text(1.235, ys[n_traj] + 0.38, "▼ 判官类 7 项（语义评分）", ha="right", va="top",
            fontsize=8.5, color=JUDGE_TINT)

    ax.set_title(f"{fw}  {FW[fw]}   —   12 维指标均值（跨 5 topic × 4 模型，共 20 格）",
                 fontsize=14, pad=16)
    ax.legend(loc="lower right", fontsize=9.5, frameon=True, framealpha=0.95)

    covered = sum(1 for v in mine if v is not None)
    fig.text(0.012, 0.012,
             f"聚合=均值（分母仅计有值格，缺失不插补）；本框架 {covered}/12 维有值。"
             f"深色竖线=该维逐格原始值，可见判官维取值为 5 点序数量表 {{0,.25,.5,.75,1}}，"
             f"故多框架落点相同属量表性质。",
             fontsize=7.6, color="#4a5568")

    fig.tight_layout(rect=(0, 0.028, 1, 1))
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)


def main() -> int:
    rows = load_rows()
    vals, excluded = build(rows)
    if excluded:
        print("  按 basis 过滤（只收 trace_metric 行）：")
        for key, _, _ in DIMS:
            if excluded.get(key):
                print(f"    {key:<5} 排除 {excluded[key]:>3} 行 judge_ordinal 值")
    grand = {}
    for key, _, _ in DIMS:
        pool = [v for fw in ORDER for v in vals[fw][key]]
        grand[key] = statistics.fmean(pool) if pool else None

    OUTDIR.mkdir(parents=True, exist_ok=True)
    missing = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for fw in ORDER:
            out = OUTDIR / f"fig_12dim_framework_{fw}_mean.png"
            plot_framework(fw, vals, grand, out)
            print(f"  写出 {out}")
        for w in caught:
            if "missing from font" in str(w.message) or "Glyph" in str(w.message):
                missing.append(str(w.message))
    print(f"字体: {FONT_FAMILY}；缺字形告警 {len(missing)} 条")
    for m in missing[:5]:
        print("   ", m)

    # 附一张均值数表，便于引用
    csv_path = OUTDIR / "12dim_by_framework_mean.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["framework", "framework_name", "indicator", "category",
                    "mean", "median", "n_cells", "n_total", "grand_mean",
                    "basis_filter", "n_excluded"])
        for fw in ORDER:
            for key, lab, cat in DIMS:
                v = vals[fw][key]
                w.writerow([fw, FW[fw], key, cat,
                            f"{statistics.fmean(v):.6f}" if v else "",
                            f"{statistics.median(v):.6f}" if v else "",
                            len(v), 20,
                            f"{grand[key]:.6f}" if grand[key] is not None else "",
                            "trace_metric_only" if key in BASIS_SENSITIVE else "all",
                            excluded.get(key, 0)])
    print(f"  写出 {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""轨迹指标 b0 / bT / AUP / UR —— 确定性部分（不调用任何 LLM）。

权威定义见 `docs/evaluation_metrics.md`。要点：
- 一条轨迹只认**一个同族字段**，保证 best-so-far 曲线内部可比；
- 方向统一为「越大越好」后计算；
- b0/bT 用**固定锚点**归一化到 [0,1]（锚点在 `metric_anchors.json`）；
- 锚点 `status=pending` 时**直接报错退出**，绝不静默用假值。

ED 的语义判重与 arc 的序数评估在 `trajectory_judge.py`（需要 LLM，单独隔离）。
"""

from __future__ import annotations

import os

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANCHORS_PATH = Path(__file__).resolve().parent / "metric_anchors.json"
DEFAULT_RUNS_ROOT = Path(os.environ.get("REAL_EVAL_RUN_ROOT", Path(__file__).resolve().parents[2] / "real_eval" / "runs"))

# 只收**同族**字段（同一 metric 语义）。顺序即优先级；依据是 814 份 trace 的实测覆盖率。
FIELD_WHITELIST: dict[str, tuple[str, ...]] = {
    "tdc": (
        "validation_metrics.macro_average_auroc",
        "macro_auroc",
        "score_summary.macro_average_auroc",
    ),
    "babylm": (
        "validation_perplexity",
        "validation_metrics.perplexity",
        "validation_metrics.validation_perplexity",
        "best_validation_perplexity",
    ),
    "psydef": (
        "score_summary.psydefdetect_score",
        "psydefdetect_score",
        "score_summary.macro_f1_positive_1_8",
        "macro_f1_positive_1_8",
        "official_score.psydefdetect_score",
        # 裸键：01/02 交付包的 trace 直接写 `{"id":..., "score":...}`。
        # 2026-10-12 逐位验证：21 个"仅裸键命中"的单元里，每一个都有一项值
        # **与官方 psydefdetect_score 15 位小数相同**；同时命中白名单字段的 4 个单元里
        # 两者**完全相同**。放末尾 = 只在显式路径全落空时才用。
        "score",
    ),
    "mc": (
        "metrics.Reward Mean",
        "validation_reward_mean",
        "mean_validation_return",
        "validation_metrics.mean_validation_return",
        "result.reward_mean",
        # 裸键：同上，2026-10-12 验证 `reward_mean` == 官方 `score`
        # （如 07_evoscientist 的 62.672596 vs 官方 62.6725959777832）。
        "reward_mean",
    ),
    # arc 的官方指标是 adjusted_final_layer_score。实测（720 条目 / 258 份 trace）：
    # 只有 23 个条目、分布在 **5 种路径前缀**下 —— 缺任何一个前缀都会漏掉整个 run
    # （曾因此漏掉了最权威的 fullpipe run）。
    # **刻意不收** best_val_loss / best_train_loss（训练损失 != WSE 分）。
    # 也**刻意不收裸键 `score`**：2026-10-12 实测，收进来会让 `03×arc×Kimi` 拿到
    # 0.2946→0.3372 的"轨迹"，而 ARC-WBE 官方 `adjusted_final_layer_score` 量级是
    # 1e-4…0.14 —— 那是别的东西。**不要"顺手补上"**。
    "arc": (
        "adjusted_final_layer_score",
        "framework_visible_validation.adjusted_final_layer_score",
        "framework_visible_validation_result.adjusted_final_layer_score",
        "validation_metrics.adjusted_final_layer_score",
        "result.adjusted_final_layer_score",
        "official_score.adjusted_final_layer_score",
    ),
}

OFFICIAL_SCORE_KEY = {
    "arc": "score", "mc": "score", "babylm": "perplexity",
    "psydef": "psydefdetect_score", "tdc": "main_score",
}

# approach 描述字段，按实测覆盖率排序（ED 的确定性抽取部分）
APPROACH_FIELDS = (
    "hypothesis", "model_strategy", "feature_strategy", "method",
    "condition", "name", "description", "change_rationale",
)

_TOPIC_HINTS = (
    ("tdc", "tdc"), ("psydef", "psydef"), ("babylm", "babylm"),
    ("mountaincar", "mc"), ("topic2", "mc"), ("arc", "arc"),
)

# UR 的相对容差：0.1%。困惑度/AUROC 都是 6 位小数，末位抖动不该算作「真正突破」。
# 严格计数（无容差）一并保留在 improvements_strict，便于做敏感性对照。
UR_REL_TOLERANCE = 1e-3


class PendingAnchorError(RuntimeError):
    """锚点未定义 —— 必须显式补齐，不能静默用假值。"""


@dataclass
class Point:
    index: int
    raw: float
    metric_field: str
    experiment_id: str
    approach: dict[str, str] = field(default_factory=dict)
    runtime_seconds: float | None = None
    status: str | None = None

    @property
    def approach_text(self) -> str:
        return " | ".join(f"{k}={v}" for k, v in self.approach.items())


def load_anchors(path: Path | None = None) -> dict:
    path = path or ANCHORS_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_score(raw: float, anchor: dict) -> tuple[float | None, bool]:
    """按固定锚点把原始分映射到 [0,1]。返回 (值, 是否超出锚点被钳制)。

    `status=pending` 的 topic 抛 PendingAnchorError。
    """
    if anchor.get("status") != "ready":
        raise PendingAnchorError(
            f"锚点未就绪（status={anchor.get('status')!r}）：{anchor.get('source', '')}"
        )
    worst, best = anchor["worst"], anchor["best"]
    if worst is None or best is None:
        raise PendingAnchorError("锚点的 worst/best 为空")
    if worst == best:
        raise ValueError("锚点的 worst 与 best 相同，无法归一化")

    if anchor.get("scale") == "log":
        if min(raw, worst, best) <= 0:
            raise ValueError(f"log 尺度锚点要求全为正数：raw={raw} worst={worst} best={best}")
        raw, worst, best = math.log10(raw), math.log10(worst), math.log10(best)

    if anchor["direction"] == "higher_better":
        value = (raw - worst) / (best - worst)
    else:  # lower_better：raw 越小越好
        value = (worst - raw) / (worst - best)

    out_of_anchor = value < 0.0 or value > 1.0
    return max(0.0, min(1.0, value)), out_of_anchor


def dig(obj: object, dotted: str) -> object | None:
    """按点分路径取值；支持含空格的字面键（如 `metrics.Reward Mean`）。"""
    if isinstance(obj, dict) and dotted in obj:
        return obj[dotted]
    cur: object = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def scalar(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def iter_manifests(run_dir: Path) -> list[Path]:
    """一个 run 可能在外层或**内层单元**才有 manifest。

    实测：`<run>/fullrun_manifest.json` 很多 run 没有，真正的在
    `<run>/NN_<framework>_<topic>_fullrun/fullrun_manifest.json`。
    只读外层会整片漏掉（曾漏掉 EvoScientist 的 mc/psydef 共 80+ 个单元）。
    """
    outer = run_dir / "fullrun_manifest.json"
    found = [outer] if outer.is_file() else []
    found.extend(sorted(run_dir.glob("*/fullrun_manifest.json")))
    return found


def detect_topic(run_dir: Path) -> str | None:
    for manifest in iter_manifests(run_dir):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(payload, dict):
            for key in ("topic", "topic_root", "slug"):
                text = str(payload.get(key) or "").lower()
                for needle, topic in _TOPIC_HINTS:
                    if needle in text:
                        return topic
    low = str(run_dir).lower()
    for needle, topic in _TOPIC_HINTS:
        if needle in low:
            return topic
    return None


def find_trace(run_dir: Path) -> Path | None:
    direct = run_dir / "workspace" / "experiment_trace.json"
    if direct.is_file():
        return direct
    nested = sorted(run_dir.glob("*/workspace/experiment_trace.json"))
    return nested[0] if nested else None


def find_log(run_dir: Path) -> Path | None:
    for candidate in (run_dir / "logs" / "e2e.log", run_dir / "e2e.log"):
        if candidate.is_file():
            return candidate
    return None


def load_experiments(trace_path: Path) -> list[dict]:
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(payload, dict):
        return []
    experiments = payload.get("experiments")
    if not isinstance(experiments, list):
        experiments = payload.get("results")
    return [e for e in experiments if isinstance(e, dict)] if isinstance(experiments, list) else []


def extract_points(experiments: list[dict], topic: str) -> tuple[list[Point], list[dict], str | None]:
    """抽出可用实验点。一条轨迹**只认一个字段**（覆盖实验点最多的那个）。"""
    whitelist = FIELD_WHITELIST.get(topic, ())
    if not whitelist or not experiments:
        return [], [], None

    best_field, best_hits = None, 0
    for candidate in whitelist:
        hits = sum(1 for e in experiments if scalar(dig(e, candidate)) is not None)
        if hits > best_hits:
            best_field, best_hits = candidate, hits
    if best_field is None:
        return [], [{"reason": "no_family_metric",
                     "detail": f"{topic} 轨迹里没有同族字段（白名单 {list(whitelist)}）"}], None

    points: list[Point] = []
    dropped: list[dict] = []
    for i, exp in enumerate(experiments):
        value = scalar(dig(exp, best_field))
        if value is None:
            dropped.append({
                "index": i, "reason": "no_value",
                "experiment_id": str(exp.get("experiment_id") or exp.get("id") or exp.get("run_id") or i),
            })
            continue
        approach = {
            key: str(exp[key]).strip()
            for key in APPROACH_FIELDS
            if isinstance(exp.get(key), str) and str(exp[key]).strip()
        }
        points.append(Point(
            index=i, raw=value, metric_field=best_field,
            experiment_id=str(exp.get("experiment_id") or exp.get("id") or exp.get("run_id") or i),
            approach=approach,
            runtime_seconds=scalar(exp.get("runtime_seconds")),
            status=str(exp["status"]) if exp.get("status") is not None else None,
        ))
    return points, dropped, best_field


def compute_curve(points: list[Point], direction: int) -> dict[str, object]:
    """b0 / bT / AUP / UR。全部在**方向统一后的原始尺度**上算。

    AUP 对仿射变换不变，所以在原始尺度还是归一化尺度上算结果相同。
    """
    if not points:
        return {"n_points": 0, "b0_raw": None, "bT_raw": None, "aup": None, "ur": None,
                "reason": "no_points"}

    oriented = [direction * p.raw for p in points]
    b0 = oriented[0]
    best_so_far: list[float] = []
    running = oriented[0]
    for value in oriented:
        running = max(running, value)
        best_so_far.append(running)
    bT = best_so_far[-1]

    span = bT - b0
    flat = span <= 0.0
    # 平坦轨迹 AUP = 0：best-so-far 从未高过起点 => 进展面积为 0。
    # 这**不会**与「最后一轮才进步」混淆 —— 后者 AUP = 1/N > 0，恒大于 0。
    aup = 0.0 if flat else sum((b - b0) / span for b in best_so_far) / len(best_so_far)

    # ⚠️ AUP 有 N 地板：末项恒为 1 => AUP >= 1/N（实测 N=2/3/4 的最小值恰为 0.5/0.333/0.25）。
    # 直接跨 run 比 AUP 会被 N 混淆，故额外给出两个可比版本。
    n = len(best_so_far)
    normalized = [0.0 if flat else (b - b0) / span for b in best_so_far]

    # aup_rel：把横轴归一化到 [0,1] 后做梯形积分（而非对均匀序号取均值）。
    # 比 `(aup-1/N)/(1-1/N)` 那种去地板法干净得多：同一相对时机下，p=0.5 时
    # N=4/8/20 都给精确 0.500（去地板法给 0.333/0.4286/0.4737）。
    if n < 2:
        aup_rel = 0.0 if flat else None
    else:
        tau = [i / (n - 1) for i in range(n)]
        aup_rel = sum(
            (normalized[i] + normalized[i + 1]) / 2.0 * (tau[i + 1] - tau[i])
            for i in range(n - 1)
        )

    # t_first：首次改进的相对位置，**真正 N 无关**，直接回答"多早"。
    # 平坦轨迹没有"首次改进"，记 None（与 AUP=0 的哨兵语义不同，不能混）。
    first_improvement = next(
        (i for i in range(1, n) if best_so_far[i] > best_so_far[i - 1]), None
    )
    if first_improvement is None or n < 2:
        t_first = None
        t_first_reason = "no_improvement" if first_improvement is None else "single_experiment"
    else:
        t_first = first_improvement / (n - 1)
        t_first_reason = None

    # UR：相对「此前最优」的严格突破。用相对容差，避免末位小数的抖动被算成突破
    # （困惑度/AUROC 都是 6 位小数，0.820001 vs 0.820000 不是「真正突破」）。
    def _beat(value: float, prev: float) -> bool:
        return value > prev + UR_REL_TOLERANCE * max(abs(prev), 1e-12)

    breakpoints = sum(1 for i in range(1, len(oriented)) if _beat(oriented[i], best_so_far[i - 1]))
    breakpoints_strict = sum(1 for i in range(1, len(oriented)) if oriented[i] > best_so_far[i - 1])
    denominator = len(oriented) - 1
    # N=1：没有"此前最优"可突破，"突破数/比较次数" = 0 —— 记 0 而非 null，
    # 并用 ur_reason 标出是无从比较，避免被当成"比过了但没突破"。
    ur = (breakpoints / denominator) if denominator > 0 else 0.0
    ur_reason = None if denominator > 0 else "single_experiment"

    return {
        "n_points": len(points),
        "b0_raw": b0,
        "bT_raw": bT,
        "aup": aup,
        "aup_rel": aup_rel,
        "t_first": t_first,
        "t_first_reason": t_first_reason,
        "ur": ur,
        "ur_reason": ur_reason,
        "improvements": breakpoints,
        "improvements_strict": breakpoints_strict,
        "flat_trajectory": flat,
        "best_so_far": best_so_far,
        "oriented_values": oriented,
    }


def load_official_final(run_dir: Path, topic: str) -> tuple[float | None, str | None]:
    key = OFFICIAL_SCORE_KEY.get(topic)
    if not key:
        return None, None
    for candidate in (run_dir / "workspace" / "score.json", run_dir / "score.json"):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(payload, dict):
            value = scalar(payload.get(key))
            if value is not None:
                return value, str(payload.get("score_source") or payload.get("source") or "unknown")
    return None, None


def compare_bt(official: float | None, bT_oriented: object, direction: int) -> str:
    """`bt_higher` = 框架没选自己最好的实验（bT 优于官方终值）。"""
    if official is None or not isinstance(bT_oriented, (int, float)) or isinstance(bT_oriented, bool):
        return "unavailable"
    delta = float(bT_oriented) - direction * official
    if abs(delta) <= 1e-9:
        return "match"
    return "bt_higher" if delta > 0 else "bt_lower"


def analyze_run(run_dir: Path, topic: str | None = None, anchors: dict | None = None,
                strict_anchors: bool = True) -> dict[str, object]:
    """一个 run 的完整轨迹指标记录（含归一化）。"""
    topic = topic or detect_topic(run_dir)
    record: dict[str, object] = {"run_dir": run_dir.name, "topic": topic}
    if topic not in FIELD_WHITELIST:
        record["error"] = "unknown_topic"
        return record

    trace = find_trace(run_dir)
    if trace is None:
        record["error"] = "no_experiment_trace"
        return record
    record["trace_path"] = str(trace)
    log = find_log(run_dir)
    record["log_path"] = str(log) if log else None

    experiments = load_experiments(trace)
    record["n_experiments"] = len(experiments)
    points, dropped, metric_field = extract_points(experiments, topic)
    record["dropped"] = dropped
    if not points:
        record.update({"basis": None, "error": "no_family_metric",
                       "b0": None, "bT": None, "aup": None, "ur": None})
        return record

    direction = 1 if topic not in ("arc", "babylm") else -1
    record["direction"] = "higher_better" if direction > 0 else "lower_better"
    record["basis"] = "trace_metric"
    record["metric_field"] = metric_field
    record.update(compute_curve(points, direction))

    # 归一化 b0/bT（固定锚点）
    anchors = anchors or load_anchors()
    anchor = (anchors.get("topics") or {}).get(topic, {})
    try:
        b0_norm, b0_oor = normalize_score(points[0].raw, anchor)
        # bT 落到某个实验点上，取其原始值
        bT_point = max(points, key=lambda p: direction * p.raw)
        bT_norm, bT_oor = normalize_score(bT_point.raw, anchor)
        record["b0"] = b0_norm
        record["bT"] = bT_norm
        record["out_of_anchor"] = {"b0": b0_oor, "bT": bT_oor}
    except PendingAnchorError as exc:
        if strict_anchors:
            raise
        record["b0"] = record["bT"] = None
        record["anchor_error"] = str(exc)

    official, source = load_official_final(run_dir, topic)
    record["official_final"] = official
    record["official_source"] = source
    record["bt_vs_official"] = compare_bt(official, record.get("bT_raw"), direction)
    record["points"] = [
        {"index": p.index, "experiment_id": p.experiment_id, "raw": p.raw,
         "approach": p.approach, "runtime_seconds": p.runtime_seconds, "status": p.status}
        for p in points
    ]
    record["approaches"] = [p.approach_text for p in points]
    return record


def iter_run_dirs(runs_root: Path) -> list[Path]:
    if not runs_root.is_dir():
        return []
    return [d for d in sorted(runs_root.iterdir()) if d.is_dir() and not d.name.startswith("_")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="轨迹指标 b0/bT/AUP/UR（确定性）")
    parser.add_argument("--run", type=Path, help="单个 run 目录")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--topic", choices=sorted(FIELD_WHITELIST))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--allow-pending-anchor", action="store_true",
                        help="锚点 pending 时不报错，改为把 b0/bT 留空（默认报错退出）")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    anchors = load_anchors()
    targets = [args.run.resolve()] if args.run else iter_run_dirs(args.runs_root)

    records = []
    for run_dir in targets:
        try:
            rec = analyze_run(run_dir, args.topic, anchors,
                              strict_anchors=not args.allow_pending_anchor)
        except PendingAnchorError as exc:
            print(f"ERROR: {run_dir.name}: {exc}\n"
                  f"补 `automation/scripts/metric_anchors.json` 后重跑。", file=sys.stderr)
            return 2
        if rec.get("topic") in FIELD_WHITELIST:
            records.append(rec)

    payload = {"runs_root": str(args.runs_root), "count": len(records), "records": records}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")

    if not args.quiet:
        usable = [r for r in records if r.get("basis") == "trace_metric"]
        print(f"扫描 run: {len(records)}，有同族字段可算的: {len(usable)}")
        by_topic: dict[str, list[bool]] = {}
        for r in records:
            by_topic.setdefault(str(r.get("topic")), []).append(r.get("basis") == "trace_metric")
        for topic, flags in sorted(by_topic.items()):
            print(f"  {topic:8s} 可算 {sum(flags):4d} / {len(flags):4d}")
        if args.out:
            print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

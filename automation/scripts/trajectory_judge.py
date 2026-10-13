#!/usr/bin/env python3
"""裁判 AI：轨迹序数评估（无同族字段时的兜底）+ ED 的 approach 判簇。

与 `trajectory_metrics.py` 的分工：
- 那边是**确定性算术**，零 LLM；
- 这边是**仅有的两处需要语义判断**的地方，故单独隔离，可注入替身以便离线测试。

⚠️ 序数评估**不是性能测量**。输出永远带 `is_performance_measurement: false`，
引用时必须连同这句话一起引（见 `docs/evaluation_metrics.md` §3）。

判官复用 `real_eval/evaluation/judge/orchestrator.py` 的 LLM 调用（凭据只从环境变量读）。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trajectory_metrics import (  # noqa: E402
    Point,
    compute_curve,
    detect_topic,
    find_log,
    find_trace,
    load_experiments,
    load_official_final,
)

# 判官实现所在目录（含 orchestrator.py 与 prompts/）
JUDGE_DIR = Path(os.environ.get(
    "JUDGE_DIR", str(Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])) / "real_eval" / "evaluation" / "judge")))
PROMPT_DIR = JUDGE_DIR / "prompts"

DEFAULT_SAMPLES = 3
ORDINAL_FIELDS = ("experiment_id", "method", "description", "decision", "verdict",
                  "status", "hypothesis", "model_strategy", "feature_strategy",
                  "name", "condition")
LOG_EXCERPT_CHARS = 12000


class JudgeUnavailable(RuntimeError):
    """判官不可用（缺密钥 / 缺实现）。"""


# 每条记录都必须带全这些键（哪怕是 null）—— 消费方不该靠 KeyError 发现缺失
METRIC_KEYS = ("b0", "bT", "b0_raw", "bT_raw", "aup", "aup_rel", "t_first", "ur")


def _null_metrics(record: dict[str, object]) -> dict[str, object]:
    for key in METRIC_KEYS:
        record.setdefault(key, None)
    return record


def _load_llm():
    """复用判官的 call_llm；缺实现或缺密钥时抛 JudgeUnavailable。"""
    if not (JUDGE_DIR / "orchestrator.py").is_file():
        raise JudgeUnavailable(f"找不到判官实现：{JUDGE_DIR / 'orchestrator.py'}")
    sys.path.insert(0, str(JUDGE_DIR))
    try:
        from orchestrator import call_llm, require_api_key  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise JudgeUnavailable(f"导入判官失败：{exc}") from exc
    try:
        require_api_key()  # 缺密钥立即报错，别等到第 3 次重试才失败
    except SystemExit as exc:
        raise JudgeUnavailable(str(exc)) from exc
    return call_llm


def load_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise JudgeUnavailable(f"找不到 prompt：{path}")
    return path.read_text(encoding="utf-8")


def fill(template: str, **values: object) -> str:
    out = template
    for key, value in values.items():
        payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        out = out.replace("{{" + key + "}}", payload)
    return out


def log_excerpt(run_dir: Path, limit: int = LOG_EXCERPT_CHARS) -> str:
    path = find_log(run_dir)
    if path is None:
        return "<无日志>"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n...（中间截断）...\n" + text[-half:]


def trajectory_evidence(run_dir: Path) -> list[dict[str, object]]:
    """给裁判看的实验证据（只挑有信息量的字段，不塞全文）。"""
    trace = find_trace(run_dir)
    if trace is None:
        return []
    out = []
    for i, exp in enumerate(load_experiments(trace)):
        row = {"index": i}
        for key in ORDINAL_FIELDS:
            value = exp.get(key)
            if value not in (None, "", [], {}):
                row[key] = value if isinstance(value, (int, float, bool)) else str(value)[:600]
        row.setdefault("experiment_id", str(exp.get("id") or i))
        out.append(row)
    return out


# ------------------------------------------------------------------ 序数评估


def ordinal_values(order: list[str], all_ids: list[str]) -> list[float] | None:
    """按 rank 映射到 [0,1]：rank 1 -> 1.0，rank N -> 0.0。"""
    n = len(all_ids)
    if n < 2:
        return None
    rank_of = {eid: r for r, eid in enumerate(order, start=1)}
    if set(rank_of) != set(all_ids):
        return None
    return [1.0 - (rank_of[eid] - 1) / (n - 1) for eid in all_ids]


def rank_once(prompt: str, llm, model: str | None, api_base: str | None) -> list[str] | None:
    kwargs = {}
    if model:
        kwargs["model"] = model
    if api_base:
        kwargs["api_base"] = api_base
    result = llm(prompt, **kwargs)
    if not isinstance(result, dict):
        return None
    ranking = result.get("ranking")
    if not isinstance(ranking, list):
        return None
    pairs = []
    for item in ranking:
        if isinstance(item, dict) and item.get("experiment_id") is not None and item.get("rank") is not None:
            try:
                pairs.append((int(item["rank"]), str(item["experiment_id"])))
            except (TypeError, ValueError):
                continue
    if not pairs:
        return None
    pairs.sort()
    return [eid for _, eid in pairs]


def assess_trajectory_ordinal(
    run_dir: Path, topic: str | None = None, *, llm=None,
    samples: int = DEFAULT_SAMPLES, model: str | None = None, api_base: str | None = None,
) -> dict[str, object]:
    """裁判对实验排序 → 序数尺度上的 b0/AUP/UR。"""
    topic = topic or detect_topic(run_dir)
    evidence = trajectory_evidence(run_dir)
    record: dict[str, object] = {
        "run_dir": run_dir.name, "topic": topic,
        "basis": "judge_ordinal", "is_performance_measurement": False,
        "n_experiments": len(evidence),
    }
    if len(evidence) < 2:
        # 单点/空轨迹没有可比对象 —— 按要求记**显式原因**，不硬造
        _null_metrics(record)
        record.update({
            "error": "insufficient_experiments",
            "error_detail": f"只有 {len(evidence)} 个实验，无法排序（裁判无从比较）",
        })
        return record

    all_ids = [str(e["experiment_id"]) for e in evidence]
    template = load_prompt("judge_trajectory_ordinal")
    prompt = fill(template, TRAJECTORY=evidence, LOG_EXCERPT=log_excerpt(run_dir))

    llm = llm or _load_llm()
    sample_orders = []
    for _ in range(max(1, samples)):
        order = rank_once(prompt, llm, model, api_base)
        if order is not None:
            sample_orders.append(tuple(order))
    if not sample_orders:
        _null_metrics(record)
        record.update({"error": "judge_failed", "error_detail": "三次采样都没拿到可解析的排序"})
        return record

    modal = statistics.mode(sample_orders) if len(sample_orders) > 1 else sample_orders[0]
    agreement = sample_orders.count(modal) / len(sample_orders)
    record["samples"] = len(sample_orders)
    record["agreement"] = agreement
    record["low_confidence"] = agreement < 1.0 or len(sample_orders) < samples

    values = ordinal_values(list(modal), all_ids)
    if values is None:
        # 排序不完整（漏了实验或给了未知 id）—— 不猜，如实记
        _null_metrics(record)
        record.update({
            "error": "incomplete_ranking",
            "error_detail": f"裁判给出的排序与实验集合不一致：{sorted(modal)} vs {sorted(all_ids)}",
            "ranking": list(modal),
        })
        return record

    aup_result = compute_curve(
        [Point(index=i, raw=v, metric_field="judge_ordinal", experiment_id=all_ids[i])
         for i, v in enumerate(values)],
        direction=1,
    )
    record.update(aup_result)
    # 序数尺度本身已经是 [0,1]，所以归一化后的 b0/bT **就是** b0_raw/bT_raw。
    # （compute_curve 只给 _raw；归一化是在 analyze_run 里补的，序数路径必须自己补，
    #   否则跑完裁判 b0/bT 仍为空 —— 实测踩到。）
    record["b0"] = record.get("b0_raw")
    record["bT"] = record.get("bT_raw")
    record["out_of_anchor"] = {"b0": False, "bT": False}
    record["ranking"] = list(modal)
    record["ordinal_values"] = values
    official, source = load_official_final(run_dir, topic)
    record["official_final"] = official
    record["official_source"] = source
    return record


# --------------------------------------------------------------------- ED


def cluster_once(prompt: str, llm, model: str | None, api_base: str | None) -> list[tuple[str, ...]] | None:
    kwargs = {}
    if model:
        kwargs["model"] = model
    if api_base:
        kwargs["api_base"] = api_base
    result = llm(prompt, **kwargs)
    if not isinstance(result, dict):
        return None
    clusters = result.get("clusters")
    if not isinstance(clusters, list):
        return None
    out = []
    for cluster in clusters:
        members = cluster.get("members") if isinstance(cluster, dict) else None
        if isinstance(members, list) and members:
            out.append(tuple(sorted(str(m) for m in members)))
    return sorted(out) if out else None


def assess_ed(
    run_dir: Path, topic: str | None = None, *, llm=None,
    samples: int = DEFAULT_SAMPLES, model: str | None = None, api_base: str | None = None,
) -> dict[str, object]:
    """ED = 裁判判定的簇数 / 实验数。"""
    topic = topic or detect_topic(run_dir)
    evidence = trajectory_evidence(run_dir)
    record: dict[str, object] = {
        "run_dir": run_dir.name, "topic": topic, "basis": "judge_cluster",
        "n_experiments": len(evidence),
    }
    with_approach = [e for e in evidence if any(e.get(k) for k in
                     ("method", "model_strategy", "feature_strategy", "hypothesis", "condition", "name"))]
    if len(with_approach) < 2:
        record["ed"] = None
        record.update({
            "error": "insufficient_approaches",
            "error_detail": f"只有 {len(with_approach)} 个实验带 approach 描述，无法判簇",
        })
        return record

    template = load_prompt("judge_ed")
    prompt = fill(template, APPROACHES=with_approach)
    llm = llm or _load_llm()

    sample_clusters = []
    for _ in range(max(1, samples)):
        clusters = cluster_once(prompt, llm, model, api_base)
        if clusters is not None:
            sample_clusters.append(tuple(clusters))
    if not sample_clusters:
        record["ed"] = None
        record.update({"error": "judge_failed", "error_detail": "三次采样都没拿到可解析的簇划分"})
        return record

    modal = statistics.mode(sample_clusters) if len(sample_clusters) > 1 else sample_clusters[0]
    agreement = sample_clusters.count(modal) / len(sample_clusters)
    n = len(with_approach)
    valid, why = _validate_partition(modal, with_approach)
    record.update({
        "ed": len(modal) / n,
        "n_clusters": len(modal),
        "n_considered": n,
        "clusters": [list(c) for c in modal],
        "members_valid": valid,
        "members_note": why,
        "samples": len(sample_clusters),
        "agreement": agreement,
        "low_confidence": agreement < 1.0 or len(sample_clusters) < samples,
    })
    return record


def _validate_partition(clusters: tuple[tuple[str, ...], ...],
                        evidence: list[dict[str, object]]) -> tuple[bool, str]:
    """校验判官给的簇是否真是实验集合的**有效划分**（每个实验恰好属于一个簇）。

    判官回的成员名**不统一**：有时是序号（`"0"`/`"1"`），有时是真实的
    `experiment_id`（`"E1"`/`"exp1"`/`"boundary_randomized_..."`）。所以两种都要认。
    不校验的话，成员写错（漏实验、编出不存在的 id）会让 ED 静默失真。
    """
    by_index = {str(e.get("index")): str(e["experiment_id"]) for e in evidence}
    by_id = {str(e["experiment_id"]) for e in evidence}
    seen: list[str] = []
    unknown: list[str] = []
    for cluster in clusters:
        for member in cluster:
            name = str(member)
            if name in by_id:
                seen.append(name)
            elif name in by_index:
                seen.append(by_index[name])
            else:
                unknown.append(name)
    if unknown:
        return False, f"簇里出现无法对应的成员：{sorted(set(unknown))[:5]}"
    if len(seen) != len(set(seen)):
        return False, "有实验被分进多个簇"
    if set(seen) != by_id:
        missing = sorted(by_id - set(seen))
        return False, f"未覆盖全部实验，缺：{missing[:5]}"
    return True, "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="裁判：轨迹序数评估 + ED 判簇")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--what", choices=("ordinal", "ed", "both"), default="both")
    parser.add_argument("--topic", choices=("arc", "mc", "babylm", "psydef", "tdc"))
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--model")
    parser.add_argument("--api-base")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    result: dict[str, object] = {"run_dir": str(args.run)}
    try:
        if args.what in ("ordinal", "both"):
            result["ordinal"] = assess_trajectory_ordinal(
                args.run, args.topic, samples=args.samples,
                model=args.model, api_base=args.api_base)
        if args.what in ("ed", "both"):
            result["ed"] = assess_ed(
                args.run, args.topic, samples=args.samples,
                model=args.model, api_base=args.api_base)
    except JudgeUnavailable as exc:
        print(f"判官不可用：{exc}", file=sys.stderr)
        print("需要可用的 JUDGE_API_KEY / OPENAI_API_KEY。", file=sys.stderr)
        return 2

    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

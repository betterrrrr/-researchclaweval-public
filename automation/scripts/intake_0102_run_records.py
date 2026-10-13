#!/usr/bin/env python3
"""01/02 交付包（researchclaweval-01-02-run-records）落地整理 —— 幂等、可干跑。

背景：01（AI-Researcher）/ 02（AI-Scientist-v2）的 run records 由协作者在**自己的环境**
跑完，打包为 `Refrainkana33/researchclaweval-01-02-run-records`（4.8G / 14,811 文件）。
本仓库只收下这份**原样副本**（`real_eval/runs_0102/`），不重跑、不改写框架代码。

整理做三件事（都属于「让管线能算对」，不是「改分」）：

1. `mc_adj_score` —— 01 MountainCar 的 3 个 run 在交付包里**没有 workspace/score.json**：
   它们的分数是事后由冻结评分器在追溯裁定记录里跑出来的（2026-09-28 的 `>=1 实验`
   门裁定）。把裁定结果**原样**落到该 run 自己的 `workspace/score.json`
   （形状与 03–07 完全一致：score / reward_std / score_source / checkpoint_count），
   另写 `workspace/score_provenance.json` 记明来源裁定 tag 与 verdict 路径。
2. `mc_manifest_model` —— 01 × mc × gpt-6-luna 的 `fullrun_manifest.json` 里
   `evaluation_model` 写成 `gpt-5.6-luna`（交付方已标为 host 侧缺陷）。管线**manifest 优先**，
   不改就会把这一格挂到 5.6 列、并让 6-luna 列整格消失。修正值取自同 run 的
   `experiment_trace.json:framework_internal_model`（`gpt-6-luna`）+ 裁定记录
   （`verdict.json:model`），原值保留在 `evaluation_model_as_delivered`。
3. `babylm_invalidate` —— 01 × babylm × kimi 两次尝试自报的 `validation_perplexity`
   （1.0314 / 1.00003）**物理上不可能**（BabyLM 上约 1.0 意味着近乎完美的语言模型；
   同类先例见 EvoScientist 的 ALiBi mask 写反导致的 val_ppl=1.007）。交付方也把这两次
   记为无分。把 `perplexity` 置 null 并标 `invalid`，原值存 `perplexity_as_delivered`
   —— 否则该格「越低越好」会把 1.00003 选成 **babylm 全局冠军**。

所有被改动的文件都先存一份 `<name>.delivered.bak`，可随时回退比对。
用法：
    python3 intake_0102_run_records.py --root $REAL_EVAL_RUNS_0102_ROOT [--dry-run]
"""

from __future__ import annotations

import os

import argparse
import json
import shutil
from pathlib import Path

# 交付包里 01 MountainCar 的三次「事后裁定出分」：run 目录 → 裁定 tag
MC_ADJUDICATED = {
    "01_ai_researcher__mountaincar_continuous__deepseek-v4-flash__"
    "fullrun_mcar_01_ds_20260927_124914": "ds_124914",
    "01_ai_researcher__mountaincar_continuous__kimi-k2.6__"
    "fullrun_mcar_01_kimi_20261003_163455": "kimi_163455",
    "01_ai_researcher__mountaincar_continuous__gpt-6-luna__"
    "fullrun_mcar_01_g6luna_rep2_20260928_113815": "g6_113815",
}
ADJUDICATION_DIR = "01_ai_researcher__mountaincar_continuous__adjudication_mcar01_ge1_20260928"

MC_MANIFEST_MODEL_FIX = {
    "01_ai_researcher__mountaincar_continuous__gpt-6-luna__"
    "fullrun_mcar_01_g6luna_rep2_20260928_113815": "gpt-6-luna",
}

BABYLM_INVALIDATE = {
    "01_ai_researcher__babylm__kimi-k2.6__attempt1__fullrun_babylm_01_kimi_20261003_072259":
        "自报 val ppl=1.0314 物理上不可能（BabyLM 语料上 ≈1.0 等于近乎完美模型）；"
        "交付方记为 stale/buggy trace 值、无分",
    "01_ai_researcher__babylm__kimi-k2.6__attempt2__fullrun_babylm_01_kimi_20261003_162502":
        "自报 val ppl=1.00003 / 2.8047 物理上不可能；该 run 本身失败"
        "（未交付 research_idea/final_report），交付方记为无分",
}

# babylm 困惑度的**可信下限**。观测依据：本包同框架同 topic 的三个有效格是
# 106.58 / 577.24 / 742.97；全项目 25 格观测区间约 20–3022。
# 低于 10 只出现过一次，就是 EvoScientist 的 ALiBi mask 写反（1.007）——判评测缺陷。
# 用它做闸门：**只作废物理上不可能的取值，不去动 20–3022 里的任何数**。
BABYLM_MIN_PLAUSIBLE_PPL = 10.0


def _backup(path: Path, dry: bool) -> None:
    bak = path.with_name(path.name + ".delivered.bak")
    if bak.exists():
        return
    if dry:
        print(f"   [dry] would back up {path.name} -> {bak.name}")
        return
    shutil.copy2(path, bak)


def _write_json(path: Path, payload: dict, dry: bool) -> None:
    if dry:
        print(f"   [dry] would write {path}")
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_mc_adj_score(root: Path, dry: bool) -> int:
    print("== 1. 01 MountainCar：把裁定分落回各 run 的 workspace/score.json")
    adj = root / ADJUDICATION_DIR
    changed = 0
    for run_name, tag in sorted(MC_ADJUDICATED.items()):
        run = root / run_name
        verdict_path = adj / tag / "verdict.json"
        if not verdict_path.is_file():
            print(f"   !! 缺 verdict: {verdict_path}")
            continue
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        score = verdict.get("score") or {}
        if score.get("score") is None:
            print(f"   !! {tag} 裁定没有分数，跳过")
            continue
        ws = run / "workspace"
        target = ws / "score.json"
        # 与 03–07 的官方 mc score.json **逐键同形**，便于同表比较
        payload = {
            "score": score["score"],
            "reward_std": score.get("reward_std"),
            "score_source": score.get("score_source", "official_evaluate_py"),
            "checkpoint_count": score.get("checkpoint_count"),
        }
        prov = {
            "score_source": payload["score_source"],
            "score_artifact": str(verdict_path.relative_to(root)),
            "adjudication": verdict.get("adjudication"),
            "adjudication_tag": tag,
            "source_run": verdict.get("source_run"),
            "gate_version": verdict.get("gate_version"),
            "gate_rc": verdict.get("gate_rc"),
            "score_rc": verdict.get("score_rc"),
            "adjudicated_at": verdict.get("adjudicated_at"),
            "note": "分数由冻结官方评分器在追溯裁定记录里产出；本文件是原样落库，未重算",
        }
        if target.is_file() and json.loads(target.read_text(encoding="utf-8")).get("score") == payload["score"]:
            print(f"   = {run_name[:60]} 已就位，跳过")
            continue
        print(f"   + {tag}: score={payload['score']} -> {run_name[:52]}/workspace/score.json")
        if target.is_file():
            _backup(target, dry)
        _write_json(target, payload, dry)
        _write_json(ws / "score_provenance.json", prov, dry)
        changed += 1
    return changed


def apply_mc_manifest_model(root: Path, dry: bool) -> int:
    print("== 2. 01 × mc × gpt-6-luna：修正 manifest 的 evaluation_model")
    changed = 0
    for run_name, model in sorted(MC_MANIFEST_MODEL_FIX.items()):
        path = root / run_name / "fullrun_manifest.json"
        if not path.is_file():
            print(f"   !! 缺 manifest: {path}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        delivered = payload.get("evaluation_model")
        if delivered == model:
            print(f"   = {run_name[:52]} 已是 {model}，跳过")
            continue
        if delivered != "gpt-5.6-luna":
            print(f"   !! {run_name[:52]} 交货值是 {delivered!r}，与预期的 gpt-5.6-luna 不符，**不动**")
            continue
        payload["evaluation_model"] = model
        payload["evaluation_model_as_delivered"] = delivered
        payload["evaluation_model_note"] = (
            "交付方标注的 host 侧缺陷（写成了 gpt-5.6-luna）；"
            "修正依据：同 run 的 experiment_trace.json:framework_internal_model 与裁定记录 "
            "verdict.json:model 均为 gpt-6-luna"
        )
        print(f"   + {run_name[:52]}: {delivered} -> {model}")
        _backup(path, dry)
        _write_json(path, payload, dry)
        changed += 1
    return changed


def apply_babylm_invalidate(root: Path, dry: bool) -> int:
    print("== 3. 01 × babylm × kimi：作废物理上不可能的 perplexity")
    changed = 0
    for run_name, reason in sorted(BABYLM_INVALIDATE.items()):
        path = root / run_name / "workspace" / "score.json"
        if not path.is_file():
            print(f"   !! 缺 score.json: {path}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("perplexity")
        if payload.get("invalid") is True:
            print(f"   = {run_name[:52]} 已作废，跳过")
            continue
        if not isinstance(value, (int, float)) or value >= BABYLM_MIN_PLAUSIBLE_PPL:
            print(f"   !! {run_name[:52]} perplexity={value!r} 不在预期区间，**不动**")
            continue
        payload["perplexity_as_delivered"] = value
        payload["perplexity"] = None
        payload["invalid"] = True
        payload["invalid_reason"] = reason
        print(f"   + {run_name[:60]}: perplexity {value} -> null（invalid）")
        _backup(path, dry)
        _write_json(path, payload, dry)
        changed += 1
    return changed


def apply_babylm_invalidate_trace(root: Path, dry: bool) -> int:
    """同一处作废也要落到 **trace** 上。

    轨迹指标读的是 `experiment_trace.json` 的 `validation_perplexity`，**不是** score.json。
    只清 score.json 会让该格继续宣称 `basis_trajectory = trace_metric`，
    b0_raw 里挂着 1.03 这个不可能的值 —— 等于用一个"真实测量"的壳装了个假数。
    """
    print("== 3b. 同上，落到 experiment_trace.json（轨迹路径）")
    changed = 0
    for run_name, reason in sorted(BABYLM_INVALIDATE.items()):
        path = root / run_name / "workspace" / "experiment_trace.json"
        if not path.is_file():
            print(f"   !! 缺 trace: {path}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        experiments = payload.get("experiments")
        if not isinstance(experiments, list):
            print(f"   !! {run_name[:52]} 没有 experiments 列表，**不动**")
            continue
        hits = [e for e in experiments if isinstance(e, dict)
                and isinstance(e.get("validation_perplexity"), (int, float))
                and e["validation_perplexity"] < BABYLM_MIN_PLAUSIBLE_PPL]
        if not hits:
            print(f"   = {run_name[:52]} trace 已无越界值，跳过")
            continue
        for e in hits:
            e["validation_perplexity_as_delivered"] = e["validation_perplexity"]
            e["validation_perplexity"] = None
            e["invalidated"] = True
        payload["invalidated_validation_perplexity"] = True
        payload["invalidated_reason"] = reason
        print(f"   + {run_name[:52]}: trace 里作废 {len(hits)} 个值")
        _backup(path, dry)
        _write_json(path, payload, dry)
        changed += len(hits)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="01/02 交付包落地整理（幂等）")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("REAL_EVAL_RUNS_0102_ROOT", Path(__file__).resolve().parents[2] / "real_eval" / "runs_0102")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        parser.error(f"root 不存在: {args.root}")
    print(f"root = {args.root}{'  [DRY RUN]' if args.dry_run else ''}\n")

    total = 0
    total += apply_mc_adj_score(args.root, args.dry_run)
    total += apply_mc_manifest_model(args.root, args.dry_run)
    total += apply_babylm_invalidate(args.root, args.dry_run)
    total += apply_babylm_invalidate_trace(args.root, args.dry_run)
    print(f"\n共改动 {total} 项" + ("（干跑，未落盘）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

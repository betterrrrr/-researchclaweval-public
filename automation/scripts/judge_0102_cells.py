#!/usr/bin/env python3
"""给 01/02 的 40 个格子补**七维判官**分（PQ/PEA/ER/OU/ECC/SC/CC）。

为什么要单独一个脚本：七维判官（`real_eval/evaluation/judge/orchestrator.py`）**不在**
12 指标管线里，它按 `--run <run_dir>` 一次一个 run 手工调；01/02 有 40 个格子，
需要「选代表性 run + 断点续跑 + 记录跳过了谁」。ED 与轨迹序数不走这里
（那是 `evaluation_metrics_report.py --judge` 的事）。

三条硬规则：

1. **只判产物齐全的 run。** 缺 `research_idea` / `experiment_trace` / `final_report`
   的 run 直接跳过并记录 —— 判官遇到 "<FILE NOT FOUND>" **照样给分**，
   那是静默假分。既有 100 格里被判过的 29 个 run **全部**产物齐全，
   这条规则与既有做法一致。
2. **跳过一次的格子不假装有值**：`basis_judge` 仍是 `missing`，原因写进 sidecar。
3. **幂等 + 断点续跑**：7 个维度逐个落盘，中断后重跑只补缺的维度
   （40 run × 7 维 = 280 次调用，不能因为一次断网全废）。

用法：
    python3 judge_0102_cells.py --dry-run          # 只报告要花多少次调用
    python3 judge_0102_cells.py --limit 1          # 冒烟：1 个 run（7 次调用）
    python3 judge_0102_cells.py --workers 6        # 并发（默认 4）：231 次调用 ≈ 1/4 墙钟
    python3 judge_0102_cells.py                    # 全量，可用 Ctrl-C 中断后续跑
"""

from __future__ import annotations

import os

import argparse
import importlib.util
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2]))
SCRIPTS = REPO / "automation" / "scripts"
RUNS_0102 = Path(os.environ.get("REAL_EVAL_RUNS_0102_ROOT", Path(__file__).resolve().parents[2] / "real_eval" / "runs_0102"))
SIDECAR_NAME = "judge_7dim_provenance.json"
REQUIRED = ("research_idea", "experiment_trace", "final_report")


def load_orchestrator():
    spec = importlib.util.spec_from_file_location(
        "judge_orchestrator", REPO / "real_eval" / "evaluation" / "judge" / "orchestrator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_report():
    spec = importlib.util.spec_from_file_location(
        "evaluation_metrics_report", SCRIPTS / "evaluation_metrics_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pick_judge_run(cells: dict, cell: tuple, orch, subs: dict | None = None) -> tuple[Path | None, str]:
    """选该格子里**产物齐全**（含可用替身）的那个 run；优先管线给的代表 run。"""
    subs = subs or {}
    units = cells.get(cell) or []
    ranked = []
    for unit in units:
        arts = orch.load_artifacts(str(unit))
        gaps = [k for k in REQUIRED
                if (arts[k]["size"] == 0 or not arts[k].get("readable", True))
                and not (subs.get(k) and (unit / subs[k]).is_file())]
        ranked.append((len(gaps), unit, gaps))
    complete = [(u, g) for n, u, g in sorted(ranked, key=lambda x: x[0]) if n == 0]
    if complete:
        return complete[0][0], "complete_artifacts"
    gaps = sorted({g for _, _, gs in ranked for g in gs})
    return None, f"skipped_missing:{','.join(gaps) if gaps else 'no_runs_in_cell'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="01/02 七维判官补分（幂等/可续跑）")
    parser.add_argument("--runs-root", type=Path, default=RUNS_0102)
    parser.add_argument("--frameworks", default="01,02",
                        help="逗号分隔的框架码（默认 01,02 = 交付包；04/07 从没判过，要单独跑）")
    parser.add_argument("--model", default=None, help="判官模型（默认取 orchestrator 的 DEFAULT_MODEL）")
    parser.add_argument("--limit", type=int, default=None, help="最多判多少个 run（冒烟用）")
    parser.add_argument("--workers", type=int, default=4,
                        help="并发处理的 run 数（默认 4；1 = 串行。每个 run 内部 7 次调用仍是顺序的）")
    parser.add_argument("--pause", type=float, default=0.0,
                        help="同一 run 内两次维度调用之间的停顿秒数（默认 0）。"
                             "并发高时后段维度容易被中继限流，表现为 empty response —— 实测 6 并发下 "
                             "失败的 19 次里有 13 次集中在第 6 个维度 sc。")
    parser.add_argument("--substitute", default="",
                        help="产物替身，形如 final_report=workspace/paper.md —— 只在**框架自己写的**产物"
                             "之间替换（如 01×tdc 的契约 final_report.md 缺失、但有框架自产的 paper.md）；"
                             "用了替身会计入 `judge_provenance.substitutions`，管线据此标 basis_judge。"
                             "**不用于 host 合成内容**。")
    parser.add_argument("--redims", action="store_true",
                        help="**重判**：已有的维度也重跑（用于统一判官模型换版）。"
                             "覆盖前会把旧 score.json 备份成 `score.json.judge-prev.bak`（只备份一次）。")
    parser.add_argument("--dims", default="",
                        help="只判这些维度（逗号分隔，默认全部 7 个）。用于产物只够判部分维度的格子 —— "
                             "判不了的维度**留 null**，不喂占位内容硬判（那是静默假分）。")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path,
                        default=REPO / "analysis" / "evaluation_metrics.json")
    args = parser.parse_args(argv)

    orch = load_orchestrator()
    report = load_report()
    model = args.model or orch.DEFAULT_MODEL

    allowed = tuple(x.strip() for x in str(args.frameworks).split(",") if x.strip())
    cells = report.collect_cells(args.runs_root, allowed=allowed)
    subs_spec = {}
    for spec in [x for x in str(args.substitute).split(",") if x.strip()]:
        key, _, rel = spec.partition("=")
        if key.strip() in REQUIRED and rel.strip():
            subs_spec[key.strip()] = rel.strip()
    targets = {c: pick_judge_run(cells, c, orch, subs_spec) for c in sorted(cells)}

    todo, skipped = [], {}
    for cell, (unit, how) in targets.items():
        if unit is None:
            skipped[f"{cell[0]}x{cell[1]}x{cell[2]}"] = how
            continue
        score_path = unit / "score.json"
        have = set()
        if score_path.is_file():
            try:
                dims = (json.loads(score_path.read_text()).get("evaluation") or {}).get("dimensions") or {}
                have = {d for d, v in dims.items() if isinstance(v, dict) and v.get("score") is not None}
            except Exception:  # noqa: BLE001
                pass
        want = [d for d in (str(args.dims).split(",") if args.dims else orch.DIMENSIONS) if d.strip()] \
               if args.dims else list(orch.DIMENSIONS)
        missing = [d for d in want if d in orch.DIMENSIONS and (args.redims or d not in have)]
        if missing:
            todo.append((cell, unit, missing))

    print(f"{'+'.join(allowed)} 格子 {len(cells)}；可判 {len(todo)}；跳过 {len(skipped)}")
    print(f"判官模型 {model} @ {orch.DEFAULT_API_BASE}")
    print(f"待调用维度数 {sum(len(m) for _, _, m in todo)}（每个维度 1 次调用）")
    for name, why in sorted(skipped.items()):
        print(f"   skip {name}: {why}")
    if args.dry_run:
        for cell, unit, missing in todo[:10]:
            print(f"   todo {cell[0]}×{cell[1]}×{cell[2]}: {unit.name[:52]} 缺 {missing}")
        return 0

    if args.limit is not None:
        todo = todo[:args.limit]

    # 并发在**run 粒度**：一个 run 的 7 次调用仍顺序进行（同一份产物反复入 prompt，
    # 顺序调用不会互相干扰），多个 run 之间并行。每个 run 只在自己结束时写自己的
    # `score.json` —— 文件互不相同，无需加锁。
    lock = threading.Lock()
    wrote, failed = 0, []

    def judge_one(item):
        cell, unit, missing = item
        fw, topic, model_name = cell
        arts = orch.load_artifacts(str(unit))
        subs = {}
        for spec in [x for x in str(args.substitute).split(",") if x.strip()]:
            key, _, rel = spec.partition("=")
            key, rel = key.strip(), rel.strip()
            if not (key in REQUIRED and rel):
                continue
            if arts[key]["size"] == 0 or not arts[key].get("readable", True):
                alt = unit / rel
                if alt.is_file():
                    try:
                        content = alt.read_text(encoding="utf-8", errors="replace")
                        arts[key] = {"path": str(alt), "size": len(content), "content": content, "substituted": True}
                        subs[key] = rel
                    except OSError:
                        pass
        score_path = unit / "score.json"
        payload = {}
        if score_path.is_file():
            try:
                payload = json.loads(score_path.read_text())
            except Exception:  # noqa: BLE001
                payload = {}
        dims = ((payload.get("evaluation") or {}).get("dimensions") or {})
        local_failed = []
        with lock:
            print(f"== 开始 {fw}×{topic}×{model_name}: {unit.name[:56]}  待补 {missing}", flush=True)
        scores = {}
        for i, dim in enumerate(missing):
            if i and args.pause:
                time.sleep(args.pause)
            prompt = orch.build_prompt(orch.load_prompt(dim), arts)
            result = orch.call_llm(prompt, model=model)
            dims[dim] = result
            scores[dim] = result.get("score", "ERR")
            if result.get("score") is None:
                local_failed.append((unit.name, dim, str(result.get("error"))[:80]))
        with lock:
            print(f"   完成 {unit.name[:56]} → {scores}", flush=True)
        payload["framework"], payload["topic"], payload["model"] = fw, topic, model_name
        payload["run_dir"] = unit.name
        payload["evaluation"] = {
            "judge_model": model,
            "judge_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "artifact_sizes": {k: v["size"] for k, v in arts.items()},
            "dimensions": dims,
        }
        # 判官记录**另存 `score.json`**（01/02 的官方分在 `workspace/score.json`，两者不同文件）
        payload["judge_provenance"] = {
            "run_selection": "complete_artifacts" + ("+substituted" if subs else ""),
            "artifact_paths": {k: arts[k]["path"] for k in arts},
            "substitutions": subs,
            "note": "官方分在 workspace/score.json，本文件只装判官七维"
                    + ("；本次用了**框架自产**的替身产物，见 substitutions" if subs else ""),
        }
        if score_path.is_file() and not score_path.with_name("score.json.judge-prev.bak").exists():
            # 重判会覆盖已发布的值 —— 旧值必须留一份可复核的副本（只备份一次，保证是**最早那版**）
            try:
                score_path.with_name("score.json.judge-prev.bak").write_bytes(score_path.read_bytes())
            except OSError:
                pass
        score_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return local_failed

    workers = max(1, args.workers)
    if workers == 1:
        for item in todo:
            failed.extend(judge_one(item))
            wrote += 1
    else:
        print(f"并发 {workers} 个 run（每个 run 内 7 次调用仍顺序）")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(judge_one, item): item for item in todo}
            for fut in as_completed(futures):
                item = futures[fut]
                try:
                    failed.extend(fut.result())
                    wrote += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"   !! {item[1].name[:56]} 整体失败: {exc}", flush=True)
                    failed.append((item[1].name, "all", str(exc)[:80]))

    sidecar = args.runs_root / (SIDECAR_NAME if allowed == ("01", "02")
                                else f"judge_7dim_provenance_{'-'.join(allowed)}.json")
    if not wrote and not failed and not todo:
        # 没真判过（例如 --limit 0 冒烟）就不要落一个 "runs_judged: 0" 的账，
        # 那种记录以后会被当成"判过了但没分"。
        print("\n本轮没有实际判分，不写 sidecar。")
        return 0
    sidecar.write_text(json.dumps({
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "judge_model": model,
        "runs_judged": wrote,
        "cells_skipped": skipped,
        "dimension_calls_failed": failed,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n判完 {wrote} 个 run；跳过的格子 {len(skipped)} 个 → 见 {sidecar}")
    if failed:
        print(f"⚠ 有 {len(failed)} 次维度调用返回空分（重跑本脚本会只补这些维度）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

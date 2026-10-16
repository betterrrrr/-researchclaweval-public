#!/usr/bin/env python3
"""把 ARC-WBE-2026 切成「框架可见验证集」+「host 评分集」。

背景
----
arc 是五个 topic 里**唯一一个框架拿不到真值的**：契约只给 `weights`
（"target labels are not visible to the framework"），而官方指标
`adjusted_final_layer_score` 要比对真激活 —— 真激活是 host-only。

后果：框架**无法自评**。tdc / psydef 给了带标签的 train/validation，
框架每轮都能算 AUROC / F1；arc 没有，于是 `experiment_trace.json` 里
没有逐轮性能数字，b0/bT/AUP/UR 只能落到裁判序数兜底。

实测（`evaluation_metrics_report.py`，140 格）：
    tdc 27/28  babylm 24/28  psydef 21/28  mc 11/28  arc **3/28**

本脚本从带标签的记录里切出一小块**可见验证集**交给框架自评，
其余作为 host 评分集。两边各自的 sha256 写进 manifest，供冻结与校验。

⚠️ 两个必须知道的口径后果
--------------------------
1. **评分集从 N 变成 N - visible_count**，因此本脚本产出的分数与既有
   140 格矩阵的 arc 分**不可并列**（旧分是在全部 100 个 MLP 上算的）。
   比赛内部可比（所有参赛者用同一份本脚本产出），对外引用必须标注。
2. 可见验证集是从**公开数据**里切的，不是从隐藏集里泄露出去的。
   它和评分集**互斥**，所以框架调不到被评分的那些 MLP。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

# 可见验证集要能算官方指标 → 必须含这三列；mlp_* 供溯源。
VISIBLE_COLUMNS = (
    "mlp_id",
    "mlp_name",
    "mlp_seed",
    "weights",
    "all_layer_means",
    "final_means",
)
# 评分集只需评分器要求的三列 + 溯源列（不喂给框架，故多留无妨）。
SCORING_COLUMNS = VISIBLE_COLUMNS

DEFAULT_VISIBLE_COUNT = 10
DEFAULT_SEED = 42


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split ARC-WBE-2026 into a visible validation set and a host scoring set."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--visible-count",
        type=int,
        default=DEFAULT_VISIBLE_COUNT,
        help=f"可见验证集条数（默认 {DEFAULT_VISIBLE_COUNT}）",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    source_data = source_root / "data"
    source_files = sorted(source_data.glob("*.parquet"))
    if not source_files:
        raise SystemExit(f"no parquet files under {source_data}")
    # 允许写进已存在的数据根（例如 data/arc_white_box_estimation_2026/），
    # 但绝不覆盖已经切好的结果 —— 切分是要冻结的，重切必须人工删掉旧目录。
    for name in ("visible-validation", "scoring"):
        if (output_root / name).exists():
            raise SystemExit(
                f"refusing to overwrite an existing split: {output_root / name}\n"
                "切分是冻结件；要重切请先人工删除该目录（这会改变 sha256）。"
            )

    import pyarrow as pa
    import pyarrow.parquet as pq

    # ── 1. 只读 mlp_id 定选择（避免把整表读进内存）────────────────────
    ids: list[int] = []
    for source_file in source_files:
        table = pq.read_table(source_file, columns=["mlp_id"])
        ids.extend(table["mlp_id"].to_pylist())
    if len(ids) != len(set(ids)):
        raise SystemExit("source dataset has duplicate mlp_id; refusing to split")
    total = len(ids)
    if not 0 < args.visible_count < total:
        raise SystemExit(
            f"--visible-count must be in 1..{total - 1}, got {args.visible_count}"
        )

    # 确定性选择：对升序 id 做种子洗牌再取前 k。
    # 用洗牌而不是"取前 k 个"，是为了避开 mlp_id 顺序里可能存在的相关性。
    ordered = sorted(ids)
    chosen = set(random.Random(args.seed).sample(ordered, args.visible_count))

    # ── 2. 整表读出，按 mlp_id 过滤后一次写完 ───────────────────────────
    # 刻意**不**用 batch_size=1 流式路由：那会写出「每行一个行组」，压缩率崩掉
    # （实测 90 行输出 1.17GB，比 100 行的源文件还大 39%，行组数 90 vs 源的 1）。
    # weights 是 32×256×256 的嵌套列，整表读需要较大内存 —— host 上跑没问题。
    output_root.mkdir(parents=True, exist_ok=True)
    visible_dir = output_root / "visible-validation" / "data"
    scoring_dir = output_root / "scoring" / "data"
    visible_dir.mkdir(parents=True)
    scoring_dir.mkdir(parents=True)
    visible_path = visible_dir / "arc_wbe_2026_visible-validation-00000-of-00001.parquet"
    scoring_path = scoring_dir / "arc_wbe_2026_scoring-00000-of-00001.parquet"

    tables = []
    for source_file in source_files:
        parquet_file = pq.ParquetFile(source_file)
        missing = [c for c in SCORING_COLUMNS if c not in parquet_file.schema_arrow.names]
        if missing:
            raise SystemExit("source dataset is missing required columns: " + ", ".join(missing))
        tables.append(parquet_file.read(columns=list(SCORING_COLUMNS)))
    table = pa.concat_tables(tables) if len(tables) > 1 else tables[0]

    visible_mask = pa.array([value in chosen for value in table["mlp_id"].to_pylist()])
    visible_table = table.filter(visible_mask)
    scoring_table = table.filter(pa.compute.invert(visible_mask))
    n_visible = visible_table.num_rows
    n_scoring = scoring_table.num_rows
    if n_visible != args.visible_count or n_visible + n_scoring != total:
        raise SystemExit(
            f"split accounting mismatch: visible={n_visible} scoring={n_scoring} total={total}"
        )
    pq.write_table(visible_table, visible_path, compression="zstd")
    pq.write_table(scoring_table, scoring_path, compression="zstd")

    # ── 3. 冻结清单（体积小、可公示）──────────────────────────────────
    manifest = {
        "topic_id": "arc_wbe_2026",
        "format": "arc-wbe-2026-visible-validation-split",
        "seed": args.seed,
        "visible_count": n_visible,
        "scoring_count": n_scoring,
        "source_total": total,
        "visible_mlp_ids": sorted(chosen),
        "files": {
            "visible-validation/data/"
            "arc_wbe_2026_visible-validation-00000-of-00001.parquet": {
                "sha256": sha256_of(visible_path),
                "n_rows": n_visible,
                "columns": list(VISIBLE_COLUMNS),
            },
            "scoring/data/arc_wbe_2026_scoring-00000-of-00001.parquet": {
                "sha256": sha256_of(scoring_path),
                "n_rows": n_scoring,
                "columns": list(SCORING_COLUMNS),
            },
        },
        "policy": (
            "visible-validation 挂进框架容器供自评；scoring 只交给 host 评分器。"
            "两者互斥，且都从公开数据切出 —— 这里没有隐藏集泄露，只有评分集与自评集分离。"
        ),
        "caveat": (
            "评分集为 %d 个 MLP（原为 %d）。因此本切分下的 arc 分与既有 140 格矩阵的 arc 分"
            "不可并列 —— 旧分在全部 %d 个 MLP 上计算。比赛内部可比。"
        ) % (n_scoring, total, total),
    }
    (output_root / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 两个 root 各放一份 metadata.json，和 weights-only 生成器保持同一形态。
    for name, path, n_rows, policy in (
        (
            "visible-validation",
            visible_path,
            n_visible,
            "Framework-visible records WITH target labels, so the framework can self-evaluate "
            "with the official metric. Disjoint from the scoring set.",
        ),
        (
            "scoring",
            scoring_path,
            n_scoring,
            "Host-side scoring records. Never mounted into the framework container.",
        ),
    ):
        (output_root / name / "metadata.json").write_text(
            json.dumps(
                {
                    "topic_id": "arc_wbe_2026",
                    "format": "arc-wbe-2026-parquet",
                    "split": name,
                    "columns": list(SCORING_COLUMNS),
                    "n_rows": n_rows,
                    "weight_shape": [32, 256, 256],
                    "policy": policy,
                    "labels_exposed": name == "visible-validation",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "visible_count": n_visible,
                "scoring_count": n_scoring,
                "manifest": str(output_root / "split_manifest.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

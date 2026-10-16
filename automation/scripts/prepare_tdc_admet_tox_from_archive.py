#!/usr/bin/env python3
"""从官方归档重建 TDC-ADMET-Tox 的 public 数据集，**不需要 pytdc**。

为什么需要这个脚本
------------------
`SOURCE.md` 记录的划分协议是 `pytdc=1.1.15` + `create_scaffold_split(seed=42)`，
复现它要装 pytdc + 指定版本的 RDKit/NumPy/Python —— 一条随时会崩的依赖链，
对参赛者是不可接受的入门成本。

本脚本改用**行号**重建：官方归档 `admet_group.zip` 已被 sha256 冻结
（`bd000524…`），因此 `train_val.csv` / `test.csv` 的行号是稳定唯一的键。
划分冻结在 `automation/tdc_admet_tox_split.canonical.json` 里。

`sample_id` 的生成规则（实测自 canonical 文件，重建结果**逐字节一致**）：

    {endpoint.upper()}_{tv|test}_{归档行号:06d}

注意 hERG 的 `endpoint` 列是 `hERG`，但 `sample_id` 前缀是 `HERG` —— 即
前缀一律取大写。用 `{ep}` 会得到 `hERG_tv_…`，与主办方的隐藏标签对不上，
predictions 会一行都匹配不到。

键的选择（踩过的坑）
--------------------
**不要用 Drug_ID 或 SMILES 当键。** hERG 的归档里有 21 行 `Drug_ID` 是空串
（其中 20 行在 train、1 行在 validation），另有 17 个重复 Drug_ID；SMILES 也有
同分子不同标签的情形。行号没有这些问题。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ENDPOINTS = ("AMES", "hERG", "DILI")
# 归档目录名（小写）与 endpoint 名的映射
ARCHIVE_DIR = {"AMES": "ames", "hERG": "herg", "DILI": "dili"}
SPLIT_FILE = (
    Path(__file__).resolve().parents[1] / "tdc_admet_tox_split.canonical.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild TDC-ADMET-Tox public CSVs from the official Dataverse archive."
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        required=True,
        help="解压后的 admet_group 目录（内含 ames/ herg/ dili/）",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--split-file", type=Path, default=SPLIT_FILE)
    return parser.parse_args()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def require_columns(rows: list[dict[str, str]], path: Path, want: set[str]) -> None:
    if not rows:
        raise SystemExit(f"{path} is empty")
    missing = want - set(rows[0])
    if missing:
        raise SystemExit(f"{path} 缺少列: {', '.join(sorted(missing))}")


def main() -> int:
    args = parse_args()
    raw_root = args.raw_root.resolve()
    output_root = args.output_root.resolve()
    split = json.loads(args.split_file.read_text(encoding="utf-8"))
    validation_rows = split["validation_rows"]

    public = output_root / "public"
    # 只拒绝已存在的 public/ —— output_root 本身可能已被 setup_datasets.sh
    # 的 .cache 目录创建（那边用 mkdir -p 建缓存），不该因此失败。
    if public.exists():
        raise SystemExit(f"refusing to overwrite an existing dataset: {public}")
    public.mkdir(parents=True)

    written: dict[str, dict[str, object]] = {}
    counts: dict[str, dict[str, int]] = {}

    for endpoint in ENDPOINTS:
        arch_dir = raw_root / ARCHIVE_DIR[endpoint]
        train_val_path = arch_dir / "train_val.csv"
        test_path = arch_dir / "test.csv"
        if not train_val_path.is_file() or not test_path.is_file():
            raise SystemExit(f"归档缺少 {endpoint} 的文件: {arch_dir}")

        train_val = read_rows(train_val_path)
        test = read_rows(test_path)
        require_columns(train_val, train_val_path, {"Drug", "Y"})
        require_columns(test, test_path, {"Drug", "Y"})

        val_idx = set(validation_rows[endpoint])
        if not val_idx or max(val_idx) >= len(train_val):
            raise SystemExit(f"{endpoint} 的 validation_rows 越界或为空")

        prefix = endpoint.upper()  # hERG -> HERG
        rows_train, rows_val, rows_test = [], [], []
        for i, row in enumerate(train_val):
            sid = f"{prefix}_tv_{i:06d}"
            record = [sid, endpoint, row["Drug"], int(float(row["Y"]))]
            (rows_val if i in val_idx else rows_train).append(record)
        for i, row in enumerate(test):
            # 公开的 test 不带标签 —— 标签由主办方持有，用于统一评分
            rows_test.append([f"{prefix}_test_{i:06d}", endpoint, row["Drug"]])

        written["train.csv"] = written.get("train.csv", []) + rows_train
        written["validation.csv"] = written.get("validation.csv", []) + rows_val
        written["test.csv"] = written.get("test.csv", []) + rows_test
        counts[endpoint] = {"train": len(rows_train), "validation": len(rows_val), "test": len(rows_test)}

    for name, header in (
        ("train.csv", ["sample_id", "endpoint", "smiles", "label"]),
        ("validation.csv", ["sample_id", "endpoint", "smiles", "label"]),
        ("test.csv", ["sample_id", "endpoint", "smiles"]),
    ):
        path = public / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(written[name])

    # 冻结清单：参赛者据此自证拿到的数据是同一份
    manifest = {
        "task_id": "tdc_admet_tox",
        "source": "TDC ADMET Group / Tox normalized export",
        "source_revision": split["source_revision"],
        "archive_sha256": split["archive_sha256"],
        "normalized_source_manifest": {
            "sha256": split["archive_sha256"],
            "source_revision": split["source_revision"],
        },
        "split_file": args.split_file.name,
        "split_file_sha256": sha256_of(args.split_file),
        "sample_id_rule": split["sample_id_rule"],
        "counts": counts,
        "files": {
            name: {
                "sha256": sha256_of(public / name),
                "n_rows": sum(counts[e][name.split(".")[0]] for e in ENDPOINTS),
            }
            for name in ("train.csv", "validation.csv", "test.csv")
        },
        "labels": {
            "public": ["train.csv", "validation.csv"],
            "test_labels": "held by the organizers; test.csv carries no label column",
        },
    }
    (public / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "output_root": str(public),
                "counts": counts,
                "manifest": str(public / "dataset_manifest.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", required=True)
    return parser.parse_args()


def build_metadata(raw_dataset_root: Path, split: str, dataset) -> dict[str, object]:
    info_path = raw_dataset_root / "dataset_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    from whestbench._provenance import flopscope_version, whestbench_version
    from whestbench.hardware import collect_hardware_fingerprint

    return {
        "schema_version": "3.0",
        "format": "hf-datasets-parquet",
        "backend": "flopscope",
        "seed_protocol": {
            "name": "whestbench_explicit_per_mlp_seeds",
            "version": "3.0",
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": split,
        "config": "default" if split == "mini" else split,
        "default_split": "mini",
        "n_mlps": len(dataset),
        "n_samples": 0,
        "width": 256,
        "depth": 32,
        "hardware": collect_hardware_fingerprint(),
        "whestbench_version": whestbench_version(),
        "flopscope_version": flopscope_version(),
        "source": {
            "kind": "researchclaweval_hf_export",
            "raw_dataset_root": str(raw_dataset_root),
            "dataset_info": info,
        },
    }


def main() -> int:
    args = parse_args()

    from datasets import load_from_disk
    from whestbench.dataset_io import write_dataset_dir

    dataset = load_from_disk(str(args.raw_dataset_root))
    metadata = build_metadata(args.raw_dataset_root, args.split, dataset)
    write_dataset_dir(dataset, output_dir=args.output_dir, split=args.split, metadata=metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

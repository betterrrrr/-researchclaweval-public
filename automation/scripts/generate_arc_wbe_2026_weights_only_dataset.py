#!/usr/bin/env python3
"""Create framework-visible ARC-WBE records with weights but no target labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_COLUMNS = ("mlp_id", "mlp_name", "mlp_seed", "weights")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    source_data = source_root / "data"
    source_files = sorted(source_data.glob("*.parquet"))
    if not source_files:
        raise SystemExit(f"no parquet files under {source_data}")
    if output_root.exists():
        raise SystemExit(f"refusing to reuse existing framework dataset: {output_root}")

    import pyarrow.parquet as pq

    output_root.mkdir(parents=True)
    output_data = output_root / "data"
    output_data.mkdir()
    row_count = 0
    writer = None
    for source_file in source_files:
        parquet_file = pq.ParquetFile(source_file)
        missing = [name for name in ALLOWED_COLUMNS if name not in parquet_file.schema_arrow.names]
        if missing:
            raise SystemExit(f"source dataset is missing required columns: {', '.join(missing)}")
        batches = parquet_file.iter_batches(columns=list(ALLOWED_COLUMNS), batch_size=4)
        for batch in batches:
            if writer is None:
                writer = pq.ParquetWriter(
                    output_data / "arc_wbe_2026_weights-00000-of-00001.parquet",
                    batch.schema,
                    compression="zstd",
                )
            writer.write_batch(batch)
            row_count += batch.num_rows
    if writer is None:
        raise SystemExit("no parquet records were found")
    writer.close()

    source_metadata = source_root / "metadata.json"
    split = "mini"
    if source_metadata.exists():
        try:
            split = str(json.loads(source_metadata.read_text(encoding="utf-8")).get("split", split))
        except json.JSONDecodeError:
            pass
    metadata = {
        "topic_id": "arc_wbe_2026",
        "format": "framework-weights-only-parquet",
        "split": split,
        "allowed_columns": list(ALLOWED_COLUMNS),
        "n_rows": row_count,
        "weight_shape": [32, 256, 256],
        "policy": "Framework-visible parquet contains real weights-only records; all_layer_means, final_means, avg_variance, and sampling metadata remain host-side.",
        "labels_exposed": False,
    }
    (output_root / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

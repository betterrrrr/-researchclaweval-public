#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_ID = "aicrowd/arc-whestbench-public-2026"
DATASET_REVISION = "v1-phase1"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "arc_white_box_estimation_2026"
DEFAULT_HF_HOME = REPO_ROOT / "data" / ".cache" / "arc_wbe_2026_hf"
DEFAULT_SPLITS = ("mini",)
DEFAULT_BAKE_SPLITS: tuple[str, ...] = ()
MANIFEST_NAME = "materialization_manifest.json"
BAKED_SUBDIR = "baked"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def parse_splits(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_SPLITS
    parts = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not parts:
        raise ValueError("at least one split is required")
    return parts


def raw_split_dir(output_root: Path, split: str) -> Path:
    if split == "full":
        return output_root / "arc-whestbench-full"
    return output_root / split


def baked_split_dir(output_root: Path, split: str) -> Path:
    return output_root / BAKED_SUBDIR / split


def default_whest_python() -> str:
    env_value = os.environ.get("ARC_WBE_2026_WHEST_PYTHON")
    if env_value:
        return env_value
    preferred = Path("/tmp/whest-starterkit/.venv/bin/python")
    if preferred.exists():
        return str(preferred)
    return shutil.which("python3") or "python3"


def build_materialization_manifest(
    output_root: Path,
    hf_home: Path,
    splits: Iterable[str],
    bake_splits: Iterable[str] = (),
) -> dict[str, object]:
    requested_bakes = set(bake_splits)
    split_rows = {
        split: {
            "raw_path": str(raw_split_dir(output_root, split)),
            "raw_materialized": raw_split_dir(output_root, split).exists(),
            "baked_path": str(baked_split_dir(output_root, split)),
            "baked_materialized": baked_split_dir(output_root, split).exists(),
            "requested_bake": split in requested_bakes,
        }
        for split in splits
    }
    return {
        "topic_id": "arc_wbe_2026",
        "dataset_id": DATASET_ID,
        "dataset_revision": DATASET_REVISION,
        "output_root": str(output_root),
        "hf_home": str(hf_home),
        "splits": split_rows,
        "updated_at": now_iso(),
    }


def write_manifest(output_root: Path, manifest: dict[str, object]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def materialize_split(output_root: Path, hf_home: Path, split: str) -> None:
    target = raw_split_dir(output_root, split)
    if target.exists():
        return
    os.environ["HF_HOME"] = str(hf_home)
    from datasets import load_dataset  # lazy import to keep local tests dependency-light

    if split == "full":
        dataset = load_dataset(DATASET_ID, "full", revision=DATASET_REVISION, split="full")
    else:
        dataset = load_dataset(DATASET_ID, revision=DATASET_REVISION, split=split)
    dataset.save_to_disk(str(target))


def bake_split(output_root: Path, split: str, whest_python: str) -> None:
    raw_root = raw_split_dir(output_root, split)
    baked_root = baked_split_dir(output_root, split)
    if baked_root.exists():
        return
    if not raw_root.exists():
        raise FileNotFoundError(f"raw split is missing for bake: {raw_root}")
    helper = Path(__file__).with_name("bake_arc_wbe_2026_dataset_with_whestbench.py")
    subprocess.run(
        [
            whest_python,
            str(helper),
            "--raw-dataset-root",
            str(raw_root),
            "--output-dir",
            str(baked_root),
            "--split",
            split,
        ],
        check=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--hf-home", type=Path, default=DEFAULT_HF_HOME)
    parser.add_argument("--splits", type=str, default=",".join(DEFAULT_SPLITS))
    parser.add_argument("--bake-splits", type=str, default=",".join(DEFAULT_BAKE_SPLITS))
    parser.add_argument("--whest-python", default=default_whest_python())
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    splits = parse_splits(args.splits)
    bake_splits = parse_splits(args.bake_splits) if args.bake_splits else ()
    args.hf_home.mkdir(parents=True, exist_ok=True)
    args.output_root.mkdir(parents=True, exist_ok=True)

    if not args.dry_run:
        for split in splits:
            materialize_split(output_root=args.output_root, hf_home=args.hf_home, split=split)
        for split in bake_splits:
            bake_split(output_root=args.output_root, split=split, whest_python=args.whest_python)

    manifest = build_materialization_manifest(
        output_root=args.output_root,
        hf_home=args.hf_home,
        splits=splits,
        bake_splits=bake_splits,
    )
    manifest_path = write_manifest(args.output_root, manifest)
    print(
        json.dumps(
            {
                "topic": "arc_wbe_2026",
                "dataset_id": DATASET_ID,
                "revision": DATASET_REVISION,
                "output_root": str(args.output_root),
                "hf_home": str(args.hf_home),
                "splits": list(splits),
                "bake_splits": list(bake_splits),
                "manifest": str(manifest_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

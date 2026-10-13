#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

TASK_ID = "tdc_admet_tox"
PYTDC_VERSION = "1.1.15"
PYTDC_SDIST_SHA256 = "cd6164859af7b9b6f60e0c6d6e50679eacaffd09cfdea1acfc8bb7360e8e2205"
DATAVERSE_DATASET_PID = "doi:10.7910/DVN/21LKWG"
DATAVERSE_DATASET_VERSION = "V105"
DATAVERSE_FILE_ID = 4426004
ARCHIVE_SIZE = 1_472_501
ARCHIVE_MD5 = "e3e4dda2f7f62268448fc813ceefccd5"
ARCHIVE_SHA256 = "bd0005246cb6f1672333c28ad202112a8bf071ab65d847848715030308faf1f1"
RDKIT_VERSION = "2023.09.5"
SPLIT_SEED = 42
SPLIT_FRACTIONS = (0.875, 0.125, 0.0)
ENDPOINTS = {
    "AMES": "ames",
    "hERG": "herg",
    "DILI": "dili",
}
SOURCE_FIELDS = ["Drug_ID", "Drug", "Y"]
OUTPUT_FIELDS = ["sample_id", "smiles", "label"]


class ExportError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExportError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def digest_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive(path: Path) -> dict[str, str | int]:
    require(path.is_file(), f"official archive is missing: {path}")
    size = path.stat().st_size
    md5 = digest_file(path, "md5")
    sha256 = digest_file(path, "sha256")
    require(size == ARCHIVE_SIZE, f"official archive size mismatch: {size}")
    require(md5 == ARCHIVE_MD5, f"official archive MD5 mismatch: {md5}")
    require(sha256 == ARCHIVE_SHA256, f"official archive SHA-256 mismatch: {sha256}")
    return {"size": size, "md5": md5, "sha256": sha256}


def read_tdc_rows(path: Path, endpoint: str, source_split: str) -> list[dict[str, object]]:
    require(path.is_file(), f"official source file is missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == SOURCE_FIELDS, f"unexpected TDC schema in {path}")
        source_rows = list(reader)
    require(bool(source_rows), f"official source file is empty: {path}")

    rows: list[dict[str, object]] = []
    id_prefix = endpoint.replace("hERG", "HERG")
    source_code = "tv" if source_split == "train_val" else "test"
    for index, row in enumerate(source_rows):
        require(
            None not in row and all(value is not None for value in row.values()),
            f"malformed source row {index + 2} in {path}",
        )
        smiles = row["Drug"].strip()
        label_raw = row["Y"].strip()
        require(bool(smiles), f"empty SMILES at row {index + 2} in {path}")
        try:
            label_float = float(label_raw)
        except ValueError as exc:
            raise ExportError(f"invalid label at row {index + 2} in {path}") from exc
        require(label_float in {0.0, 1.0}, f"non-binary label at row {index + 2} in {path}")
        rows.append(
            {
                "sample_id": f"{id_prefix}_{source_code}_{index:06d}",
                "smiles": smiles,
                "label": int(label_float),
                "source_row": index,
                "source_drug_id": row["Drug_ID"],
            }
        )
    return rows


def split_rows_by_scaffold(
    rows: list[dict[str, object]],
    *,
    seed: int,
    scaffold_fn: Callable[[str], str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    scaffolds: defaultdict[str, set[int]] = defaultdict(set)
    omitted_indices: list[int] = []
    for index, row in enumerate(rows):
        try:
            scaffold = scaffold_fn(str(row["smiles"]))
            scaffolds[scaffold].add(index)
        except Exception:
            omitted_indices.append(index)

    usable_count = len(rows) - len(omitted_indices)
    train_size = int(usable_count * SPLIT_FRACTIONS[0])
    validation_size = int(usable_count * SPLIT_FRACTIONS[1])
    test_size = usable_count - train_size - validation_size

    big_index_sets: list[set[int]] = []
    small_index_sets: list[set[int]] = []
    for index_set in scaffolds.values():
        if len(index_set) > validation_size / 2 or len(index_set) > test_size / 2:
            big_index_sets.append(index_set)
        else:
            small_index_sets.append(index_set)

    rng = random.Random(seed)
    rng.shuffle(big_index_sets)
    rng.shuffle(small_index_sets)
    index_sets = big_index_sets + small_index_sets
    train_indices: list[int] = []
    validation_indices: list[int] = []
    test_indices: list[int] = []
    if SPLIT_FRACTIONS[2] == 0:
        for index_set in index_sets:
            if len(train_indices) + len(index_set) <= train_size:
                train_indices += index_set
            else:
                validation_indices += index_set
    else:
        for index_set in index_sets:
            if len(train_indices) + len(index_set) <= train_size:
                train_indices += index_set
            elif len(validation_indices) + len(index_set) <= validation_size:
                validation_indices += index_set
            else:
                test_indices += index_set

    return (
        [rows[index] for index in train_indices],
        [rows[index] for index in validation_indices],
        [rows[index] for index in omitted_indices + test_indices],
    )


def write_normalized_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def class_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    positive = sum(int(row["label"]) for row in rows)
    return {"records": len(rows), "positive": positive, "negative": len(rows) - positive}


def validate_binary_split(rows: list[dict[str, object]], endpoint: str, split: str) -> None:
    require({int(row["label"]) for row in rows} == {0, 1}, f"{endpoint} {split} is not binary")


def default_scaffold_fn() -> tuple[Callable[[str], str], str]:
    try:
        from rdkit import Chem, RDLogger
        from rdkit import __version__ as rdkit_version
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except ImportError as exc:
        raise ExportError("RDKit 2023.9.5 is required for official scaffold splitting") from exc
    require(rdkit_version == RDKIT_VERSION, f"expected RDKit {RDKIT_VERSION}, got {rdkit_version}")
    RDLogger.DisableLog("rdApp.*")

    def scaffold(smiles: str) -> str:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"RDKit rejected SMILES: {smiles}")
        return MurckoScaffold.MurckoScaffoldSmiles(mol=molecule, includeChirality=False)

    return scaffold, rdkit_version


def export_official_splits(
    *,
    archive_path: Path,
    benchmark_root: Path,
    output_root: Path,
    seed: int = SPLIT_SEED,
    scaffold_fn: Callable[[str], str] | None = None,
    rdkit_version: str | None = None,
) -> Path:
    archive_path = archive_path.resolve()
    benchmark_root = benchmark_root.resolve()
    output_root = output_root.resolve()
    archive = validate_archive(archive_path)
    require(benchmark_root.is_dir(), f"extracted admet_group root is missing: {benchmark_root}")
    if output_root.exists():
        require(output_root.is_dir(), f"output root is not a directory: {output_root}")
        require(
            not any(output_root.iterdir()),
            f"refusing to reuse non-empty output root: {output_root}",
        )
    if scaffold_fn is None:
        scaffold_fn, detected_rdkit_version = default_scaffold_fn()
        rdkit_version = detected_rdkit_version
    require(bool(rdkit_version), "RDKit version must be recorded")

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_endpoints: dict[str, object] = {}
    for endpoint, source_name in ENDPOINTS.items():
        endpoint_source = benchmark_root / source_name
        train_val_path = endpoint_source / "train_val.csv"
        test_path = endpoint_source / "test.csv"
        train_val_rows = read_tdc_rows(train_val_path, endpoint, "train_val")
        official_test_rows = read_tdc_rows(test_path, endpoint, "test")
        train_rows, validation_rows, omitted_rows = split_rows_by_scaffold(
            train_val_rows,
            seed=seed,
            scaffold_fn=scaffold_fn,
        )
        require(
            not omitted_rows, f"{endpoint} contains {len(omitted_rows)} invalid or unassigned rows"
        )
        for split_name, split_rows in (
            ("train", train_rows),
            ("validation", validation_rows),
            ("test", official_test_rows),
        ):
            validate_binary_split(split_rows, endpoint, split_name)

        endpoint_output = output_root / endpoint
        endpoint_output.mkdir()
        output_paths = {
            "train": endpoint_output / "train.csv",
            "validation": endpoint_output / "validation.csv",
            "test": endpoint_output / "test.csv",
        }
        write_normalized_csv(output_paths["train"], train_rows)
        write_normalized_csv(output_paths["validation"], validation_rows)
        write_normalized_csv(output_paths["test"], official_test_rows)
        manifest_endpoints[endpoint] = {
            "source_name": source_name,
            "source_files": {
                "train_val.csv": {"sha256": digest_file(train_val_path, "sha256")},
                "test.csv": {"sha256": digest_file(test_path, "sha256")},
            },
            "splits": {
                name: {
                    **class_counts(rows),
                    "sha256": digest_file(output_paths[name], "sha256"),
                }
                for name, rows in (
                    ("train", train_rows),
                    ("validation", validation_rows),
                    ("test", official_test_rows),
                )
            },
        }

    source_revision = (
        f"{DATAVERSE_DATASET_PID}@{DATAVERSE_DATASET_VERSION};file={DATAVERSE_FILE_ID};"
        f"pytdc={PYTDC_VERSION};split=scaffold;seed={seed};frac=0.875,0.125,0"
    )
    manifest = {
        "task_id": TASK_ID,
        "source_revision": source_revision,
        "dataverse": {
            "dataset_persistent_id": DATAVERSE_DATASET_PID,
            "dataset_version": DATAVERSE_DATASET_VERSION,
            "file_id": DATAVERSE_FILE_ID,
            "archive": archive,
        },
        "split_implementation": {
            "pytdc_version": PYTDC_VERSION,
            "pytdc_sdist_sha256": PYTDC_SDIST_SHA256,
            "function": "tdc.utils.create_scaffold_split",
            "seed": seed,
            "fractions": list(SPLIT_FRACTIONS),
            "rdkit_version": rdkit_version,
            "python_version": platform.python_version(),
        },
        "endpoints": manifest_endpoints,
        "created_at": now_iso(),
    }
    manifest_path = output_root / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export fixed official TDC ADMET toxicity splits.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = export_official_splits(
            archive_path=args.archive,
            benchmark_root=args.benchmark_root,
            output_root=args.output_root,
            seed=args.seed,
        )
    except ExportError as exc:
        print(json.dumps({"task_id": TASK_ID, "status": "failed", "error": str(exc)}))
        return 13
    print(
        json.dumps(
            {"task_id": TASK_ID, "status": "exported", "source_manifest": str(manifest)},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

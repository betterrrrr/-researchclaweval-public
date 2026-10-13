#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

TASK_ID = "tdc_admet_tox"
ENDPOINTS = ("AMES", "hERG", "DILI")
SPLITS = ("train", "validation", "test")
SOURCE_FIELDS = ["sample_id", "smiles", "label"]
PUBLIC_LABELED_FIELDS = ["sample_id", "endpoint", "smiles", "label"]
PUBLIC_TEST_FIELDS = ["sample_id", "endpoint", "smiles"]
HIDDEN_LABEL_FIELDS = ["sample_id", "endpoint", "label"]


class MaterializationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MaterializationError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paths_overlap(first: Path, second: Path) -> bool:
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def ensure_empty_target(path: Path, name: str) -> None:
    if path.exists():
        require(path.is_dir(), f"{name} exists and is not a directory: {path}")
        require(not any(path.iterdir()), f"refusing to reuse non-empty {name}: {path}")


def read_source(path: Path, endpoint: str, split: str) -> list[dict[str, object]]:
    require(path.is_file(), f"missing normalized source file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == SOURCE_FIELDS, f"invalid source schema in {path}")
        rows = list(reader)
    require(bool(rows), f"normalized source file has no rows: {path}")

    result: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        require(
            None not in row and all(value is not None for value in row.values()),
            f"malformed row in {path} row {row_number}",
        )
        sample_id = row["sample_id"].strip()
        smiles = row["smiles"].strip()
        label = row["label"].strip()
        require(bool(sample_id), f"empty sample_id in {path} row {row_number}")
        require(sample_id not in seen_ids, f"duplicate sample_id in {path}: {sample_id}")
        require(bool(smiles), f"empty SMILES in {path} row {row_number}")
        require(label in {"0", "1"}, f"label must be 0 or 1 in {path} row {row_number}")
        seen_ids.add(sample_id)
        result.append(
            {
                "sample_id": sample_id,
                "endpoint": endpoint,
                "smiles": smiles,
                "label": int(label),
                "split": split,
            }
        )
    labels = {int(row["label"]) for row in result}
    require(labels == {0, 1}, f"{endpoint} {split} must contain both binary classes")
    return result


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def counts(rows: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for endpoint in ENDPOINTS:
        endpoint_rows = [row for row in rows if row["endpoint"] == endpoint]
        result[endpoint] = {
            "records": len(endpoint_rows),
            "positive": sum(int(row["label"]) for row in endpoint_rows),
            "negative": sum(1 - int(row["label"]) for row in endpoint_rows),
        }
    return result


def materialize(
    source_root: Path,
    public_output_root: Path,
    hidden_output_root: Path,
    source_revision: str,
) -> tuple[Path, Path]:
    source_root = source_root.resolve()
    public_output_root = public_output_root.resolve()
    hidden_output_root = hidden_output_root.resolve()
    require(source_root.is_dir(), f"source root does not exist: {source_root}")
    require(
        not paths_overlap(public_output_root, hidden_output_root),
        "public and hidden output roots must be physically separate",
    )
    require(
        not paths_overlap(source_root, public_output_root)
        and not paths_overlap(source_root, hidden_output_root),
        "source and output roots must be physically separate",
    )
    ensure_empty_target(public_output_root, "public output root")
    ensure_empty_target(hidden_output_root, "hidden output root")

    normalized_manifest_path = source_root / "source_manifest.json"
    normalized_manifest: dict[str, object] | None = None
    if normalized_manifest_path.is_file():
        try:
            payload = json.loads(normalized_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MaterializationError("normalized source manifest is invalid JSON") from exc
        require(isinstance(payload, dict), "normalized source manifest must be an object")
        require(
            payload.get("task_id") == TASK_ID, "normalized source manifest has the wrong task_id"
        )
        require(
            payload.get("source_revision") == source_revision,
            "source revision does not match normalized source manifest",
        )
        normalized_manifest = {
            "sha256": sha256_file(normalized_manifest_path),
            "source_revision": payload["source_revision"],
        }

    by_split: dict[str, list[dict[str, object]]] = {split: [] for split in SPLITS}
    source_files: dict[str, dict[str, object]] = {}
    global_keys: set[tuple[str, str]] = set()
    for endpoint in ENDPOINTS:
        for split in SPLITS:
            source_path = source_root / endpoint / f"{split}.csv"
            rows = read_source(source_path, endpoint, split)
            for row in rows:
                key = (endpoint, str(row["sample_id"]))
                require(key not in global_keys, f"sample appears in more than one split: {key}")
                global_keys.add(key)
            by_split[split].extend(rows)
            source_files[f"{endpoint}/{split}.csv"] = {
                "sha256": sha256_file(source_path),
                "record_count": len(rows),
            }

    for rows in by_split.values():
        rows.sort(key=lambda row: (ENDPOINTS.index(str(row["endpoint"])), str(row["sample_id"])))

    public_output_root.mkdir(parents=True, exist_ok=True)
    hidden_output_root.mkdir(parents=True, exist_ok=True)
    train_path = public_output_root / "train.csv"
    validation_path = public_output_root / "validation.csv"
    test_path = public_output_root / "test.csv"
    hidden_labels_path = hidden_output_root / "test_labels.csv"
    write_csv(train_path, PUBLIC_LABELED_FIELDS, by_split["train"])
    write_csv(validation_path, PUBLIC_LABELED_FIELDS, by_split["validation"])
    write_csv(test_path, PUBLIC_TEST_FIELDS, by_split["test"])
    write_csv(hidden_labels_path, HIDDEN_LABEL_FIELDS, by_split["test"])

    public_manifest = {
        "task_id": TASK_ID,
        "source": "TDC ADMET Group / Tox normalized export",
        "source_revision": source_revision,
        "normalized_source_manifest": normalized_manifest,
        "source_files": source_files,
        "splits": {
            "train": counts(by_split["train"]),
            "validation": counts(by_split["validation"]),
            "test": {
                endpoint: {"records": row["records"]}
                for endpoint, row in counts(by_split["test"]).items()
            },
        },
        "files": {
            "train.csv": {"sha256": sha256_file(train_path)},
            "validation.csv": {"sha256": sha256_file(validation_path)},
            "test.csv": {"sha256": sha256_file(test_path)},
        },
        "created_at": now_iso(),
    }
    public_manifest_path = public_output_root / "dataset_manifest.json"
    public_manifest_path.write_text(
        json.dumps(public_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )

    hidden_manifest = {
        "task_id": TASK_ID,
        "visibility": "host_only",
        "source_revision": source_revision,
        "normalized_source_manifest": normalized_manifest,
        "test_labels": {
            "sha256": sha256_file(hidden_labels_path),
            "record_count": len(by_split["test"]),
            "counts": counts(by_split["test"]),
        },
        "public_test_sha256": sha256_file(test_path),
        "created_at": now_iso(),
    }
    hidden_manifest_path = hidden_output_root / "hidden_manifest.json"
    hidden_manifest_path.write_text(
        json.dumps(hidden_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )

    public_output_root.parent.chmod(0o755)
    public_output_root.chmod(0o755)
    for path in (train_path, validation_path, test_path, public_manifest_path):
        path.chmod(0o444)
    hidden_output_root.chmod(0o700)
    hidden_labels_path.chmod(0o600)
    hidden_manifest_path.chmod(0o600)
    return public_manifest_path, hidden_manifest_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project normalized TDC endpoint splits into public data and host-only test labels."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--public-output-root", type=Path, required=True)
    parser.add_argument("--hidden-output-root", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        public_manifest, hidden_manifest = materialize(
            args.source_root,
            args.public_output_root,
            args.hidden_output_root,
            args.source_revision,
        )
    except MaterializationError as exc:
        print(json.dumps({"task_id": TASK_ID, "status": "failed", "error": str(exc)}))
        return 13
    print(
        json.dumps(
            {
                "task_id": TASK_ID,
                "status": "materialized",
                "public_manifest": str(public_manifest),
                "hidden_manifest": str(hidden_manifest),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_dataset(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"dataset is not a list: {path}")
    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("id"), str) or not isinstance(item.get("dialogue_id"), str):
            continue
        if not isinstance(item.get("label"), int):
            continue
        rows.append(item)
    if not rows:
        raise SystemExit(f"dataset has no usable rows: {path}")
    return rows


def load_split_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"split manifest is not an object: {path}")
    return payload


def load_predictions(path: Path) -> dict[str, int]:
    if path.suffix.lower() == ".jsonl":
        predictions: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            item_id = payload.get("id")
            label = payload.get("predicted_label", payload.get("label"))
            if isinstance(item_id, str) and isinstance(label, int):
                predictions[item_id] = label
        return predictions

    if path.suffix.lower() == ".csv":
        predictions = {}
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                item_id = row.get("id")
                label_raw = row.get("predicted_label") or row.get("label")
                if not item_id or label_raw is None:
                    continue
                try:
                    predictions[item_id] = int(label_raw)
                except ValueError:
                    continue
        return predictions

    raise SystemExit(f"unsupported prediction artifact: {path}")


def macro_f1(gold: list[int], pred: list[int], labels: list[int]) -> float:
    f1_values: list[float] = []
    for label in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        if precision + recall == 0:
            f1_values.append(0.0)
        else:
            f1_values.append(2 * precision * recall / (precision + recall))
    return sum(f1_values) / len(f1_values)


def accuracy(gold: list[int], pred: list[int]) -> float:
    return sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score PsyDefDetect predictions with the standardized split.")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output-score", required=True)
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root).resolve()
    split_manifest = Path(args.split_manifest).resolve()
    prediction_path = Path(args.predictions).resolve()
    output_score = Path(args.output_score).resolve()

    rows = load_dataset(dataset_root / "PsyDefConv.json")
    split = load_split_manifest(split_manifest)
    eval_ids = split.get("eval_record_ids")
    if not isinstance(eval_ids, list) or not all(isinstance(item, str) for item in eval_ids):
        raise SystemExit("split manifest missing eval_record_ids")
    eval_id_set = set(eval_ids)

    predictions = load_predictions(prediction_path)
    gold_rows = [row for row in rows if row["id"] in eval_id_set]
    if len(gold_rows) != len(eval_id_set):
        raise SystemExit("dataset/split mismatch: some eval ids are missing from dataset")

    missing = sorted(eval_id_set - set(predictions))
    if missing:
        raise SystemExit(f"prediction artifact is missing {len(missing)} eval ids")

    gold = [row["label"] for row in gold_rows]
    pred = [predictions[row["id"]] for row in gold_rows]
    macro_f1_all = macro_f1(gold, pred, list(range(9)))
    macro_f1_positive = macro_f1(gold, pred, list(range(1, 9)))

    payload = {
        "psydefdetect_score": macro_f1_positive,
        "score_key": "psydefdetect_score",
        "official_metric_implemented": "macro-F1 over labels 1-8, excluding label 0",
        "macro_f1_positive_1_8": macro_f1_positive,
        "macro_f1_all_0_8": macro_f1_all,
        "accuracy": accuracy(gold, pred),
        "eval_record_count": len(gold_rows),
        "prediction_artifact": str(prediction_path),
        "split_manifest": str(split_manifest),
    }
    output_score.parent.mkdir(parents=True, exist_ok=True)
    output_score.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

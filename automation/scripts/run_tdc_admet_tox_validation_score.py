#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

TASK_ID = "tdc_admet_tox"
ENDPOINTS = ("AMES", "hERG", "DILI")
LABEL_FIELDS = ("sample_id", "endpoint", "smiles", "label")
PREDICTION_FIELDS = ("sample_id", "endpoint", "probability")
LABELED_PREDICTION_FIELDS = (*PREDICTION_FIELDS, "label")


def fail(message: str) -> None:
    raise SystemExit(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        fail(f"CSV file does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(fields):
            fail(f"invalid CSV schema for {path}: expected {list(fields)}")
        rows = list(reader)
    if not rows:
        fail(f"CSV file has no rows: {path}")
    return rows


def key(row: dict[str, str], path: Path, row_number: int) -> tuple[str, str]:
    sample_id = row["sample_id"].strip()
    endpoint = row["endpoint"].strip()
    if not sample_id or endpoint not in ENDPOINTS:
        fail(f"invalid key in {path} row {row_number}")
    return sample_id, endpoint


def load_labels(path: Path) -> dict[tuple[str, str], int]:
    labels: dict[tuple[str, str], int] = {}
    for row_number, row in enumerate(read_rows(path, LABEL_FIELDS), start=2):
        row_key = key(row, path, row_number)
        if row_key in labels:
            fail(f"duplicate validation key in {path}: {row_key}")
        if row["label"] not in {"0", "1"}:
            fail(f"validation label must be 0 or 1 in row {row_number}")
        if not row["smiles"].strip():
            fail(f"empty validation SMILES in row {row_number}")
        labels[row_key] = int(row["label"])
    return labels


def load_predictions(path: Path) -> dict[tuple[str, str], float]:
    predictions: dict[tuple[str, str], float] = {}
    if not path.is_file():
        fail(f"CSV file does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames not in (list(PREDICTION_FIELDS), list(LABELED_PREDICTION_FIELDS)):
            fail(
                f"invalid validation prediction schema for {path}: "
                f"expected {list(PREDICTION_FIELDS)} with optional label"
            )
        rows = list(reader)
    if not rows:
        fail(f"CSV file has no rows: {path}")
    for row_number, row in enumerate(rows, start=2):
        row_key = key(row, path, row_number)
        if row_key in predictions:
            fail(f"duplicate prediction key in {path}: {row_key}")
        try:
            probability = float(row["probability"])
        except ValueError:
            fail(f"invalid probability in row {row_number}")
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            fail(f"probability outside [0, 1] in row {row_number}")
        predictions[row_key] = probability
    return predictions


def auroc(labels: list[int], probabilities: list[float]) -> float:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        fail("AUROC requires both classes for every endpoint")
    ordered = sorted(zip(probabilities, labels), key=lambda item: item[0])
    positive_rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        positive_rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    statistic = positive_rank_sum - positives * (positives + 1) / 2.0
    return statistic / (positives * negatives)


def average_precision(labels: list[int], probabilities: list[float]) -> float:
    positives = sum(labels)
    if positives == 0:
        fail("average precision requires a positive label for every endpoint")
    ordered = sorted(zip(probabilities, labels), key=lambda item: item[0], reverse=True)
    true_positives = 0
    false_positives = 0
    previous_recall = 0.0
    result = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        group = ordered[index:end]
        group_positives = sum(label for _, label in group)
        true_positives += group_positives
        false_positives += len(group) - group_positives
        recall = true_positives / positives
        precision = true_positives / (true_positives + false_positives)
        result += (recall - previous_recall) * precision
        previous_recall = recall
        index = end
    return result


def brier_score(labels: list[int], probabilities: list[float]) -> float:
    return sum((probability - label) ** 2 for label, probability in zip(labels, probabilities)) / len(labels)


def calibration_error(labels: list[int], probabilities: list[float], bins: int = 10) -> float:
    grouped: list[list[tuple[int, float]]] = [[] for _ in range(bins)]
    for label, probability in zip(labels, probabilities):
        grouped[min(bins - 1, int(probability * bins))].append((label, probability))
    result = 0.0
    for rows in grouped:
        if not rows:
            continue
        observed = sum(label for label, _ in rows) / len(rows)
        predicted = sum(probability for _, probability in rows) / len(rows)
        result += len(rows) / len(labels) * abs(observed - predicted)
    return result


def score(
    labels: dict[tuple[str, str], int], predictions: dict[tuple[str, str], float]
) -> dict[str, object]:
    if set(labels) != set(predictions):
        fail(
            "validation predictions do not match labeled validation keys: "
            f"missing={len(set(labels) - set(predictions))}, "
            f"extra={len(set(predictions) - set(labels))}"
        )
    per_endpoint: dict[str, dict[str, float | int]] = {}
    for endpoint in ENDPOINTS:
        keys = sorted(item for item in labels if item[1] == endpoint)
        endpoint_labels = [labels[item] for item in keys]
        endpoint_probabilities = [predictions[item] for item in keys]
        per_endpoint[endpoint] = {
            "n": len(keys),
            "positive_count": sum(endpoint_labels),
            "auroc": auroc(endpoint_labels, endpoint_probabilities),
            "auprc_average_precision": average_precision(
                endpoint_labels, endpoint_probabilities
            ),
            "brier_score": brier_score(endpoint_labels, endpoint_probabilities),
            "ece_10_bin": calibration_error(endpoint_labels, endpoint_probabilities),
        }
    return {
        "task_id": TASK_ID,
        "split": "validation",
        "primary_metric": "macro_average_auroc",
        "macro_average_auroc": sum(
            float(per_endpoint[endpoint]["auroc"]) for endpoint in ENDPOINTS
        )
        / len(ENDPOINTS),
        "macro_average_auprc": sum(
            float(per_endpoint[endpoint]["auprc_average_precision"])
            for endpoint in ENDPOINTS
        )
        / len(ENDPOINTS),
        "macro_average_brier_score": sum(
            float(per_endpoint[endpoint]["brier_score"]) for endpoint in ENDPOINTS
        )
        / len(ENDPOINTS),
        "macro_average_ece_10_bin": sum(
            float(per_endpoint[endpoint]["ece_10_bin"]) for endpoint in ENDPOINTS
        )
        / len(ENDPOINTS),
        "per_endpoint": per_endpoint,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score TDC-ADMET-Tox validation predictions.")
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-metrics", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validation = args.validation.resolve()
    predictions = args.predictions.resolve()
    output = args.output_metrics.resolve()
    if output in {validation, predictions}:
        fail("output metrics must not overwrite an input")
    payload = score(load_labels(validation), load_predictions(predictions))
    payload["artifacts"] = {
        "validation_sha256": sha256_file(validation),
        "predictions_sha256": sha256_file(predictions),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

TASK_ID = "tdc_admet_tox"
SCORER_VERSION = "1"
ENDPOINTS = ("AMES", "hERG", "DILI")
TEST_FIELDS = ("sample_id", "endpoint", "smiles")
PREDICTION_FIELDS = ("sample_id", "endpoint", "probability")
LABEL_FIELDS = ("sample_id", "endpoint", "label")


def fail(message: str) -> None:
    raise SystemExit(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def read_csv(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        fail(f"CSV file does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(expected_fields):
            fail(
                f"invalid CSV schema for {path}: expected {list(expected_fields)}, "
                f"got {reader.fieldnames}"
            )
        rows = list(reader)
    for row_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            fail(f"malformed CSV row in {path} row {row_number}")
    if not rows:
        fail(f"CSV file has no data rows: {path}")
    return rows


def parse_key(row: dict[str, str], path: Path, row_number: int) -> tuple[str, str]:
    sample_id = row["sample_id"].strip()
    endpoint = row["endpoint"].strip()
    if not sample_id:
        fail(f"empty sample_id in {path} row {row_number}")
    if endpoint not in ENDPOINTS:
        fail(f"invalid endpoint {endpoint!r} in {path} row {row_number}")
    return sample_id, endpoint


def load_test_keys(path: Path) -> set[tuple[str, str]]:
    rows = read_csv(path, TEST_FIELDS)
    keys: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        key = parse_key(row, path, row_number)
        if key in keys:
            fail(f"duplicate public test key {key!r} in {path}")
        if not row["smiles"].strip():
            fail(f"empty SMILES in {path} row {row_number}")
        keys.add(key)
    return keys


def load_predictions(path: Path) -> dict[tuple[str, str], float]:
    rows = read_csv(path, PREDICTION_FIELDS)
    predictions: dict[tuple[str, str], float] = {}
    for row_number, row in enumerate(rows, start=2):
        key = parse_key(row, path, row_number)
        if key in predictions:
            fail(f"duplicate prediction key {key!r} in {path}")
        try:
            probability = float(row["probability"])
        except ValueError:
            fail(f"invalid probability in {path} row {row_number}")
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            fail(f"probability outside [0, 1] in {path} row {row_number}")
        predictions[key] = probability
    return predictions


def load_labels(path: Path) -> dict[tuple[str, str], int]:
    rows = read_csv(path, LABEL_FIELDS)
    labels: dict[tuple[str, str], int] = {}
    for row_number, row in enumerate(rows, start=2):
        key = parse_key(row, path, row_number)
        if key in labels:
            fail(f"duplicate hidden-label key {key!r} in {path}")
        if row["label"] not in {"0", "1"}:
            fail(f"hidden label must be 0 or 1 in {path} row {row_number}")
        labels[key] = int(row["label"])
    return labels


def require_same_keys(
    test_keys: set[tuple[str, str]],
    predictions: dict[tuple[str, str], float],
    labels: dict[tuple[str, str], int],
) -> None:
    for name, keys in (("predictions", set(predictions)), ("hidden labels", set(labels))):
        missing = test_keys - keys
        extra = keys - test_keys
        if missing or extra:
            fail(
                f"{name} do not match public test keys: missing={len(missing)}, extra={len(extra)}"
            )


def auroc(labels: list[int], probabilities: list[float]) -> float:
    positive_count = sum(labels)
    negative_count = len(labels) - positive_count
    if positive_count == 0 or negative_count == 0:
        fail("AUROC requires both positive and negative labels for every endpoint")

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

    u_statistic = positive_rank_sum - positive_count * (positive_count + 1) / 2.0
    return u_statistic / (positive_count * negative_count)


def average_precision(labels: list[int], probabilities: list[float]) -> float:
    positive_count = sum(labels)
    if positive_count == 0:
        fail("AUPRC requires at least one positive label for every endpoint")

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
        true_positives += sum(label for _, label in group)
        false_positives += len(group) - sum(label for _, label in group)
        recall = true_positives / positive_count
        precision = true_positives / (true_positives + false_positives)
        result += (recall - previous_recall) * precision
        previous_recall = recall
        index = end
    return result


def brier_score(labels: list[int], probabilities: list[float]) -> float:
    return sum(
        (probability - label) ** 2 for label, probability in zip(labels, probabilities)
    ) / len(labels)


def expected_calibration_error(
    labels: list[int], probabilities: list[float], bin_count: int = 10
) -> float:
    bins: list[list[tuple[int, float]]] = [[] for _ in range(bin_count)]
    for label, probability in zip(labels, probabilities):
        bin_index = min(bin_count - 1, int(probability * bin_count))
        bins[bin_index].append((label, probability))

    result = 0.0
    for rows in bins:
        if not rows:
            continue
        mean_label = sum(label for label, _ in rows) / len(rows)
        mean_probability = sum(probability for _, probability in rows) / len(rows)
        result += len(rows) / len(labels) * abs(mean_label - mean_probability)
    return result


def score(
    test_keys: set[tuple[str, str]],
    predictions: dict[tuple[str, str], float],
    labels: dict[tuple[str, str], int],
) -> tuple[dict[str, dict[str, float | int]], dict[str, float]]:
    per_endpoint: dict[str, dict[str, float | int]] = {}
    for endpoint in ENDPOINTS:
        endpoint_keys = sorted(key for key in test_keys if key[1] == endpoint)
        endpoint_labels = [labels[key] for key in endpoint_keys]
        endpoint_probabilities = [predictions[key] for key in endpoint_keys]
        if not endpoint_keys:
            fail(f"public test data has no rows for endpoint {endpoint}")
        per_endpoint[endpoint] = {
            "auroc": auroc(endpoint_labels, endpoint_probabilities),
            "auprc_average_precision": average_precision(endpoint_labels, endpoint_probabilities),
            "brier_score": brier_score(endpoint_labels, endpoint_probabilities),
            "ece_10_bin": expected_calibration_error(endpoint_labels, endpoint_probabilities),
            "record_count": len(endpoint_keys),
            "positive_count": sum(endpoint_labels),
            "negative_count": len(endpoint_labels) - sum(endpoint_labels),
        }

    macro = {
        "macro_average_auroc": sum(float(per_endpoint[e]["auroc"]) for e in ENDPOINTS) / 3.0,
        "macro_average_auprc": sum(
            float(per_endpoint[e]["auprc_average_precision"]) for e in ENDPOINTS
        )
        / 3.0,
        "macro_average_brier_score": sum(float(per_endpoint[e]["brier_score"]) for e in ENDPOINTS)
        / 3.0,
        "macro_average_ece_10_bin": sum(float(per_endpoint[e]["ece_10_bin"]) for e in ENDPOINTS)
        / 3.0,
    }
    return per_endpoint, macro


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Host-score TDC-ADMET-Tox hidden test labels.")
    parser.add_argument("--public-dataset-root", type=Path, required=True)
    parser.add_argument("--hidden-labels", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-score", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    public_root = args.public_dataset_root.resolve()
    hidden_labels_path = args.hidden_labels.resolve()
    predictions_path = args.predictions.resolve()
    output_score = args.output_score.resolve()
    public_test_path = public_root / "test.csv"

    if not public_root.is_dir():
        fail(f"public dataset root does not exist: {public_root}")
    if is_relative_to(hidden_labels_path, public_root):
        fail("hidden labels must not be located under the public dataset root")
    if hidden_labels_path == predictions_path:
        fail("hidden labels and predictions must be separate files")
    if output_score in {hidden_labels_path, predictions_path, public_test_path}:
        fail("output score must not overwrite an input artifact")

    test_keys = load_test_keys(public_test_path)
    predictions = load_predictions(predictions_path)
    labels = load_labels(hidden_labels_path)
    require_same_keys(test_keys, predictions, labels)
    per_endpoint, macro = score(test_keys, predictions, labels)

    payload = {
        "task_id": TASK_ID,
        "score_source": "host_hidden_test_labels",
        "primary_metric": "macro_average_auroc",
        "main_score": macro["macro_average_auroc"],
        "macro_average_auroc": macro["macro_average_auroc"],
        "per_endpoint": per_endpoint,
        "secondary_metrics": {
            "macro_average_auprc": macro["macro_average_auprc"],
            "macro_average_brier_score": macro["macro_average_brier_score"],
            "macro_average_ece_10_bin": macro["macro_average_ece_10_bin"],
            "scorer_runtime_seconds": time.monotonic() - started,
        },
        "record_count": len(test_keys),
        "artifacts": {
            "public_test": {"sha256": sha256_file(public_test_path)},
            "predictions": {"sha256": sha256_file(predictions_path)},
            "hidden_labels": {"sha256": sha256_file(hidden_labels_path)},
        },
        "scorer": {
            "name": Path(__file__).name,
            "version": SCORER_VERSION,
        },
    }
    output_score.parent.mkdir(parents=True, exist_ok=True)
    output_score.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

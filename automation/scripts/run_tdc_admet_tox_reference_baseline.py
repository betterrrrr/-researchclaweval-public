#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

TASK_ID = "tdc_admet_tox"
ENDPOINTS = ("AMES", "hERG", "DILI")
SEED = 42
RESOURCE_BUDGET = {
    "cpu_cores": 4,
    "memory_gib": 16,
    "gpu_count": 0,
    "workspace_disk_gib": 10,
    "max_experiment_runtime_seconds": 3600,
    "max_total_wall_seconds": 7200,
    "network_policy": "injected_llm_relay_only",
}
CONFIGURATIONS = (
    {
        "run_id": "run_001",
        "hypothesis": "A compact Morgan fingerprint provides a reproducible nonlinear structure basis.",
        "model_strategy": "endpoint_logistic_regression_unweighted",
        "feature_strategy": "morgan_radius_2_1024_bits",
        "radius": 2,
        "n_bits": 1024,
        "c": 1.0,
        "class_weight": None,
    },
    {
        "run_id": "run_002",
        "hypothesis": "More fingerprint capacity and balanced loss improve minority-sensitive ranking.",
        "model_strategy": "endpoint_logistic_regression_balanced",
        "feature_strategy": "morgan_radius_2_2048_bits",
        "radius": 2,
        "n_bits": 2048,
        "c": 1.0,
        "class_weight": "balanced",
    },
)


class BaselineError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BaselineError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dependencies():
    try:
        import numpy as np
        import rdkit
        import sklearn
        from rdkit import Chem, DataStructs, RDLogger
        from rdkit.Chem import rdFingerprintGenerator
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise BaselineError("RDKit, NumPy, and scikit-learn are required") from exc
    RDLogger.DisableLog("rdApp.*")
    return np, rdkit, sklearn, Chem, DataStructs, rdFingerprintGenerator, LogisticRegression


def read_public_csv(path: Path, labeled: bool) -> list[dict[str, object]]:
    expected = ["sample_id", "endpoint", "smiles"] + (["label"] if labeled else [])
    require(path.is_file(), f"public input is missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == expected, f"invalid public schema in {path}")
        raw_rows = list(reader)
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for row_number, row in enumerate(raw_rows, start=2):
        require(
            None not in row and all(value is not None for value in row.values()),
            f"bad row {row_number}",
        )
        endpoint = row["endpoint"].strip()
        sample_id = row["sample_id"].strip()
        smiles = row["smiles"].strip()
        require(
            endpoint in ENDPOINTS and sample_id and smiles, f"invalid row {row_number} in {path}"
        )
        key = (sample_id, endpoint)
        require(key not in seen, f"duplicate key in {path}: {key}")
        seen.add(key)
        normalized: dict[str, object] = {
            "sample_id": sample_id,
            "endpoint": endpoint,
            "smiles": smiles,
        }
        if labeled:
            require(row["label"] in {"0", "1"}, f"invalid label in {path} row {row_number}")
            normalized["label"] = int(row["label"])
        rows.append(normalized)
    require(bool(rows), f"public input is empty: {path}")
    return rows


def featurize(smiles_values: list[str], radius: int, n_bits: int, dependencies) -> object:
    np, _, _, Chem, DataStructs, rdFingerprintGenerator, _ = dependencies
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=n_bits)
    matrix = np.zeros((len(smiles_values), n_bits), dtype=np.uint8)
    for index, smiles in enumerate(smiles_values):
        molecule = Chem.MolFromSmiles(smiles)
        require(molecule is not None, f"RDKit rejected public SMILES: {smiles}")
        fingerprint = generator.GetFingerprint(molecule)
        DataStructs.ConvertToNumpyArray(fingerprint, matrix[index])
    return matrix


def auroc(labels: list[int], probabilities: list[float]) -> float:
    positives = sum(labels)
    negatives = len(labels) - positives
    require(positives > 0 and negatives > 0, "AUROC requires both classes")
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
    u_statistic = positive_rank_sum - positives * (positives + 1) / 2.0
    return u_statistic / (positives * negatives)


def average_precision(labels: list[int], probabilities: list[float]) -> float:
    positives = sum(labels)
    require(positives > 0, "average precision requires a positive class")
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
    return sum(
        (probability - label) ** 2 for label, probability in zip(labels, probabilities)
    ) / len(labels)


def expected_calibration_error(labels: list[int], probabilities: list[float]) -> float:
    bins: list[list[tuple[int, float]]] = [[] for _ in range(10)]
    for label, probability in zip(labels, probabilities):
        bins[min(9, int(probability * 10))].append((label, probability))
    result = 0.0
    for rows in bins:
        if rows:
            mean_label = sum(label for label, _ in rows) / len(rows)
            mean_probability = sum(probability for _, probability in rows) / len(rows)
            result += len(rows) / len(labels) * abs(mean_label - mean_probability)
    return result


def metric_payload(rows: list[dict[str, object]]) -> dict[str, object]:
    per_endpoint: dict[str, dict[str, float | int]] = {}
    for endpoint in ENDPOINTS:
        endpoint_rows = [row for row in rows if row["endpoint"] == endpoint]
        labels = [int(row["label"]) for row in endpoint_rows]
        probabilities = [float(row["probability"]) for row in endpoint_rows]
        per_endpoint[endpoint] = {
            "auroc": auroc(labels, probabilities),
            "auprc_average_precision": average_precision(labels, probabilities),
            "brier_score": brier_score(labels, probabilities),
            "ece_10_bin": expected_calibration_error(labels, probabilities),
            "record_count": len(endpoint_rows),
        }
    return {
        "split": "validation",
        "macro_average_auroc": sum(float(per_endpoint[e]["auroc"]) for e in ENDPOINTS) / 3.0,
        "macro_average_auprc": sum(
            float(per_endpoint[e]["auprc_average_precision"]) for e in ENDPOINTS
        )
        / 3.0,
        "macro_average_brier_score": sum(float(per_endpoint[e]["brier_score"]) for e in ENDPOINTS)
        / 3.0,
        "macro_average_ece_10_bin": sum(float(per_endpoint[e]["ece_10_bin"]) for e in ENDPOINTS)
        / 3.0,
        "per_endpoint": per_endpoint,
    }


def write_predictions(
    path: Path, rows: list[dict[str, object]], include_label: bool = False
) -> None:
    fields = ["sample_id", "endpoint", "probability"] + (["label"] if include_label else [])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def fit_predict_configuration(
    configuration: dict[str, object],
    train_rows: list[dict[str, object]],
    prediction_rows: list[dict[str, object]],
    dependencies,
) -> list[dict[str, object]]:
    _, _, _, _, _, _, LogisticRegression = dependencies
    result: list[dict[str, object]] = []
    for endpoint in ENDPOINTS:
        endpoint_train = [row for row in train_rows if row["endpoint"] == endpoint]
        endpoint_prediction = [row for row in prediction_rows if row["endpoint"] == endpoint]
        train_features = featurize(
            [str(row["smiles"]) for row in endpoint_train],
            int(configuration["radius"]),
            int(configuration["n_bits"]),
            dependencies,
        )
        prediction_features = featurize(
            [str(row["smiles"]) for row in endpoint_prediction],
            int(configuration["radius"]),
            int(configuration["n_bits"]),
            dependencies,
        )
        model = LogisticRegression(
            C=float(configuration["c"]),
            class_weight=configuration["class_weight"],
            max_iter=1000,
            random_state=SEED,
            solver="liblinear",
        )
        model.fit(train_features, [int(row["label"]) for row in endpoint_train])
        probabilities = model.predict_proba(prediction_features)[:, 1]
        for row, probability in zip(endpoint_prediction, probabilities):
            output = {
                "sample_id": row["sample_id"],
                "endpoint": endpoint,
                "probability": float(probability),
            }
            if "label" in row:
                output["label"] = row["label"]
            result.append(output)
    return result


def run_baseline(public_root: Path, output_root: Path) -> Path:
    started = time.monotonic()
    public_root = public_root.resolve()
    output_root = output_root.resolve()
    require(public_root.is_dir(), f"public dataset root is missing: {public_root}")
    if output_root.exists():
        require(output_root.is_dir(), f"output root is not a directory: {output_root}")
        require(
            not any(output_root.iterdir()),
            f"refusing to reuse non-empty output root: {output_root}",
        )
    dependencies = load_dependencies()
    np, rdkit, sklearn, _, _, _, _ = dependencies
    require(rdkit.__version__ == "2023.09.5", f"unexpected RDKit version: {rdkit.__version__}")
    require(np.__version__ == "1.26.4", f"unexpected NumPy version: {np.__version__}")
    require(
        sklearn.__version__ == "1.5.2", f"unexpected scikit-learn version: {sklearn.__version__}"
    )

    train_path = public_root / "train.csv"
    validation_path = public_root / "validation.csv"
    test_path = public_root / "test.csv"
    train_rows = read_public_csv(train_path, labeled=True)
    validation_rows = read_public_csv(validation_path, labeled=True)
    test_rows = read_public_csv(test_path, labeled=False)

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "runs").mkdir()
    (output_root / "logs").mkdir()
    experiments: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    paper_rows: list[str] = []
    for configuration in CONFIGURATIONS:
        experiment_started = time.monotonic()
        run_id = str(configuration["run_id"])
        run_root = output_root / "runs" / run_id
        run_root.mkdir()
        config_path = run_root / "config.json"
        prediction_path = run_root / "validation_predictions.csv"
        metrics_path = run_root / "metrics.json"
        log_path = run_root / "train.log"
        config_payload = {
            **configuration,
            "seed": SEED,
            "candidate_count": 1,
            "input_hashes": {
                "train.csv": sha256_file(train_path),
                "validation.csv": sha256_file(validation_path),
            },
        }
        config_path.write_text(
            json.dumps(config_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
        validation_predictions = fit_predict_configuration(
            configuration, train_rows, validation_rows, dependencies
        )
        write_predictions(prediction_path, validation_predictions, include_label=True)
        metrics = metric_payload(validation_predictions)
        metrics_path.write_text(
            json.dumps(metrics, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
        runtime_seconds = time.monotonic() - experiment_started
        log_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": "complete",
                    "runtime_seconds": runtime_seconds,
                    "macro_average_auroc": metrics["macro_average_auroc"],
                },
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )
        experiment = {
            "run_id": run_id,
            "status": "complete",
            "hypothesis": configuration["hypothesis"],
            "model_strategy": configuration["model_strategy"],
            "feature_strategy": configuration["feature_strategy"],
            "config_file": str(config_path.relative_to(output_root)),
            "prediction_file": str(prediction_path.relative_to(output_root)),
            "metrics_file": str(metrics_path.relative_to(output_root)),
            "log_file": str(log_path.relative_to(output_root)),
            "runtime_seconds": runtime_seconds,
            "seed": SEED,
            "candidate_count": 1,
            "validation_metrics": {
                "macro_average_auroc": metrics["macro_average_auroc"],
                "per_endpoint": metrics["per_endpoint"],
            },
        }
        experiments.append(experiment)

        row_values: list[str] = []
        for endpoint in (*ENDPOINTS, "macro"):
            value = (
                float(metrics["macro_average_auroc"])
                if endpoint == "macro"
                else float(metrics["per_endpoint"][endpoint]["auroc"])
            )
            claim_id = f"table1_{run_id}_{endpoint.lower()}_auroc"
            claims.append(
                {
                    "claim_id": claim_id,
                    "endpoint": endpoint,
                    "metric": "AUROC",
                    "value": value,
                    "source_run_id": run_id,
                    "prediction_file": experiment["prediction_file"],
                    "config_file": experiment["config_file"],
                    "log_file": experiment["log_file"],
                }
            )
            row_values.append(f"{value:.6f} <!-- claim:{claim_id} -->")
        paper_rows.append(
            "| {name} | {ames} | {herg} | {dili} | {macro} |".format(
                name="Baseline A" if run_id == "run_001" else "Baseline B",
                ames=row_values[0],
                herg=row_values[1],
                dili=row_values[2],
                macro=row_values[3],
            )
        )

    selected = max(
        experiments, key=lambda row: float(row["validation_metrics"]["macro_average_auroc"])
    )
    selected_configuration = next(
        configuration
        for configuration in CONFIGURATIONS
        if configuration["run_id"] == selected["run_id"]
    )
    refit_rows = train_rows + validation_rows
    test_predictions = fit_predict_configuration(
        selected_configuration, refit_rows, test_rows, dependencies
    )
    write_predictions(output_root / "predictions.csv", test_predictions)

    shutil.copy2(Path(__file__).resolve(), output_root / "reproduce.py")
    environment = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "device": "cpu",
        "seeds": [SEED],
        "packages": {
            "numpy": np.__version__,
            "rdkit": rdkit.__version__,
            "scikit-learn": sklearn.__version__,
        },
        "created_at": now_iso(),
    }
    (output_root / "environment.json").write_text(
        json.dumps(environment, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    total_wall_seconds = time.monotonic() - started
    trace = {
        "task_id": TASK_ID,
        "reference_non_ranking": True,
        "experiments": experiments,
        "selected_experiment_id": selected["run_id"],
        "selection_metric": "validation_macro_average_auroc",
        "final_prediction_file": "predictions.csv",
        "reproduction": {
            "entrypoint": "reproduce.py",
            "command": (
                "python3 reproduce.py --public-dataset-root /data/tdc_admet_tox/public "
                "--output-root ./reproduced"
            ),
            "seed": SEED,
        },
        "environment_file": "environment.json",
        "resource_budget": RESOURCE_BUDGET,
        "total_wall_seconds": total_wall_seconds,
        "claims": claims,
    }
    (output_root / "experiment_trace.json").write_text(
        json.dumps(trace, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    paper = "\n".join(
        [
            "# TDC-ADMET-Tox Reference Baseline",
            "",
            "This non-ranking infrastructure baseline compares two fixed molecular classifiers on the public validation split. It is not evidence for any research framework.",
            "",
            "| Configuration | AMES AUROC | hERG AUROC | DILI AUROC | Macro AUROC |",
            "|---|---:|---:|---:|---:|",
            *paper_rows,
            "",
            "The selected configuration is refit on public train plus validation data. Hidden test labels were unavailable during this workflow.",
            "",
        ]
    )
    (output_root / "paper.md").write_text(paper, encoding="utf-8")
    (output_root / "logs" / "baseline.log").write_text(
        json.dumps(
            {
                "status": "complete",
                "reference_non_ranking": True,
                "selected_experiment_id": selected["run_id"],
                "total_wall_seconds": total_wall_seconds,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return output_root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the non-ranking TDC-ADMET-Tox reference baseline."
    )
    parser.add_argument("--public-dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output_root = run_baseline(args.public_dataset_root, args.output_root)
    except BaselineError as exc:
        print(json.dumps({"task_id": TASK_ID, "status": "failed", "error": str(exc)}))
        return 13
    print(
        json.dumps(
            {
                "task_id": TASK_ID,
                "status": "complete",
                "reference_non_ranking": True,
                "output_root": str(output_root),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

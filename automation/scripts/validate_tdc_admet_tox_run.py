#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

TASK_ID = "tdc_admet_tox"
ENDPOINTS = ("AMES", "hERG", "DILI")
EXPECTED_RESOURCE_BUDGET = {
    "cpu_cores": 4,
    "memory_gib": 16,
    "gpu_count": 0,
    "workspace_disk_gib": 10,
    "max_experiment_runtime_seconds": 3600,
    "max_total_wall_seconds": 7200,
    "network_policy": "injected_llm_relay_only",
}
PREDICTION_FIELDS = ["sample_id", "endpoint", "probability"]
PUBLIC_TEST_FIELDS = ["sample_id", "endpoint", "smiles"]
CLAIM_MARKER = re.compile(r"<!--\s*claim:([A-Za-z0-9_.:-]+)\s*-->")
NUMBER = re.compile(r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?%?")
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
EMPIRICAL_TERM = re.compile(
    r"\b(?:auroc|auprc|average precision|brier|calibration|ece|runtime|seconds?|score|improv(?:e|ed|ement))\b",
    re.IGNORECASE,
)


class AuditError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def read_json(path: Path) -> dict:
    require(path.is_file(), f"required JSON file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read JSON file {path}: {exc}") from exc
    require(isinstance(payload, dict), f"JSON root must be an object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_artifact(root: Path, raw: object, field: str) -> Path:
    require(isinstance(raw, str) and raw.strip(), f"{field} must be a non-empty relative path")
    path = Path(raw)
    require(not path.is_absolute(), f"{field} must be relative to the run workspace")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AuditError(f"{field} escapes the run workspace") from exc
    require(resolved.is_file(), f"{field} does not exist: {path}")
    return resolved


def validate_predictions(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == PREDICTION_FIELDS, "predictions.csv has an invalid schema")
        seen: set[tuple[str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            sample_id = row["sample_id"].strip()
            endpoint = row["endpoint"].strip()
            require(bool(sample_id), f"empty prediction sample_id at row {row_number}")
            require(endpoint in ENDPOINTS, f"invalid prediction endpoint at row {row_number}")
            key = (sample_id, endpoint)
            require(key not in seen, f"duplicate prediction key at row {row_number}: {key}")
            seen.add(key)
            try:
                probability = float(row["probability"])
            except ValueError as exc:
                raise AuditError(f"invalid probability at row {row_number}") from exc
            require(
                math.isfinite(probability) and 0.0 <= probability <= 1.0,
                f"probability outside [0, 1] at row {row_number}",
            )
    require(bool(seen), "predictions.csv has no rows")
    require(
        {endpoint for _, endpoint in seen} == set(ENDPOINTS), "predictions.csv misses an endpoint"
    )
    return len(seen)


def validate_prediction_keys(path: Path, public_dataset_root: Path) -> None:
    test_path = public_dataset_root / "test.csv"
    require(test_path.is_file(), f"public test.csv is missing: {test_path}")
    with test_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == PUBLIC_TEST_FIELDS, "public test.csv has an invalid schema")
        expected = {(row["sample_id"].strip(), row["endpoint"].strip()) for row in reader}
    with path.open("r", encoding="utf-8", newline="") as handle:
        actual = {
            (row["sample_id"].strip(), row["endpoint"].strip())
            for row in csv.DictReader(handle)
        }
    require(actual == expected, "predictions.csv keys do not exactly match public test.csv")


def validate_environment(root: Path, trace: dict) -> Path:
    path = resolve_artifact(root, trace.get("environment_file"), "environment_file")
    payload = read_json(path)
    required_fields = ("python_version", "platform", "device", "seeds", "packages", "created_at")
    for field in required_fields:
        require(payload.get(field) not in (None, "", [], {}), f"environment.json missing {field}")
    return path


def endpoint_metrics(payload: object, field: str) -> dict:
    require(isinstance(payload, dict), f"{field} must be an object")
    require(set(payload) >= set(ENDPOINTS), f"{field} must contain all endpoints")
    for endpoint in ENDPOINTS:
        row = payload[endpoint]
        require(isinstance(row, dict), f"{field}.{endpoint} must be an object")
        require(is_number(row.get("auroc")), f"{field}.{endpoint}.auroc must be numeric")
    return payload


def is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def contains_test_metric(value: object) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if (
                normalized == "test"
                or normalized.startswith("test_")
                or normalized.endswith("_test")
            ):
                return True
            if contains_test_metric(nested):
                return True
    elif isinstance(value, list):
        return any(contains_test_metric(item) for item in value)
    elif isinstance(value, str):
        return value.lower() in {"test", "hidden_test", "final_test"}
    return False


def validate_experiments(
    root: Path, trace: dict
) -> tuple[dict[str, dict], dict[str, dict[str, Path]]]:
    experiments = trace.get("experiments")
    require(isinstance(experiments, list), "experiments must be a list")
    require(2 <= len(experiments) <= 4, "exactly 2 to 4 complete experiments are required")

    by_id: dict[str, dict] = {}
    paths_by_id: dict[str, dict[str, Path]] = {}
    config_hashes: set[str] = set()
    strategy_signatures: set[tuple[str, str]] = set()
    for index, experiment in enumerate(experiments, start=1):
        require(isinstance(experiment, dict), f"experiment {index} must be an object")
        run_id = experiment.get("run_id")
        require(isinstance(run_id, str) and run_id.strip(), f"experiment {index} has no run_id")
        require(run_id not in by_id, f"duplicate experiment run_id: {run_id}")
        require(experiment.get("status") == "complete", f"experiment {run_id} is not complete")
        for field in ("hypothesis", "model_strategy", "feature_strategy"):
            require(
                isinstance(experiment.get(field), str) and experiment[field].strip(),
                f"experiment {run_id} has no {field}",
            )
        require(is_number(experiment.get("runtime_seconds")), f"experiment {run_id} has no runtime")
        require(isinstance(experiment.get("seed"), int), f"experiment {run_id} has no integer seed")
        require(
            experiment.get("candidate_count") == 1,
            f"experiment {run_id} must contain one candidate",
        )

        resolved_paths = {
            field: resolve_artifact(root, experiment.get(field), f"experiments.{run_id}.{field}")
            for field in ("config_file", "prediction_file", "metrics_file", "log_file")
        }
        metrics_file = read_json(resolved_paths["metrics_file"])
        require(
            metrics_file.get("split") == "validation",
            f"experiment {run_id} metrics are not validation",
        )
        require(not contains_test_metric(metrics_file), f"experiment {run_id} exposes test metrics")

        metrics = experiment.get("validation_metrics")
        require(isinstance(metrics, dict), f"experiment {run_id} has no validation_metrics")
        require(
            is_number(metrics.get("macro_average_auroc")),
            f"experiment {run_id} has no validation macro AUROC",
        )
        endpoint_metrics(
            metrics.get("per_endpoint"), f"experiments.{run_id}.validation_metrics.per_endpoint"
        )
        require(
            metric_values_match(metrics, metrics_file),
            f"experiment {run_id} trace metrics do not match its metrics_file",
        )

        if index >= 3:
            parent = experiment.get("parent_run_id")
            require(parent in by_id, f"experiment {run_id} has no valid prior parent_run_id")
            require(
                isinstance(experiment.get("change_rationale"), str)
                and experiment["change_rationale"].strip(),
                f"experiment {run_id} has no evidence-based change_rationale",
            )

        config_hashes.add(sha256_file(resolved_paths["config_file"]))
        strategy_signatures.add((experiment["model_strategy"], experiment["feature_strategy"]))
        by_id[run_id] = experiment
        paths_by_id[run_id] = resolved_paths

    require(len(config_hashes) >= 2, "at least two experiments must have distinct config content")
    require(
        len(strategy_signatures) >= 2, "at least two experiments must declare distinct strategies"
    )
    total_experiment_runtime = sum(float(row["runtime_seconds"]) for row in by_id.values())
    require(total_experiment_runtime <= 3600, "cumulative experiment runtime exceeds 3600 seconds")
    return by_id, paths_by_id


def metric_values_match(trace_metrics: dict, file_metrics: dict) -> bool:
    if file_metrics.get("macro_average_auroc") != trace_metrics.get("macro_average_auroc"):
        return False
    trace_endpoint = trace_metrics.get("per_endpoint")
    file_endpoint = file_metrics.get("per_endpoint")
    if not isinstance(trace_endpoint, dict) or not isinstance(file_endpoint, dict):
        return False
    for endpoint in ENDPOINTS:
        trace_row = trace_endpoint.get(endpoint)
        file_row = file_endpoint.get(endpoint)
        if not isinstance(trace_row, dict) or not isinstance(file_row, dict):
            return False
        for metric, value in trace_row.items():
            if is_number(value) and file_row.get(metric) != value:
                return False
    return True


def metric_value_for_claim(claim: dict, experiment: dict, metrics_file: dict) -> float:
    endpoint = claim.get("endpoint")
    metric = claim.get("metric")
    require(
        endpoint in (*ENDPOINTS, "macro"), f"claim {claim.get('claim_id')} has invalid endpoint"
    )
    require(isinstance(metric, str) and metric, f"claim {claim.get('claim_id')} has no metric")
    normalized = metric.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "auroc": "auroc",
        "auprc": "auprc_average_precision",
        "average_precision": "auprc_average_precision",
        "brier": "brier_score",
        "brier_score": "brier_score",
        "ece": "ece_10_bin",
        "ece_10_bin": "ece_10_bin",
    }
    if normalized == "runtime_seconds":
        return float(experiment["runtime_seconds"])
    require(
        normalized in aliases, f"claim {claim.get('claim_id')} uses unsupported metric {metric}"
    )
    key = aliases[normalized]
    if endpoint == "macro":
        macro_keys = {
            "auroc": "macro_average_auroc",
            "auprc_average_precision": "macro_average_auprc",
            "brier_score": "macro_average_brier_score",
            "ece_10_bin": "macro_average_ece_10_bin",
        }
        macro_key = macro_keys[key]
        value = metrics_file.get(macro_key)
    else:
        per_endpoint = metrics_file.get("per_endpoint")
        value = per_endpoint.get(endpoint, {}).get(key) if isinstance(per_endpoint, dict) else None
    require(is_number(value), f"claim {claim.get('claim_id')} metric is absent from metrics_file")
    return float(value)


def validate_claims(
    root: Path,
    trace: dict,
    experiments: dict[str, dict],
    paths_by_id: dict[str, dict[str, Path]],
) -> dict[str, dict]:
    claims = trace.get("claims")
    require(isinstance(claims, list), "claims must be a list")
    require(bool(claims), "at least one evidence-backed quantitative claim is required")
    by_id: dict[str, dict] = {}
    for index, claim in enumerate(claims, start=1):
        require(isinstance(claim, dict), f"claim {index} must be an object")
        claim_id = claim.get("claim_id")
        require(isinstance(claim_id, str) and claim_id.strip(), f"claim {index} has no claim_id")
        require(
            CLAIM_MARKER.fullmatch(f"<!-- claim:{claim_id} -->") is not None,
            f"invalid claim_id: {claim_id}",
        )
        require(claim_id not in by_id, f"duplicate claim_id: {claim_id}")
        run_id = claim.get("source_run_id")
        require(run_id in experiments, f"claim {claim_id} references an unknown source_run_id")
        require(is_number(claim.get("value")), f"claim {claim_id} value must be numeric")

        experiment = experiments[run_id]
        experiment_paths = paths_by_id[run_id]
        for claim_field, experiment_field in (
            ("prediction_file", "prediction_file"),
            ("config_file", "config_file"),
            ("log_file", "log_file"),
        ):
            claim_path = resolve_artifact(
                root, claim.get(claim_field), f"claims.{claim_id}.{claim_field}"
            )
            require(
                claim_path == experiment_paths[experiment_field],
                f"claim {claim_id} {claim_field} does not match source experiment",
            )

        metrics_file = read_json(experiment_paths["metrics_file"])
        source_value = metric_value_for_claim(claim, experiment, metrics_file)
        require(
            math.isclose(float(claim["value"]), source_value, rel_tol=0.0, abs_tol=1e-12),
            f"claim {claim_id} value does not match source metrics",
        )
        by_id[claim_id] = claim
    return by_id


def table_rows(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    result: list[str] = []
    index = 0
    while index + 1 < len(lines):
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if "|" not in header or "|" not in separator:
            index += 1
            continue
        separator_cells = [cell.strip() for cell in separator.strip("|").split("|")]
        if not separator_cells or not all(
            TABLE_SEPARATOR_CELL.fullmatch(cell) for cell in separator_cells
        ):
            index += 1
            continue
        row_index = index + 2
        while row_index < len(lines) and "|" in lines[row_index]:
            result.append(lines[row_index])
            row_index += 1
        index = row_index
    return result


def displayed_value_matches(raw: str, source_value: float) -> bool:
    percentage = raw.endswith("%")
    numeric = raw[:-1] if percentage else raw
    displayed = float(numeric)
    if percentage:
        displayed /= 100.0
    mantissa = numeric.lower().split("e", 1)[0]
    decimals = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
    tolerance = 0.5 * (10**-decimals)
    if percentage:
        tolerance /= 100.0
    return math.isclose(displayed, source_value, rel_tol=0.0, abs_tol=tolerance + 1e-15)


def validate_paper(root: Path, claims: dict[str, dict]) -> tuple[Path, int]:
    paper = root / "paper.md"
    if not paper.is_file():
        require((root / "paper.pdf").is_file(), "paper.md or paper.pdf is required")
        paper = root / "paper_claims.md"
        require(paper.is_file(), "PDF-only submissions require paper_claims.md")
    markdown = paper.read_text(encoding="utf-8")
    referenced = set(CLAIM_MARKER.findall(markdown))
    unknown = referenced - set(claims)
    require(not unknown, f"paper references unknown claim ids: {sorted(unknown)}")
    require(set(claims) <= referenced, "every trace claim must be referenced by the paper")

    checked_numbers = 0
    for row in table_rows(markdown):
        for cell in row.strip().strip("|").split("|"):
            numbers = NUMBER.findall(CLAIM_MARKER.sub("", cell))
            if not numbers:
                continue
            markers = CLAIM_MARKER.findall(cell)
            require(markers, f"numeric paper table cell has no claim marker: {cell.strip()}")
            source_values = [float(claims[claim_id]["value"]) for claim_id in markers]
            for raw_number in numbers:
                require(
                    any(displayed_value_matches(raw_number, value) for value in source_values),
                    f"paper table value {raw_number} does not match its claim marker",
                )
                checked_numbers += 1

    in_code_block = False
    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or "|" in line or not EMPIRICAL_TERM.search(line):
            continue
        numbers = NUMBER.findall(CLAIM_MARKER.sub("", line))
        if not numbers:
            continue
        markers = CLAIM_MARKER.findall(line)
        require(markers, f"quantitative paper prose has no claim marker: {line.strip()}")
        source_values = [float(claims[claim_id]["value"]) for claim_id in markers]
        for raw_number in numbers:
            require(
                any(displayed_value_matches(raw_number, value) for value in source_values),
                f"paper prose value {raw_number} does not match its claim marker",
            )
            checked_numbers += 1
    return paper, checked_numbers


def reject_hidden_label_artifacts(root: Path) -> None:
    forbidden = re.compile(r"(?:hidden.*labels?|test.*labels?|labels?.*test)", re.IGNORECASE)
    hits = [
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and forbidden.search(path.name)
    ]
    require(not hits, f"framework workspace contains possible hidden test labels: {hits}")


def reject_cross_topic_or_private_markers(paths: set[Path]) -> None:
    forbidden = re.compile(
        r"(?:babylm|gave2|arc_wbe_2026|arc-wbe-2026|psydefdetect|"
        r"TDC_ADMET_TOX_HIDDEN_LABELS_ROOT|test_labels[.]csv)",
        re.IGNORECASE,
    )
    hits: list[str] = []
    for path in sorted(paths):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = forbidden.search(text)
        if match:
            hits.append(f"{path}: {match.group(0)}")
    require(not hits, f"framework outputs contain cross-topic or private-label markers: {hits}")


def validate_reproduction(root: Path, trace: dict) -> Path:
    reproduction = trace.get("reproduction")
    require(isinstance(reproduction, dict), "reproduction must be an object")
    entrypoint = resolve_artifact(root, reproduction.get("entrypoint"), "reproduction.entrypoint")
    require(
        isinstance(reproduction.get("command"), str) and reproduction["command"].strip(),
        "reproduction.command is required",
    )
    require(isinstance(reproduction.get("seed"), int), "reproduction.seed must be an integer")
    return entrypoint


def validate_final_score(root: Path, predictions: Path) -> dict:
    score_path = root / "score.json"
    score = read_json(score_path)
    require(score.get("task_id") == TASK_ID, "score.json has the wrong task_id")
    require(
        score.get("score_source") == "host_hidden_test_labels", "score.json is not host-produced"
    )
    require(
        score.get("primary_metric") == "macro_average_auroc",
        "score.json has the wrong primary metric",
    )
    require(is_number(score.get("main_score")), "score.json has no numeric main_score")
    artifacts = score.get("artifacts")
    prediction_row = artifacts.get("predictions") if isinstance(artifacts, dict) else None
    require(isinstance(prediction_row, dict), "score.json has no prediction provenance")
    require(
        prediction_row.get("sha256") == sha256_file(predictions),
        "score.json prediction hash does not match predictions.csv",
    )
    per_endpoint = score.get("per_endpoint")
    require(
        isinstance(per_endpoint, dict) and set(per_endpoint) == set(ENDPOINTS),
        "score endpoint set is invalid",
    )
    endpoint_scores = []
    for endpoint in ENDPOINTS:
        endpoint_row = per_endpoint[endpoint]
        require(isinstance(endpoint_row, dict), f"score endpoint {endpoint} is not an object")
        require(is_number(endpoint_row.get("auroc")), f"score lacks {endpoint} AUROC")
        endpoint_scores.append(float(endpoint_row["auroc"]))
    expected_main = sum(endpoint_scores) / 3.0
    require(
        math.isclose(float(score["main_score"]), expected_main, rel_tol=0.0, abs_tol=1e-12),
        "score main_score is not the macro average AUROC",
    )
    return score


def audit(root: Path, stage: str, public_dataset_root: Path | None = None) -> dict:
    root = root.resolve()
    require(root.is_dir(), f"run workspace does not exist: {root}")
    reject_hidden_label_artifacts(root)

    predictions = root / "predictions.csv"
    require(predictions.is_file(), "root-level predictions.csv is required")
    prediction_count = validate_predictions(predictions)
    if public_dataset_root is not None:
        validate_prediction_keys(predictions, public_dataset_root.resolve())
    trace = read_json(root / "experiment_trace.json")
    require(trace.get("task_id") == TASK_ID, "experiment_trace.json has the wrong task_id")
    require(
        trace.get("framework_native_execution") is True,
        "experiment_trace.json must set framework_native_execution=true",
    )
    require(
        trace.get("consumed_topic_input") is True,
        "experiment_trace.json must set consumed_topic_input=true",
    )
    for field in ("framework_internal_model", "framework_internal_api_base_url"):
        require(
            isinstance(trace.get(field), str) and trace[field].strip(),
            f"experiment_trace.json must include non-empty {field}",
        )
    require(
        trace.get("selection_metric") == "validation_macro_average_auroc",
        "selection must use validation macro average AUROC",
    )
    require(
        trace.get("final_prediction_file") == "predictions.csv",
        "final_prediction_file must be predictions.csv",
    )
    require(
        trace.get("resource_budget") == EXPECTED_RESOURCE_BUDGET,
        "resource_budget does not match contract",
    )
    require(is_number(trace.get("total_wall_seconds")), "total_wall_seconds must be numeric")
    require(
        float(trace["total_wall_seconds"]) <= 7200,
        "total framework wall time exceeds 7200 seconds",
    )

    experiments, paths_by_id = validate_experiments(root, trace)
    selected_id = trace.get("selected_experiment_id")
    require(
        selected_id in experiments, "selected_experiment_id does not name a complete experiment"
    )
    selected_score = float(experiments[selected_id]["validation_metrics"]["macro_average_auroc"])
    best_score = max(
        float(row["validation_metrics"]["macro_average_auroc"]) for row in experiments.values()
    )
    require(
        math.isclose(selected_score, best_score, rel_tol=0.0, abs_tol=1e-12),
        "selected experiment is not best by validation macro AUROC",
    )

    environment = validate_environment(root, trace)
    entrypoint = validate_reproduction(root, trace)
    claims = validate_claims(root, trace, experiments, paths_by_id)
    paper, checked_table_numbers = validate_paper(root, claims)

    authored_paths = {root / "experiment_trace.json", environment, paper}
    for experiment_paths in paths_by_id.values():
        authored_paths.update(experiment_paths.values())
    reject_cross_topic_or_private_markers(authored_paths)

    logs_dir = root / "logs"
    require(
        logs_dir.is_dir() and any(path.is_file() for path in logs_dir.rglob("*")),
        "logs directory is empty",
    )

    score_path = root / "score.json"
    if stage == "framework":
        require(not score_path.exists(), "framework stage must not contain score.json")
        score = None
    else:
        score = validate_final_score(root, predictions)

    return {
        "task_id": TASK_ID,
        "stage": stage,
        "status": "passed",
        "workspace": str(root),
        "experiment_count": len(experiments),
        "selected_experiment_id": selected_id,
        "prediction_count": prediction_count,
        "claim_count": len(claims),
        "checked_paper_table_numbers": checked_table_numbers,
        "paper": str(paper.relative_to(root)),
        "environment": str(environment.relative_to(root)),
        "entrypoint": str(entrypoint.relative_to(root)),
        "main_score": score.get("main_score") if score else None,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit a TDC-ADMET-Tox framework handoff.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--stage", choices=("framework", "final"), required=True)
    parser.add_argument("--public-dataset-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = audit(args.workspace, args.stage, args.public_dataset_root)
    except AuditError as exc:
        print(
            json.dumps(
                {"task_id": TASK_ID, "stage": args.stage, "status": "failed", "error": str(exc)}
            )
        )
        return 13
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

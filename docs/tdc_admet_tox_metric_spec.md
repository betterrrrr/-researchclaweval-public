# TDC-ADMET-Tox Metric Specification

## Main Leaderboard Score

For endpoints `E = {AMES, hERG, DILI}`:

```text
Main Score = (1 / 3) * sum(AUROC_e for e in E)
```

All three endpoints have equal weight. The main score is undefined if an endpoint is missing predictions or its hidden test split does not contain both classes. Such a submission fails validation instead of receiving an imputed value.

## AUROC

AUROC is computed from probability scores using the Mann-Whitney rank statistic with average ranks for tied probabilities. Probabilities must be finite values in `[0, 1]`. Hard class labels are syntactically valid probabilities but are discouraged because they discard ranking information.

## Secondary Metrics

The host scorer reports, but does not rank by:

- per-endpoint average precision (`AUPRC`)
- per-endpoint Brier score
- per-endpoint expected calibration error with 10 equal-width probability bins
- macro averages of those endpoint metrics
- scorer runtime and record counts

Training runtime and reproduction evidence come from `experiment_trace.json` and `environment.json`, not from the hidden-label scorer.

## Failure Conditions

Scoring fails when:

- a required `(sample_id, endpoint)` pair is missing or duplicated
- an extra prediction is present
- an endpoint name differs from exactly `AMES`, `hERG`, or `DILI`
- a probability is non-finite or outside `[0, 1]`
- `predictions.csv` contains a label column or any field outside the submission schema
- public `test.csv`, predictions, and hidden labels do not have identical keys
- hidden labels are located below the public dataset root

## Score Provenance

The official local `score.json` must contain `score_source: "host_hidden_test_labels"`, SHA-256 hashes of public test features, predictions, and hidden labels, and the exact scorer version. A framework-authored metric file cannot substitute for this artifact.


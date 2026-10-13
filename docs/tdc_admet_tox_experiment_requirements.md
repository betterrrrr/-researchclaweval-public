# TDC-ADMET-Tox Experiment And Paper Requirements

## Experiment Trace

`experiment_trace.json` must contain:

- `task_id: "tdc_admet_tox"`
- `experiments`, with 2 to 4 complete records
- `selected_experiment_id`
- `selection_metric: "validation_macro_average_auroc"`
- `final_prediction_file: "predictions.csv"`
- `reproduction.entrypoint`, `reproduction.command`, and `reproduction.seed`
- `environment_file: "environment.json"`
- `resource_budget` matching `docs/tdc_admet_tox_compute_budget.md`
- `total_wall_seconds`
- `claims`, a unique claim-evidence ledger

Each experiment record must include:

- `run_id`, `status: "complete"`, and a non-empty `hypothesis`
- non-empty `model_strategy` and `feature_strategy`
- `config_file`, `prediction_file`, `metrics_file`, and `log_file`
- `runtime_seconds` and `seed`
- `candidate_count: 1`
- `validation_metrics.macro_average_auroc`
- `validation_metrics.per_endpoint` AUROC for `AMES`, `hERG`, and `DILI`
- `parent_run_id` and `change_rationale` for experiments 3 and 4

The referenced metrics file must identify `split: "validation"` and contain the same metric values as the trace. Test metrics, hidden-label paths, and framework-authored `score.json` are forbidden.

## Environment Metadata

`environment.json` must record at least:

- operating system or container image identity
- Python version
- installed package versions used by the run
- CPU/GPU execution device
- all random seeds
- creation timestamp

## Paper

The paper is short and evidence based. It should state the hypotheses, methods, validation protocol, comparative results, limitations, and the selected approach. It must not claim access to hidden-test performance.

For Markdown papers, every empirical result cell uses an inline marker such as:

```markdown
| Model | AMES AUROC |
|---|---:|
| Model B | 0.8421 <!-- claim:table1_ames_auroc_model_b --> |
```

Every marker resolves to a claim record whose value and paths match the source experiment. A PDF-only paper must include a Markdown claim sidecar containing the same table values and markers so automated audit does not depend on PDF text extraction.

## Two-Stage Acceptance

Framework stage:

- all framework artifacts exist
- experiment and paper claims pass audit
- no hidden-label artifact exists
- no root-level `score.json` exists

Final stage:

- framework-stage requirements still pass
- root-level `score.json` exists
- its source is `host_hidden_test_labels`
- its prediction hash matches root-level `predictions.csv`

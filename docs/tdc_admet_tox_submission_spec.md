# TDC-ADMET-Tox Submission Specification

## Public Data Files

`train.csv` and `validation.csv` use exactly these columns:

```text
sample_id,endpoint,smiles,label
```

`test.csv` uses exactly these columns and contains no label:

```text
sample_id,endpoint,smiles
```

Endpoint values are case-sensitive: `AMES`, `hERG`, and `DILI`. Labels are binary integers `0` or `1`.

## Trusted Source Projection

The offline projector accepts a host-only normalized source tree:

```text
source-root/
  AMES/{train,validation,test}.csv
  hERG/{train,validation,test}.csv
  DILI/{train,validation,test}.csv
```

Each normalized source file has exactly `sample_id,smiles,label`. The source revision and split-generation procedure must be fixed before projection. The projector rejects cross-split sample IDs, non-binary labels, single-class endpoint splits, nested public/private roots, and non-empty output roots. It strips labels from public test data and writes them to a separate host-only root.

## Prediction Artifact

Root-level `predictions.csv` uses exactly:

```text
sample_id,endpoint,probability
```

Requirements:

- one row for every public test row and no other rows
- the same `sample_id` and `endpoint` pair as public `test.csv`
- a finite positive-class probability in `[0, 1]`
- no `label`, `prediction_label`, SMILES, fold, or metric columns
- deterministic row generation from the selected runnable configuration

Example:

```csv
sample_id,endpoint,probability
AMES_000001,AMES,0.7312
hERG_000001,hERG,0.1184
DILI_000001,DILI,0.5570
```

## Host Scoring Interface

The scorer is invoked outside the framework container:

```bash
python3 automation/scripts/run_tdc_admet_tox_host_score.py \
  --public-dataset-root /path/to/public \
  --hidden-labels /host-private/test_labels.csv \
  --predictions /run/workspace/predictions.csv \
  --output-score /run/workspace/score.json
```

The hidden-label CSV uses `sample_id,endpoint,label`. Its path is never projected into framework inputs, logs, prompts, manifests visible during execution, or container environment variables.

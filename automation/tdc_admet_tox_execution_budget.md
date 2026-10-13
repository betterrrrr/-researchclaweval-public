# TDC-ADMET-Tox Execution Budget

This budget applies independently to every framework evaluation.

## Complete Configuration

A complete configuration is one distinct model, training, or feature strategy evaluated on the fixed validation split. It must produce all of the following before another configuration begins:

- a stated molecular-ML hypothesis
- an immutable configuration file
- validation probabilities for all three endpoints
- per-endpoint AUROC and AUPRC plus macro AUROC
- a complete training/evaluation log
- runtime, seed, feature strategy, and model strategy metadata

Failed setup attempts that do not train or evaluate a configuration are logged but do not count as experiments. Re-running the same configuration with no material change is not a new experiment.

## Hard Limits

- Complete 2 to 4 configurations. Never begin a fifth.
- Each configuration may evaluate exactly one candidate (`candidate_count: 1`). Every hidden sweep candidate counts as a separate configuration.
- At least two configurations must differ in config content and declared model or feature strategy.
- Use experiments 1 and 2 to establish and test the initial hypotheses.
- Run experiment 3 or 4 only when its trace records the prior run and a specific evidence-based change.
- Use the fixed train/validation split. Do not resample validation data to search for a favorable split.
- Keep cumulative experiment runtime at or below 3,600 seconds and total native framework wall time at or below 7,200 seconds. Use no more than 4 vCPU, 16 GiB memory, 10 GiB writable disk, and no GPU.
- Select the final configuration by validation macro AUROC only. Hidden test labels and hidden test scores are unavailable.
- Keep a compact experiment ledger; do not paste datasets, prediction files, or complete source files into the agent context.

## Mandatory Finalization

Immediately after the last allowed configuration:

1. Stop exploration.
2. Select the best valid configuration using validation macro AUROC.
3. Run the selected code once to create root-level `predictions.csv` for public `test.csv`.
4. Write `experiment_trace.json`, `environment.json`, runnable code, logs, and the paper.
5. Do not create `score.json`; exit and hand control to the host scorer.

If the framework cannot produce the required handoff inside its native workflow, it must stop with a concrete blocker rather than fabricate or promote partial results.

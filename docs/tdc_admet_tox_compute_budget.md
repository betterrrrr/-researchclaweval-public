# TDC-ADMET-Tox Fixed Compute Budget

This budget applies independently to every framework and evaluation-model variant.

## Host Limits

- CPU: at most 4 vCPU
- Memory: at most 16 GiB
- GPU: unavailable (`0` GPUs)
- Writable workspace: at most 10 GiB
- Cumulative scientific experiment runtime: at most 3,600 seconds
- Total native framework wall time, including planning and paper generation: at most 7,200 seconds
- Network: only the evaluator-injected LLM relay is allowed; public internet, package indexes, model hubs, chemistry services, and remote data stores are blocked

The wrapper must enforce host limits. The trace must record the observed runtime and declared budget; self-reported values alone are not sufficient runtime evidence.

## Configuration Accounting

A complete configuration contains exactly one candidate model/feature/training strategy evaluated on validation data. Grid search, random search, Bayesian optimization, AutoML, repeated model selection, and any other procedure that evaluates multiple candidates count once per candidate, even when launched from one command.

- Minimum complete configurations: 2
- Maximum complete configurations: 4
- `candidate_count` in every experiment record must equal `1`
- Cross-validation may estimate a single fixed candidate, but changing a hyperparameter or selecting among fitted candidates creates additional configurations
- Seed-only repeats of an otherwise unchanged configuration do not count as materially different experiments

If a framework cannot stay inside these limits, its result is invalid rather than degraded or normalized after the fact.


# TDC-ADMET-Tox Feature-Generation Contract

## Allowed Inputs

Features may be generated only from the provided SMILES string, endpoint identity, and labeled training data. The validation labels may be used for comparing the 2 to 4 declared configurations but not as training labels for those comparisons. Final refitting on train plus validation is allowed only after configuration selection and must be recorded.

## Offline Boundary

- No network access, remote chemistry service, database lookup, literature lookup, or runtime asset download.
- No lookup keyed by `sample_id` or SMILES against external labels or benchmark answers.
- Preinstalled chemistry and ML libraries are allowed when their versions are recorded in `environment.json`.
- Preexisting model artifacts are allowed only when the evaluator explicitly includes and hashes them as visible task inputs.

## Reproducibility

Every experiment records:

- feature generator name and version
- molecular standardization assumptions
- descriptor or fingerprint parameters
- model and training parameters
- random seed
- input file SHA-256 hashes
- generated feature-cache SHA-256 hashes when caches are used

The materialized SMILES and `sample_id` values are immutable. Invalid SMILES handling must be deterministic, logged, and identical across splits. Endpoint-specific models and a shared multi-endpoint model are both allowed, but the chosen strategy must generate all three endpoint probabilities in a single reproducible final command.

## Budget Semantics

Changing a fingerprint radius, descriptor family, molecule standardization rule, model family, loss, calibration strategy, or training procedure and evaluating it on validation data constitutes a new complete configuration. Sweeps count once per evaluated configuration, not once per launcher command.

